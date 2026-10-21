"""Owner-requested, one-time opportunity register reset introduced in 3.5.1.

The backup and reset run before a Store is made available to request handlers.
The database marker is committed with the reset, so later imports are retained
on every subsequent startup. Retiring a fixed cohort instead of deleting rows
preserves legacy foreign-key parents, Tender records and contribution history.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone

from .auto_upgrade import UpgradeError, _process_lock

RESET_KEY = 'opportunities-owner-reset-v351'
log = logging.getLogger(__name__)


def _backup(store, expected_counts):
    """Snapshot committed data while the caller blocks other database writers."""
    folder = store.path.parent / 'upgrade_backups'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = folder / f'{store.path.stem}-before-opportunity-reset-v351-{stamp}-{uuid.uuid4().hex[:6]}.db'
    pending = target.with_suffix('.pending')
    try:
        descriptor = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(f'{store.path.as_uri()}?mode=ro', uri=True, timeout=15)) as source:
            with closing(sqlite3.connect(pending, timeout=15)) as saved:
                deadline = time.monotonic() + 60

                def progress(status, remaining, total):
                    if time.monotonic() > deadline:
                        raise UpgradeError('The opportunity backup timed out. No opportunities were cleared. Ask your administrator to review server storage and retry.')

                source.backup(saved, pages=256, progress=progress)
                if saved.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise UpgradeError('The opportunity backup failed verification. No opportunities were cleared.')
                for table, expected in expected_counts.items():
                    if saved.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0] != expected:
                        raise UpgradeError('The opportunity backup is incomplete. No opportunities were cleared.')
                # A single portable backup file must not depend on WAL sidecars.
                saved.execute('PRAGMA journal_mode=DELETE')
        os.chmod(pending, 0o600)
        os.replace(pending, target)
        return target
    finally:
        pending.unlink(missing_ok=True)


def reset_once(store):
    """Retire the old register once, retaining every original row and link."""
    from . import opportunities, tenders
    from . import opportunity_retention as retention

    opportunities.initialize(store)
    with store.connect() as db:
        retention.ensure_schema(db)
        if db.execute('SELECT 1 FROM settings WHERE id=?', (RESET_KEY,)).fetchone():
            return {'applied': False, 'removed': 0}

    lock = store.path.with_name('.' + store.path.name + '.opportunity-reset-v351.lock')
    with _process_lock(lock):
        with store.connect() as db:
            # Also excludes writes from old workers until the snapshot and reset
            # have both finished. No mutations precede the backup.
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM settings WHERE id=?', (RESET_KEY,)).fetchone():
                return {'applied': False, 'removed': 0}
            counts = {
                'opportunities': db.execute('SELECT COUNT(*) FROM opportunities').fetchone()[0],
                'assignments': db.execute('SELECT COUNT(*) FROM opportunity_people').fetchone()[0],
                'deadlineEvents': db.execute('SELECT COUNT(*) FROM opportunity_events').fetchone()[0],
                'builders': db.execute('SELECT COUNT(*) FROM opportunity_builders').fetchone()[0],
                'notifications': db.execute("SELECT COUNT(*) FROM tender_notifications WHERE target_kind='opportunity'").fetchone()[0],
            }
            previously_visible = db.execute('''SELECT COUNT(*) FROM opportunities
                WHERE deleted_at IS NULL AND ''' + retention.active_sql('opportunity', 'opportunities.id')).fetchone()[0]
            backup_counts = {
                'opportunities': counts['opportunities'],
                'opportunity_people': counts['assignments'],
                'opportunity_events': counts['deadlineEvents'],
                'opportunity_builders': counts['builders'],
                'tender_notifications': db.execute('SELECT COUNT(*) FROM tender_notifications').fetchone()[0],
            }
            backup = _backup(store, backup_counts) if any(counts.values()) else None
            moment = tenders.timestamp()
            retention.retire_current(db, moment)
            details = {
                'release': '3.5.5',
                'reason': 'Owner requested an empty opportunity register before importing new data.',
                'method': 'retained-records',
                'removed': counts,
                'previouslyVisibleOpportunities': previously_visible,
                'backupCreated': backup is not None,
                'contributionHistoryRetained': True,
                'originalRecordsAndRelationshipsRetained': True,
            }
            if any(counts.values()):
                # A register-wide system action has no opportunity/user parent.
                # Do not invent empty IDs or insert them into legacy FK-backed
                # activity tables. This dedicated log and the completion marker
                # retain the reset summary alongside the untouched user history.
                db.execute('''INSERT INTO opportunity_reset_history
                    (reset_key,actor_name,action,details,created_at) VALUES(?,?,?,?,?)''',
                    (RESET_KEY, 'System', 'Cleared opportunity register', json.dumps(details), moment))
                db.execute('UPDATE opportunity_generation SET value=value+1')
            db.execute('INSERT INTO settings(id,body) VALUES(?,?)',
                       (RESET_KEY, json.dumps({**details, 'completedAt': moment,
                                              'backupFile': backup.name if backup else None})))
        if any(counts.values()):
            log.warning('Opportunity register reset completed: %s previously visible opportunities; %s original opportunity records retained; safety backup: %s',
                        previously_visible, counts['opportunities'], backup)
        else:
            log.info('Opportunity reset marker recorded for an empty register.')
    return {'applied': True, 'removed': counts['opportunities']}
