"""Preserve constrained legacy audit/assignment tables before current writes.

The current application resolves people in its separate account database and
records both project-specific and register-wide activity. Older installations
can have additional local foreign keys or required metadata on these tables.
Only demonstrated incompatibilities trigger this migration. Original tables,
their complete rows and dependent history remain in permanent archives.
"""
from __future__ import annotations

import sqlite3

from .auto_upgrade import UpgradeError


_COLUMNS = {
    'opportunity_activity': (
        'id', 'opportunity_id', 'actor_id', 'actor_name', 'project', 'action',
        'details', 'created_at',
    ),
    'opportunity_people': ('opportunity_id', 'kind', 'person_id'),
}

_DDL = {
    'opportunity_activity': '''CREATE TABLE opportunity_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL,
        actor_id INTEGER NOT NULL, actor_name TEXT NOT NULL,
        project TEXT NOT NULL, action TEXT NOT NULL,
        details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL)''',
    'opportunity_people': '''CREATE TABLE opportunity_people (
        opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
        kind TEXT NOT NULL, person_id INTEGER NOT NULL,
        PRIMARY KEY(opportunity_id,kind,person_id))''',
}


def _quoted(identifier):
    """Quote schema identifiers obtained from constants or SQLite metadata."""
    return '"' + identifier.replace('"', '""') + '"'


def _foreign_keys(db, table):
    return list(db.execute('PRAGMA foreign_key_list(' + _quoted(table) + ')'))


def _unsupported_required_columns(db, table):
    for row in db.execute('PRAGMA table_info(' + _quoted(table) + ')'):
        if row['name'] in _COLUMNS[table] or not row['notnull']:
            continue
        default = row['dflt_value']
        # A literal NULL default cannot satisfy a NOT NULL column either.
        if default is None or str(default).strip().strip('()').strip().upper() == 'NULL':
            return True
    return False


def migration_plan(db, present):
    """Return only tables whose observed constraints obstruct current writes."""
    plan = []
    if 'opportunity_activity' in present:
        if (_foreign_keys(db, 'opportunity_activity') or
                _unsupported_required_columns(db, 'opportunity_activity')):
            plan.append('opportunity_activity')
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
            plan.append('opportunity_people')
    return plan


def _archive_name(db, table):
    for number in range(1, 101):
        name = table + '_legacy_v355' + ('' if number == 1 else '_' + str(number))
        if not db.execute('SELECT 1 FROM sqlite_master WHERE name=? COLLATE NOCASE', (name,)).fetchone():
            return name
    raise UpgradeError('The legacy ' + table + ' archive names are already in use. No opportunity schema changes were committed.')


def _copy_exactly(db, table, archive):
    columns = ','.join(_quoted(column) for column in _COLUMNS[table])
    source = 'SELECT ' + columns + ' FROM ' + _quoted(archive)
    target = 'SELECT ' + columns + ' FROM ' + _quoted(table)
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


def migrate(db, plan):
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
        if not set(_COLUMNS[table]) <= columns:
            raise UpgradeError('The existing ' + table + ' table has unsupported missing columns. No opportunity schema changes were committed.')

    before = {tuple(row) for row in db.execute('PRAGMA foreign_key_check')}
    archives = {}
    # Rename every original first so cross-table historical references continue
    # to point to the originals, never to a newly created current table.
    for table in plan:
        archive = _archive_name(db, table)
        db.execute('ALTER TABLE ' + _quoted(table) + ' RENAME TO ' + _quoted(archive))
        archives[table] = archive
    for table, archive in archives.items():
        db.execute(_DDL[table])
        _copy_exactly(db, table, archive)

    def renamed(name):
        return archives.get(name.casefold(), name)

    expected = {(renamed(table), row_id, renamed(parent), key_id)
                for table, row_id, parent, key_id in before}
    if {tuple(row) for row in db.execute('PRAGMA foreign_key_check')} != expected:
        raise UpgradeError('The legacy opportunity compatibility migration changed foreign-key integrity. No opportunity schema changes were committed.')
    return archives
