"""Preserve constrained legacy opportunity tables before current writes.

The current application resolves people in its separate account database and
records both project-specific and register-wide activity. Older installations
can have additional local foreign keys or required metadata on these tables.
Only demonstrated incompatibilities trigger this migration. Original tables,
their complete rows and dependent history remain in permanent archives.
"""
from __future__ import annotations

import re
import sqlite3

from .auto_upgrade import UpgradeError


_COLUMNS = {
    'opportunities': (
        'id', 'body', 'revision', 'status', 'region', 'due', 'project_key',
        'created_by', 'deleted_at', 'updated_at',
    ),
    'opportunity_activity': (
        'id', 'opportunity_id', 'actor_id', 'actor_name', 'project', 'action',
        'details', 'created_at',
    ),
    'opportunity_people': ('opportunity_id', 'kind', 'person_id'),
    'opportunity_generation': ('value',),
    'opportunity_regions': ('code', 'origin', 'timezone'),
    'opportunity_builders': ('builder_key', 'name'),
    'opportunity_events': ('event_key', 'created_at'),
    'tender_notifications': (
        'id', 'user_id', 'kind', 'target_kind', 'target_id', 'title', 'message',
        'due', 'created_at', 'read_at', 'event_key',
    ),
    'opportunity_reset_entries': ('kind', 'record_key', 'retired_at', 'restored_at'),
    'opportunity_reset_history': ('reset_key', 'actor_name', 'action', 'details', 'created_at'),
}

_DDL = {
    'opportunities': '''CREATE TABLE opportunities (
        id TEXT PRIMARY KEY, body TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL, region TEXT NOT NULL, due TEXT NOT NULL DEFAULT '',
        project_key TEXT NOT NULL, created_by INTEGER,
        deleted_at TEXT, updated_at TEXT NOT NULL)''',
    'opportunity_activity': '''CREATE TABLE opportunity_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL,
        actor_id INTEGER NOT NULL, actor_name TEXT NOT NULL,
        project TEXT NOT NULL, action TEXT NOT NULL,
        details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL)''',
    'opportunity_people': '''CREATE TABLE opportunity_people (
        opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
        kind TEXT NOT NULL, person_id INTEGER NOT NULL,
        PRIMARY KEY(opportunity_id,kind,person_id))''',
    'opportunity_generation': 'CREATE TABLE opportunity_generation(value INTEGER NOT NULL)',
    'opportunity_regions': '''CREATE TABLE opportunity_regions (
        code TEXT PRIMARY KEY, origin TEXT NOT NULL,
        timezone TEXT NOT NULL DEFAULT 'Australia/Sydney')''',
    'opportunity_builders': 'CREATE TABLE opportunity_builders (builder_key TEXT PRIMARY KEY, name TEXT NOT NULL)',
    'opportunity_events': 'CREATE TABLE opportunity_events (event_key TEXT PRIMARY KEY, created_at TEXT NOT NULL)',
    'tender_notifications': '''CREATE TABLE tender_notifications (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
        kind TEXT NOT NULL, target_kind TEXT NOT NULL,
        target_id TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL,
        due TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, read_at TEXT,
        event_key TEXT NOT NULL, UNIQUE(user_id,event_key))''',
    'opportunity_reset_entries': '''CREATE TABLE opportunity_reset_entries (
        kind TEXT NOT NULL, record_key TEXT NOT NULL,
        retired_at TEXT NOT NULL, restored_at TEXT,
        PRIMARY KEY(kind,record_key))''',
    'opportunity_reset_history': '''CREATE TABLE opportunity_reset_history (
        reset_key TEXT PRIMARY KEY, actor_name TEXT NOT NULL,
        action TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL)''',
}

_NULLABLE = {
    'opportunities': {'created_by', 'deleted_at'},
    'tender_notifications': {'read_at'},
    'opportunity_reset_entries': {'restored_at'},
}


def _quoted(identifier):
    """Quote schema identifiers obtained from constants or SQLite metadata."""
    return '"' + identifier.replace('"', '""') + '"'


def _foreign_keys(db, table):
    return list(db.execute('PRAGMA foreign_key_list(' + _quoted(table) + ')'))


def _unsupported_required_columns(db, table):
    for row in db.execute('PRAGMA table_info(' + _quoted(table) + ')'):
        if row['name'] in _NULLABLE.get(table, ()) and row['notnull']:
            return True
        if row['name'] in _COLUMNS[table] or not row['notnull']:
            continue
        default = row['dflt_value']
        # A literal NULL default cannot satisfy a NOT NULL column either.
        if default is None or str(default).strip().strip('()').strip().upper() == 'NULL':
            return True
    return False


