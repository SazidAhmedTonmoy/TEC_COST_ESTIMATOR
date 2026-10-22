"""Restore only approvals demonstrably superseded by the old expiry sweep."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sqlite3
import time
import uuid
from contextlib import closing

from .auto_upgrade import UpgradeError, _process_lock
from .opportunity_retention import active_sql

MIGRATION_KEY = 'opportunities-approved-persistence-v357'


def _instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def _candidates(db):
    from . import opportunities as op
    result = []
    for row in db.execute("SELECT * FROM opportunities WHERE status='expired' AND deleted_at IS NULL AND " +
                          active_sql('opportunity', 'opportunities.id')).fetchall():
        item = op._decode_opportunity(row)
        approval = db.execute('''SELECT * FROM opportunity_activity WHERE opportunity_id=? AND action IN
            ('Approved opportunity','Rejected opportunity','Requested opportunity approval')
            ORDER BY id DESC LIMIT 1''', (item['id'],)).fetchone()
        if not approval or approval['action'] != 'Approved opportunity':
            continue
        try:
            details = json.loads(approval['details'])
        except (ValueError, TypeError):
            continue
        if not isinstance(details, dict) or details.get('after') != 'approved':
            continue
        expired = db.execute('''SELECT * FROM opportunity_activity WHERE opportunity_id=?
            AND action='Expired opportunity' AND actor_id=0 AND actor_name='System' AND id>?
            ORDER BY id DESC LIMIT 1''', (item['id'], approval['id'])).fetchone()
        decision_at, approved_at = _instant(item.get('decisionAt')), _instant(approval['created_at'])
        expired_at = _instant(expired['created_at']) if expired else None
        # Existing approval code sets decisionAt immediately before inserting
        # its audit row. Matching actor plus this ordered timestamp window and
        # the latest-decision query avoids inferring approval from sourceStatus.
        if (item.get('status') != 'expired' or not expired or
                item.get('decisionBy') != approval['actor_id'] or
                item.get('decisionByName') != approval['actor_name'] or
                not decision_at or not approved_at or not expired_at or
                not 0 <= (approved_at - decision_at).total_seconds() <= 60 or
                expired_at < approved_at):
            continue
        result.append((item, approval['id'], expired['id']))
    return result


def _backup(store, expected_counts):
    folder = store.path.parent / 'upgrade_backups'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = folder / f'{store.path.stem}-before-opportunity-workflow-v357-{stamp}-{uuid.uuid4().hex[:6]}.db'
    pending = target.with_suffix('.pending')
    try:
        descriptor = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(f'{store.path.as_uri()}?mode=ro', uri=True, timeout=15)) as source:
            with closing(sqlite3.connect(pending, timeout=15)) as saved:
                deadline = time.monotonic() + 60

                def progress(status, remaining, total):
                    if time.monotonic() > deadline:
                        raise UpgradeError('The approval-history backup timed out. No approval corrections were committed.')

                source.backup(saved, pages=256, progress=progress)
                if saved.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise UpgradeError('The approval-history backup failed verification. No approval corrections were committed.')
                for table, count in expected_counts.items():
                    if saved.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0] != count:
                        raise UpgradeError('The approval-history backup is incomplete. No approval corrections were committed.')
                saved.execute('PRAGMA journal_mode=DELETE')
        os.chmod(pending, 0o600)
        os.replace(pending, target)
        return target
    finally:
        pending.unlink(missing_ok=True)


def restore_approved_once(store):
    """Apply one narrow correction without changing reset membership or history."""
    from . import opportunities as op, tenders
    from .opportunity_reset import RESET_KEY

    with store.connect() as db:
        if db.execute('SELECT 1 FROM settings WHERE id=?', (MIGRATION_KEY,)).fetchone():
            return {'applied': False, 'restored': 0}
    lock = store.path.with_name('.' + store.path.name + '.opportunity-workflow-v357.lock')
    with _process_lock(lock):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM settings WHERE id=?', (MIGRATION_KEY,)).fetchone():
                return {'applied': False, 'restored': 0}
            # Store.__init__ runs this after the one-time reset. Also protect
            # direct repair callers from restoring/notifying an unretired
            # reset cohort if the reset has not completed yet.
            reset_completed = bool(db.execute('SELECT 1 FROM settings WHERE id=?', (RESET_KEY,)).fetchone())
            candidates = _candidates(db) if reset_completed else []
            counts = {table: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                      for table in ('opportunities', 'opportunity_activity', 'tender_activity', 'tender_notifications')}
            backup = _backup(store, counts) if candidates else None
            users = op.directory()[1] if candidates else []
            moment = tenders.timestamp()
            for item, approval_id, expiry_id in candidates:
                previous = {'status': item['status'], 'revision': item['revision'],
                            'updatedAt': item.get('updatedAt')}
                item.update(status='approved', revision=item['revision'] + 1, updatedAt=moment)
                # Preserve original decisionBy/Name/At and the entire old audit
                # trail. The explicit system event explains this new revision.
                op._write(db, item)
                event = op._activity(store, db, op.SYSTEM, 'Restored approved opportunity', item, {
                    'before': previous, 'after': 'approved', 'migration': MIGRATION_KEY,
                    'approvalActivityId': approval_id, 'expiryActivityId': expiry_id,
                    'reason': 'Approved opportunities remain approved after their deadline.',
                }, timestamp=moment)
                op._notify(db, op._recipients(item, users), f'approval-restored:{event}', 'approved', item,
                           'The previous approval has been restored. Approved opportunities now stay approved after their deadline.',
                           created_at=moment)
            db.execute('INSERT INTO settings(id,body) VALUES(?,?)', (MIGRATION_KEY, json.dumps({
                'completedAt': moment, 'restored': len(candidates),
                'pendingResetCohortSkipped': not reset_completed,
                'backupFile': backup.name if backup else None,
            })))
    return {'applied': True, 'restored': len(candidates)}
