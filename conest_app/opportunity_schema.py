"""Atomic upgrades for the JSON-backed opportunity register.

An existing SQLite table is not changed by CREATE TABLE IF NOT EXISTS. Inspect
the real columns, upgrade the supported id/body layout, and only then create
indexes that use those columns. The JSON document and existing SQL values are
left intact; newly added search/filter columns are recovered from that document.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import os
import sqlite3
import time
import uuid

from .auto_upgrade import UpgradeError, _process_lock


_COLUMNS = {
    'revision': 'INTEGER NOT NULL DEFAULT 0',
    'status': "TEXT NOT NULL DEFAULT 'pending'",
    'region': "TEXT NOT NULL DEFAULT 'NSW'",
    'due': "TEXT NOT NULL DEFAULT ''",
    'project_key': "TEXT NOT NULL DEFAULT ''",
    'created_by': 'INTEGER',
    'deleted_at': 'TEXT',
    'updated_at': "TEXT NOT NULL DEFAULT ''",
}

_TABLES = (
    '''CREATE TABLE IF NOT EXISTS opportunities (
        id TEXT PRIMARY KEY, body TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL, region TEXT NOT NULL, due TEXT NOT NULL DEFAULT '',
        project_key TEXT NOT NULL, created_by INTEGER,
        deleted_at TEXT, updated_at TEXT NOT NULL)''',
    'CREATE TABLE IF NOT EXISTS opportunity_generation(value INTEGER NOT NULL)',
    '''CREATE TABLE IF NOT EXISTS opportunity_people (
        opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
        kind TEXT NOT NULL, person_id INTEGER NOT NULL,
        PRIMARY KEY(opportunity_id,kind,person_id))''',
    '''CREATE TABLE IF NOT EXISTS opportunity_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL,
        actor_id INTEGER NOT NULL, actor_name TEXT NOT NULL,
        project TEXT NOT NULL, action TEXT NOT NULL,
        details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS opportunity_regions (
        code TEXT PRIMARY KEY, origin TEXT NOT NULL,
        timezone TEXT NOT NULL DEFAULT 'Australia/Sydney')''',
    'CREATE TABLE IF NOT EXISTS opportunity_builders (builder_key TEXT PRIMARY KEY, name TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS opportunity_events (event_key TEXT PRIMARY KEY, created_at TEXT NOT NULL)',
    '''CREATE TABLE IF NOT EXISTS tender_notifications (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
        kind TEXT NOT NULL, target_kind TEXT NOT NULL,
        target_id TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL,
        due TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, read_at TEXT,
        event_key TEXT NOT NULL, UNIQUE(user_id,event_key))''',
)

_RELATED_COLUMNS = {
    'opportunity_generation': {'value'},
    'opportunity_people': {'opportunity_id', 'kind', 'person_id'},
    'opportunity_activity': {'id', 'opportunity_id', 'actor_id', 'actor_name', 'project', 'action', 'details', 'created_at'},
    'opportunity_regions': {'code', 'origin', 'timezone'},
    'opportunity_builders': {'builder_key', 'name'},
    'opportunity_events': {'event_key', 'created_at'},
    'tender_notifications': {'id', 'user_id', 'kind', 'target_kind', 'target_id', 'title', 'message', 'due', 'created_at', 'read_at', 'event_key'},
}

_INDEXES = (
    'CREATE INDEX IF NOT EXISTS opportunity_status_due ON opportunities(deleted_at,status,due)',
    'CREATE INDEX IF NOT EXISTS opportunity_region_project ON opportunities(region,project_key)',
    'CREATE INDEX IF NOT EXISTS opportunity_updated ON opportunities(deleted_at,updated_at DESC)',
    'CREATE INDEX IF NOT EXISTS opportunity_people_lookup ON opportunity_people(kind,person_id,opportunity_id)',
    'CREATE INDEX IF NOT EXISTS opportunity_activity_record ON opportunity_activity(opportunity_id,id DESC)',
    'CREATE INDEX IF NOT EXISTS opportunity_activity_actor ON opportunity_activity(actor_id,created_at)',
    'CREATE INDEX IF NOT EXISTS tender_notification_user ON tender_notifications(user_id,created_at DESC,id DESC)',
    'CREATE INDEX IF NOT EXISTS tender_notification_unread ON tender_notifications(user_id,read_at)',
)


def _columns(db, table):
    # All identifiers come from the schema constants above, never request data.
    return {row['name'] for row in db.execute('PRAGMA table_info("' + table + '")')}


def _backup(store, expected_count):
    """Snapshot committed data while the migration holds the writer reservation."""
    folder = store.path.parent / 'upgrade_backups'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = folder / f'{store.path.stem}-before-opportunity-schema-v353-{stamp}-{uuid.uuid4().hex[:6]}.db'
    pending = target.with_suffix('.pending')
    try:
        # Keep the snapshot private even while SQLite is filling the file.
        descriptor = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(f'{store.path.as_uri()}?mode=ro', uri=True, timeout=15)) as source:
            with closing(sqlite3.connect(pending, timeout=15)) as saved:
                deadline = time.monotonic() + 60

                def progress(status, remaining, total):
                    if time.monotonic() > deadline:
                        raise UpgradeError('The opportunity schema backup timed out. No opportunity schema changes were committed.')

                source.backup(saved, pages=256, progress=progress)
                if saved.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise UpgradeError('The opportunity schema backup failed verification. No opportunity schema changes were committed.')
                if saved.execute('SELECT COUNT(*) FROM opportunities').fetchone()[0] != expected_count:
                    raise UpgradeError('The opportunity schema backup is incomplete. No opportunity schema changes were committed.')
                saved.execute('PRAGMA journal_mode=DELETE')
        os.chmod(pending, 0o600)
        os.replace(pending, target)
        return target
    finally:
        pending.unlink(missing_ok=True)


def _value(item, column):
    """Recover only a missing column; never overwrite an existing SQL value."""
    from .tenders import project_key

    if column == 'revision':
        value = item.get('revision', 0)
        if type(value) is not int or value < 0:
            raise ValueError('revision must be a non-negative integer')
        return value
    if column == 'created_by':
        value = item.get('createdBy')
        if value is not None and type(value) is not int:
            raise ValueError('createdBy must be an integer or null')
        return value
    if column == 'deleted_at':
        value = item.get('deletedAt')
        if value is not None and not isinstance(value, str):
            raise ValueError('deletedAt must be text or null')
        return value or None
    if column == 'project_key':
        value = item.get('project')
        if not isinstance(value, str) or not value.strip():
            raise ValueError('project must contain the project name')
        return project_key(value)
    key, default = {
        'status': ('status', 'pending'),
        'region': ('region', 'NSW'),
        'due': ('due', ''),
        'updated_at': ('updatedAt', item.get('createdAt', '')),
    }[column]
    value = item.get(key, default)
    if not isinstance(value, str):
        raise ValueError(key + ' must be text')
    return value


def _backfill(db, missing):
    if not missing:
        return
    assignments = ','.join('"' + column + '"=?' for column in missing)
    # Stream rows rather than loading an entire imported register into memory.
    for row in db.execute('SELECT id,body FROM opportunities'):
        try:
            item = json.loads(row['body'])
            if not isinstance(item, dict):
                raise ValueError('body must be a JSON object')
            values = [_value(item, column) for column in missing]
        except (TypeError, ValueError) as exc:
            raise UpgradeError('An existing opportunity cannot be upgraded: ' + str(exc) +
                               '. Its stored record and the database backup were preserved.') from exc
        db.execute('UPDATE opportunities SET ' + assignments + ' WHERE id=?', (*values, row['id']))


def _restore_new_lookups(db, absent, default_regions):
    """Recover only absent lookup tables, without fabricating history or notices."""
    from .tenders import builder_key

    needed = absent & {'opportunity_people', 'opportunity_builders', 'opportunity_regions'}
    if not needed:
        return
    for row in db.execute('SELECT id,body FROM opportunities'):
        try:
            item = json.loads(row['body'])
            if not isinstance(item, dict):
                raise ValueError('body must be a JSON object')
            if 'opportunity_people' in needed:
                for kind in ('assignedTeamIds', 'assignedUserIds', 'editorTeamIds', 'editorUserIds'):
                    identifiers = item.get(kind, [])
                    if not isinstance(identifiers, list) or any(type(value) is not int for value in identifiers):
                        raise ValueError(kind + ' must be a list of integer IDs')
                    db.executemany('''INSERT OR IGNORE INTO opportunity_people
                        (opportunity_id,kind,person_id) VALUES(?,?,?)''',
                        [(row['id'], kind, identifier) for identifier in identifiers])
            if 'opportunity_builders' in needed:
                names = item.get('builders', [])
                if not isinstance(names, list) or any(not isinstance(value, str) for value in names):
                    raise ValueError('builders must be a list of names')
                for name in names:
                    key = builder_key(name)
                    if key:
                        db.execute('INSERT OR IGNORE INTO opportunity_builders(builder_key,name) VALUES(?,?)',
                                   (key, name))
            if 'opportunity_regions' in needed:
                code = _value(item, 'region')
                default_origin, zone = default_regions.get(code, ('', 'Australia/Sydney'))
                # A per-project distance override must not become the default
                # for every later project in an already configured region.
                origin = default_origin if code in default_regions else item.get('distanceOrigin')
                if not isinstance(origin, str) or not origin.strip():
                    raise ValueError('distanceOrigin is required for an existing custom region')
                db.execute('INSERT OR IGNORE INTO opportunity_regions(code,origin,timezone) VALUES(?,?,?)',
                           (code, origin, zone))
        except (TypeError, ValueError) as exc:
            raise UpgradeError('Existing opportunity lookups cannot be recovered: ' + str(exc) +
                               '. No opportunity schema changes were committed.') from exc


def initialize(store, default_regions):
    """Create or upgrade once per Store, safely across Passenger workers."""
    lock = store.path.with_name('.' + store.path.name + '.opportunity-schema.lock')
    with _process_lock(lock):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            present = {row['name'] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            existing = _columns(db, 'opportunities') if 'opportunities' in present else set()
            missing = [column for column in _COLUMNS if existing and column not in existing]
            if 'opportunities' in present and not {'id', 'body'} <= existing:
                raise UpgradeError('The existing opportunities table has an unsupported layout: id and body are required. No opportunity schema changes were committed.')
            if existing:
                primary = [row['name'] for row in db.execute('PRAGMA table_info(opportunities)') if row['pk']]
                if primary != ['id']:
                    raise UpgradeError('The existing opportunities table has an unsupported layout: id must be its primary key. No opportunity schema changes were committed.')
            # Unknown related-table layouts need an explicit migration, not an
            # invented reconstruction of assignment, notification or audit data.
            for table, required in _RELATED_COLUMNS.items():
                if table in present:
                    absent = required - _columns(db, table)
                    if absent:
                        raise UpgradeError('The existing ' + table + ' table needs a schema migration for: ' +
                                           ', '.join(sorted(absent)) + '. No opportunity schema changes were committed.')
            count = db.execute('SELECT COUNT(*) FROM opportunities').fetchone()[0] if existing else 0
            absent = set(_RELATED_COLUMNS) - present
            if (missing or absent) and count:
                _backup(store, count)
            for statement in _TABLES:
                db.execute(statement)
            for column in missing:
                db.execute('ALTER TABLE opportunities ADD COLUMN "' + column + '" ' + _COLUMNS[column])
            _backfill(db, missing)
            _restore_new_lookups(db, absent, default_regions)
            for statement in _INDEXES:
                db.execute(statement)
            db.execute('''INSERT INTO opportunity_generation(value) SELECT 0
                WHERE NOT EXISTS (SELECT 1 FROM opportunity_generation)''')
            for code, (origin, zone) in default_regions.items():
                db.execute('INSERT OR IGNORE INTO opportunity_regions(code,origin,timezone) VALUES(?,?,?)',
                           (code, origin, zone))