def _parent_constraints(db):
    """Observe constraints absent from the current writable parent contract.

    A legacy UNIQUE(region,project_key), for example, prevents re-importing a
    retired project under a fresh ID. Keep every such constraint and its rows
    on the archive; current application validation governs new records.
    """
    if _foreign_keys(db, 'opportunities'):
        return True
    for index in db.execute('PRAGMA index_list(opportunities)'):
        if index['unique']:
            columns = [row['name'] for row in db.execute('PRAGMA index_info(' + _quoted(index['name']) + ')')]
            if columns != ['id']:
                return True
    definition = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='opportunities'").fetchone()[0]
    # Exclude quoted literals/identifiers and comments before recognizing a
    # CHECK keyword. Optional metadata containing the word is not a constraint.
    unquoted = re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^\]]*\]|--[^\n]*|/\*.*?\*/",
                      ' ', definition or '', flags=re.DOTALL)
    return re.search(r'\bCHECK\s*\(', unquoted, flags=re.IGNORECASE) is not None


def migration_plan(db, present, separate_archives=()):
    """Return only tables whose observed constraints obstruct current writes."""
    separate_archives = set(separate_archives)
    if not separate_archives <= set(_COLUMNS):
        raise ValueError('Unsupported separate opportunity archive')
    plan = set()
    if 'opportunities' in present and (
            _unsupported_required_columns(db, 'opportunities') or _parent_constraints(db)):
        plan.add('opportunities')
    for table in _COLUMNS:
        if table in present and table not in {'opportunities', 'opportunity_people'} | separate_archives:
            if _foreign_keys(db, table) or _unsupported_required_columns(db, table):
                plan.add(table)
    if 'opportunity_people' in present:
        outgoing = _foreign_keys(db, 'opportunity_people')
        groups = {}
        for row in outgoing:
            groups.setdefault(row['id'], []).append(row)
        unsupported = any(
            len(rows) != 1 or
            rows[0]['table'].casefold() != 'opportunities' or
            rows[0]['from'].casefold() != 'opportunity_id' or
            (rows[0]['to'] is not None and rows[0]['to'].casefold() != 'id')
            for rows in groups.values()
        )
        # Assignment changes must not erase a historical table's referenced row.
        incoming = any(
            row['table'].casefold() == 'opportunity_people'
            for table in sorted(present)
            if table.casefold() != 'opportunity_people'
            for row in _foreign_keys(db, table)
        )
        if unsupported or incoming or _unsupported_required_columns(db, 'opportunity_people'):
            plan.add('opportunity_people')
    # Native RENAME correctly retargets all incoming references to the original
    # archive. Current app tables must be copied/rebound too or newly created
    # opportunity IDs would fail against that historical parent. Follow only
    # allowlisted current names; never rewrite an unknown historical table.
    for _ in _COLUMNS:
        dependent = {
            table for table in _COLUMNS if table in present and table not in plan | separate_archives
            if any(row['table'].casefold() in plan | separate_archives for row in _foreign_keys(db, table))
        }
        if not dependent:
            break
        plan.update(dependent)
    return [table for table in _COLUMNS if table in plan]


def _archive_name(db, table, version):
    for number in range(1, 101):
        name = table + '_legacy_' + version + ('' if number == 1 else '_' + str(number))
        if not db.execute('SELECT 1 FROM sqlite_master WHERE name=? COLLATE NOCASE', (name,)).fetchone():
            return name
    raise UpgradeError('The legacy ' + table + ' archive names are already in use. No opportunity schema changes were committed.')


