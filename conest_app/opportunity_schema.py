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
import re
import sqlite3
import time
import uuid

from .auto_upgrade import UpgradeError, _process_lock
from . import opportunity_compatibility, opportunity_retention


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


def _create_index(db, statement):
    """Keep archived indexes intact and index the current table as well."""
    match = re.match(r'CREATE(?: UNIQUE)? INDEX(?: IF NOT EXISTS)? (\w+) ON (\w+)', statement)
    if not match:
        raise ValueError('Unsupported opportunity index definition')
    name, table = match.groups()
    for number in range(101):
        candidate = name if number == 0 else name + '_v355' + ('' if number == 1 else '_' + str(number))
        owner = db.execute('SELECT tbl_name FROM sqlite_master WHERE name=? COLLATE NOCASE',
                           (candidate,)).fetchone()
        if not owner or owner['tbl_name'].casefold() == table.casefold():
            db.execute(statement[:match.start(1)] + candidate + statement[match.end(1):])
            return
    raise UpgradeError('An opportunity index name could not be reserved. No opportunity schema changes were committed.')


def _backup(store, expected_counts):
    """Snapshot committed data while the migration holds the writer reservation."""
    folder = store.path.parent / 'upgrade_backups'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = folder / f'{store.path.stem}-before-opportunity-schema-v354-{stamp}-{uuid.uuid4().hex[:6]}.db'
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
                # A legacy builder directory can exist without any opportunity
                # rows, or even without the opportunities table itself.
                for table, expected in expected_counts.items():
                    if saved.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0] != expected:
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


def _builder_archive_name(db):
    # A retry rolls back the rename, but a separately restored legacy table may
    # coexist with an earlier archive. Never replace or reuse that archive.
    for number in range(1, 101):
        name = 'opportunity_builders_legacy_v354' + ('' if number == 1 else '_' + str(number))
        if not db.execute('SELECT 1 FROM sqlite_master WHERE name=? COLLATE NOCASE', (name,)).fetchone():
            return name
    raise UpgradeError('The legacy builder archive names are already in use. No opportunity schema changes were committed.')


def _migrate_builders(db):
    """Retain the original directory and construct a writable current lookup.

    Adding a key alone leaves legacy required columns/constraints in place and
    can silently reject current INSERT OR IGNORE(builder_key,name) writes.
    Native RENAME preserves the original rows, columns, indexes and constraints;
    modern SQLite also keeps dependent views/triggers and foreign keys attached
    to those archived historical rows. The archive must never be dropped.
    """
    from .builders import validate_builders
    from .tenders import builder_key

    if sqlite3.sqlite_version_info < (3, 26, 0):
        raise UpgradeError('Migrating the legacy builder directory requires SQLite 3.26 or newer so references are preserved. No opportunity schema changes were committed.')
    if db.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
        raise UpgradeError('Foreign-key enforcement must be enabled before migrating the legacy builder directory. No opportunity schema changes were committed.')
    db.execute('PRAGMA legacy_alter_table=OFF')
    if db.execute('PRAGMA legacy_alter_table').fetchone()[0] != 0:
        raise UpgradeError('SQLite could not enable safe builder-table renaming. No opportunity schema changes were committed.')
    before = {tuple(row) for row in db.execute('PRAGMA foreign_key_check')}
    archive = _builder_archive_name(db)
    db.execute('ALTER TABLE opportunity_builders RENAME TO "' + archive + '"')
    db.execute('CREATE TABLE opportunity_builders (builder_key TEXT PRIMARY KEY, name TEXT NOT NULL)')
    # Binary source ordering makes the retained display spelling deterministic.
    # Every raw spelling and invalid/empty entry remains in the archived table.
    for row in db.execute('SELECT name FROM "' + archive + '" ORDER BY name COLLATE BINARY'):
        if not isinstance(row['name'], str):
            continue
        try:
            names = validate_builders([row['name']])
        except ValueError:
            continue
        if not names:
            continue
        name = names[0]
        key = builder_key(name)
        if key:
            db.execute('INSERT OR IGNORE INTO opportunity_builders(builder_key,name) VALUES(?,?)', (key, name))
    # Existing violations are not repaired or hidden by this focused migration.
    # Account for SQLite's reference renames before checking for new violations.
    expected = {
        (archive if table.casefold() == 'opportunity_builders' else table, row_id,
         archive if parent.casefold() == 'opportunity_builders' else parent, key_id)
        for table, row_id, parent, key_id in before
    }
    if {tuple(row) for row in db.execute('PRAGMA foreign_key_check')} != expected:
        raise UpgradeError('The legacy builder migration changed foreign-key integrity. No opportunity schema changes were committed.')


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
            builder_columns = _columns(db, 'opportunity_builders') if 'opportunity_builders' in present else set()
            legacy_builders = 'name' in builder_columns and 'builder_key' not in builder_columns
            # Unknown related-table layouts need an explicit migration, not an
            # invented reconstruction of assignment, notification or audit data.
            for table, required in _RELATED_COLUMNS.items():
                if table in present:
                    absent = required - _columns(db, table)
                    if table == 'opportunity_builders' and legacy_builders:
                        continue
                    if absent:
                        raise UpgradeError('The existing ' + table + ' table needs a schema migration for: ' +
                                           ', '.join(sorted(absent)) + '. No opportunity schema changes were committed.')
            compatibility_plan = opportunity_compatibility.migration_plan(db, present)
            counts = {table: db.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0]
                      for table in dict.fromkeys(('opportunities', 'opportunity_builders', *compatibility_plan))
                      if table in present}
            absent = set(_RELATED_COLUMNS) - present
            if legacy_builders or compatibility_plan or ((missing or absent) and any(counts.values())):
                _backup(store, counts)
            if legacy_builders:
                _migrate_builders(db)
            if compatibility_plan:
                opportunity_compatibility.migrate(db, compatibility_plan)
            for statement in _TABLES:
                db.execute(statement)
            opportunity_retention.ensure_schema(db)
            for column in missing:
                db.execute('ALTER TABLE opportunities ADD COLUMN "' + column + '" ' + _COLUMNS[column])
            _backfill(db, missing)
            _restore_new_lookups(db, absent, default_regions)
            for statement in _INDEXES:
                _create_index(db, statement)
            db.execute('''INSERT INTO opportunity_generation(value) SELECT 0
                WHERE NOT EXISTS (SELECT 1 FROM opportunity_generation)''')
            for code, (origin, zone) in default_regions.items():
                db.execute('INSERT OR IGNORE INTO opportunity_regions(code,origin,timezone) VALUES(?,?,?)',
                           (code, origin, zone))
