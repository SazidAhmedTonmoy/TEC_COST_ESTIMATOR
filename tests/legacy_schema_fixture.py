"""Private test-fixture downgrades for SQLite versions without DROP COLUMN.

Only the four known migration fixtures below are supported. This is not an
application migration helper or a general SQL parser. The exact appended
declarations are removed from the fixture's existing DDL; all other column and
table constraints remain in that DDL unchanged.
"""

_DECLARATIONS = {
    'catalog_items': {
        'importance_rating': 'importance_rating INTEGER NOT NULL DEFAULT 0 CHECK(importance_rating BETWEEN 0 AND 5)',
    },
    'project_lines': {
        name: name + ' INTEGER NOT NULL DEFAULT 0 CHECK (' + name + ' IN (0,1))'
        for name in ('exclude_material_markup', 'exclude_hours_markup', 'exclude_final_markup')
    },
    'projects': {
        'review_deadline': 'review_deadline TEXT',
        'review_cycle': 'review_cycle INTEGER NOT NULL DEFAULT 0',
    },
    'users': {
        'contact_number': '"contact_number" TEXT NOT NULL DEFAULT \'\'',
        'avatar_version': '"avatar_version" INTEGER NOT NULL DEFAULT 0',
        'has_avatar': '"has_avatar" INTEGER NOT NULL DEFAULT 0',
    },
}


def _quoted(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def drop_fixture_columns(conn, table, columns):
    """Rebuild a prepared private fixture, committing its pending seed writes.

    SQLite cannot disable FK enforcement inside an existing transaction. Commit
    the test's prepared data first, perform the rebuild in its own transaction,
    and restore the caller's FK and ALTER TABLE settings on both success/failure.
    """
    columns = tuple(columns)
    if not columns or len(set(columns)) != len(columns) or not set(columns) <= _DECLARATIONS.get(table, {}).keys():
        raise AssertionError('Unsupported private legacy-schema fixture downgrade')
    table_sql = _quoted(table)
    original = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
    downgraded = original
    for name in columns:
        fragment = ', ' + _DECLARATIONS[table][name]
        if downgraded.count(fragment) != 1:
            raise AssertionError('The known fixture declaration changed: ' + table + '.' + name)
        downgraded = downgraded.replace(fragment, '', 1)
    header, separator, body = downgraded.partition('(')
    if not separator or header.strip() not in ('CREATE TABLE ' + table, 'CREATE TABLE ' + table_sql):
        raise AssertionError('Unexpected CREATE TABLE header in private fixture: ' + table)

    information = [tuple(row) for row in conn.execute('PRAGMA table_info(' + table_sql + ')')]
    surviving = [row for row in information if row[1] not in columns]
    projection = ','.join(_quoted(row[1]) for row in surviving)
    select_rows = 'SELECT ' + projection + ' FROM ' + table_sql + ' ORDER BY id'
    rows = [tuple(row) for row in conn.execute(select_rows)]
    objects = list(conn.execute("SELECT sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY type,name", (table,)))
    sequence = conn.execute('SELECT seq FROM sqlite_sequence WHERE name=?', (table,)).fetchone()
    temporary = '_legacy_fixture_' + table
    if conn.execute('SELECT 1 FROM sqlite_master WHERE name=?', (temporary,)).fetchone():
        raise AssertionError('Temporary fixture table already exists: ' + temporary)
    foreign_keys = conn.execute('PRAGMA foreign_keys').fetchone()[0]
    legacy_alter_table = conn.execute('PRAGMA legacy_alter_table').fetchone()[0]
    conn.commit()
    try:
        conn.execute('PRAGMA foreign_keys=OFF')
        conn.execute('PRAGMA legacy_alter_table=ON')
        if conn.execute('PRAGMA foreign_keys').fetchone()[0]:
            raise AssertionError('Fixture FK enforcement was not disabled outside a transaction')
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('CREATE TABLE ' + _quoted(temporary) + ' (' + body)
        conn.execute('INSERT INTO ' + _quoted(temporary) + ' (' + projection + ') SELECT ' + projection + ' FROM ' + table_sql)
        conn.execute('DROP TABLE ' + table_sql)
        conn.execute('ALTER TABLE ' + _quoted(temporary) + ' RENAME TO ' + table_sql)
        for saved in objects:
            conn.execute(saved[0])
        if sequence is not None:
            conn.execute('UPDATE sqlite_sequence SET seq=? WHERE name=?', (sequence[0], table))
        else:
            conn.execute('DELETE FROM sqlite_sequence WHERE name=?', (table,))
        restored = [tuple(row)[1:] for row in conn.execute('PRAGMA table_info(' + table_sql + ')')]
        if restored != [row[1:] for row in surviving] or rows != [tuple(row) for row in conn.execute(select_rows)]:
            raise AssertionError('The fixture rebuild changed surviving columns or row values')
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise AssertionError('The fixture rebuild did not retain valid foreign-key relationships')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute('PRAGMA legacy_alter_table=' + str(legacy_alter_table))
        conn.execute('PRAGMA foreign_keys=' + str(foreign_keys))