def _copy_exactly(db, table, archive, recover_parent=None):
    present = {row['name'] for row in db.execute('PRAGMA table_info(' + _quoted(archive) + ')')}
    known = _COLUMNS[table]
    missing = [column for column in known if column not in present]
    columns = ','.join(_quoted(column) for column in known if column in present)
    source = 'SELECT ' + columns + ' FROM ' + _quoted(archive)
    target = 'SELECT ' + columns + ' FROM ' + _quoted(table)
    if missing:
        if table != 'opportunities' or recover_parent is None or not {'id', 'body'} <= present:
            raise UpgradeError('The existing ' + table + ' table has unsupported missing columns. No opportunity schema changes were committed.')
        # Recover missing current fields into the new table only. The original
        # archive retains its exact columns and values, and no legacy UPDATE
        # trigger can alter historical metadata during this backfill.
        extra = ',creator_id' if 'created_by' in missing and 'creator_id' in present else ''
        insert = 'INSERT INTO ' + _quoted(table) + '(' + ','.join(map(_quoted, known)) + ') VALUES(' + ','.join('?' for _ in known) + ')'
        for row in db.execute('SELECT ' + columns + extra + ' FROM ' + _quoted(archive)):
            recovered = recover_parent(row, missing)
            db.execute(insert, [row[column] if column in present else recovered[column] for column in known])
    else:
        db.execute('INSERT INTO ' + _quoted(table) + '(' + columns + ') ' + source)
    source_count = db.execute('SELECT COUNT(*) FROM ' + _quoted(archive)).fetchone()[0]
    target_count = db.execute('SELECT COUNT(*) FROM ' + _quoted(table)).fetchone()[0]
    if (source_count != target_count or
            db.execute(source + ' EXCEPT ' + target + ' LIMIT 1').fetchone() or
            db.execute(target + ' EXCEPT ' + source + ' LIMIT 1').fetchone()):
        raise UpgradeError('The legacy ' + table + ' records could not be copied exactly. No opportunity schema changes were committed.')

    if table == 'opportunity_activity':
        # Preserve AUTOINCREMENT high-water marks as well as existing IDs. An
        # older deleted event ID must not be reused by notification event keys.
        old = db.execute('SELECT seq FROM sqlite_sequence WHERE name=?', (archive,)).fetchone()
        if old is not None:
            if type(old[0]) is not int or old[0] < 0:
                raise UpgradeError('The legacy activity sequence is invalid. No opportunity schema changes were committed.')
            current = db.execute('SELECT seq FROM sqlite_sequence WHERE name=?', (table,)).fetchone()
            high = max(old[0], current[0] if current is not None else 0)
            if current is None:
                db.execute('INSERT INTO sqlite_sequence(name,seq) VALUES(?,?)', (table, high))
            else:
                db.execute('UPDATE sqlite_sequence SET seq=? WHERE name=?', (high, table))


def migrate(db, plan, recover_parent=None):
    """Archive and copy inside the caller's backed-up write transaction.

    Named indexes and triggers stay with their original archived tables. The
    caller creates distinct indexes for the current tables after migration.
    """
    if not plan:
        return {}
    if len(set(plan)) != len(plan) or any(table not in _COLUMNS for table in plan):
        raise ValueError('Unsupported opportunity compatibility migration')
    if not db.in_transaction:
        raise UpgradeError('Opportunity compatibility migration requires an active write transaction.')
    if sqlite3.sqlite_version_info < (3, 26, 0):
        raise UpgradeError('Migrating legacy opportunity references requires SQLite 3.26 or newer. No opportunity schema changes were committed.')
    if db.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
        raise UpgradeError('Foreign-key enforcement must be enabled before migrating legacy opportunity references. No opportunity schema changes were committed.')
    db.execute('PRAGMA legacy_alter_table=OFF')
    if db.execute('PRAGMA legacy_alter_table').fetchone()[0] != 0:
        raise UpgradeError('SQLite could not enable safe opportunity-table renaming. No opportunity schema changes were committed.')
    for table in plan:
        columns = {row['name'] for row in db.execute('PRAGMA table_info(' + _quoted(table) + ')')}
        allowed_missing_parent = table == 'opportunities' and recover_parent is not None and {'id', 'body'} <= columns
        if not set(_COLUMNS[table]) <= columns and not allowed_missing_parent:
            raise UpgradeError('The existing ' + table + ' table has unsupported missing columns. No opportunity schema changes were committed.')

    before = {tuple(row) for row in db.execute('PRAGMA foreign_key_check')}
    archives = {}
    version = 'v355' if set(plan) <= {'opportunity_activity', 'opportunity_people'} else 'v356'
    # Rename every original first so cross-table historical references continue
    # to point to the originals, never to a newly created current table.
    for table in plan:
        archive = _archive_name(db, table, version)
        db.execute('ALTER TABLE ' + _quoted(table) + ' RENAME TO ' + _quoted(archive))
        archives[table] = archive
    # The only canonical outgoing FK is people -> opportunities. Always build
    # the current parent first, including when a caller supplies a different
    # plan ordering. All originals were already archived above.
    for table in _COLUMNS:
        if table not in archives:
            continue
        archive = archives[table]
        db.execute(_DDL[table])
        _copy_exactly(db, table, archive, recover_parent=recover_parent)

    archived_names = {name.casefold() for name in archives.values()}
    for table in _COLUMNS:
        if any(row['table'].casefold() in archived_names for row in _foreign_keys(db, table)):
            raise UpgradeError('A current opportunity table still references an archived parent. No opportunity schema changes were committed.')

    def renamed(name):
        return archives.get(name.casefold(), name)

    expected = {(renamed(table), row_id, renamed(parent), key_id)
                for table, row_id, parent, key_id in before}
    if {tuple(row) for row in db.execute('PRAGMA foreign_key_check')} != expected:
        raise UpgradeError('The legacy opportunity compatibility migration changed foreign-key integrity. No opportunity schema changes were committed.')
    return archives
