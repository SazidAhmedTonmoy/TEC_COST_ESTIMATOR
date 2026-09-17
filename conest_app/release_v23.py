"""Additive v2.3 migration and account deletion without losing project history."""
from .utils import utc_now
from .accounts import AccessError


def add_columns(conn, table, additions):
    existing = {row['name'] for row in conn.execute(f'PRAGMA table_info("{table}")')}
    for name, definition in additions.items():
        if name not in existing:
            conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')


def initialize_v23(conn):
    conn.commit()
    conn.execute('BEGIN IMMEDIATE')
    add_columns(conn, 'projects', {
        'award_status': "TEXT NOT NULL DEFAULT '' CHECK(award_status IN ('','won','lost'))",
        'award_updated_at': 'TEXT',
        **{f'{key}_name_snapshot': 'TEXT' for key in ('created_by', 'updated_by', 'completed_by')},
    })
    add_columns(conn, 'project_lines', {'reference_name': "TEXT NOT NULL DEFAULT ''"})
    add_columns(conn, 'project_activity', {
        'actor_name_snapshot': 'TEXT', 'actor_username_snapshot': 'TEXT', 'actor_id_snapshot': 'INTEGER',
    })
    for table in ('tender_revisions', 'catalog_price_history'):
        add_columns(conn, table, {'author_name_snapshot': 'TEXT'})
    # Notes formerly required a live author account. Rebuild just these two tables
    # inside a transaction, retaining every note ID and every read receipt.
    author = next(r for r in conn.execute('PRAGMA table_info(project_notes)') if r['name'] == 'author_id')
    if author['notnull']:
        sequence_row = conn.execute("SELECT seq FROM sqlite_sequence WHERE name='project_notes'").fetchone()
        old_note_sequence = sequence_row[0] if sequence_row else 0
        conn.execute('CREATE TEMP TABLE v23_saved_note_reads AS SELECT * FROM project_note_reads')
        conn.execute('''CREATE TABLE project_notes_v23 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            author_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            body TEXT NOT NULL, created_at TEXT NOT NULL,
            author_name_snapshot TEXT, author_username_snapshot TEXT)''')
        conn.execute('''INSERT INTO project_notes_v23(id,project_id,author_id,body,created_at)
            SELECT id,project_id,author_id,body,created_at FROM project_notes''')
        conn.execute('DROP TABLE project_note_reads')
        conn.execute('DROP TABLE project_notes')
        conn.execute('ALTER TABLE project_notes_v23 RENAME TO project_notes')
        # Do not reuse deleted historical note IDs when rebuilding AUTOINCREMENT.
        conn.execute("INSERT INTO sqlite_sequence(name,seq) SELECT 'project_notes',? WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name='project_notes')", (old_note_sequence,))
        conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='project_notes'", (old_note_sequence,))
        conn.execute('CREATE INDEX idx_notes_project ON project_notes(project_id,id DESC)')
        conn.execute('''CREATE TABLE project_note_reads(
            note_id INTEGER NOT NULL REFERENCES project_notes(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            read_at TEXT NOT NULL, PRIMARY KEY(note_id,user_id))''')
        conn.execute('INSERT INTO project_note_reads SELECT * FROM v23_saved_note_reads')
        conn.execute('DROP TABLE v23_saved_note_reads')
    else:
        add_columns(conn, 'project_notes', {'author_name_snapshot': 'TEXT', 'author_username_snapshot': 'TEXT'})
    conn.execute('''CREATE TABLE IF NOT EXISTS account_deletions(
        id INTEGER PRIMARY KEY, deleted_user_id INTEGER NOT NULL, username TEXT NOT NULL,
        name TEXT NOT NULL, deleted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        deleted_at TEXT NOT NULL, transferred_projects INTEGER NOT NULL DEFAULT 0)''')
    conn.execute('INSERT OR IGNORE INTO app_migrations VALUES (?,?)', ('v2.3-project-lighting-workspace', utc_now()))
    conn.execute('UPDATE schema_version SET version=23')
    conn.commit()


def delete_account(conn, target_id, actor, payload):
    """Permanently revoke/delete an account; keep work, history and attribution."""
    live_actor = conn.execute('SELECT * FROM users WHERE id=? AND is_active=1', (actor['id'],)).fetchone()
    if not live_actor or live_actor['role'] != 'admin':
        raise AccessError(403, 'Administrator access is required')
    target = conn.execute('SELECT * FROM users WHERE id=?', (target_id,)).fetchone()
    if not target:
        raise LookupError('User not found')
    if target_id == actor['id']:
        raise ValueError('You cannot delete your own signed-in account')
    if target['role'] == 'admin' and target['is_active'] and conn.execute(
            "SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0] <= 1:
        raise ValueError('At least one active administrator must remain')
    if payload.get('confirm_username') != target['username']:
        raise ValueError('Enter the exact username to confirm account deletion')
    # Keep a human-readable attribution, not credentials or a usable login.
    conn.execute('''UPDATE project_activity SET actor_name_snapshot=?,actor_username_snapshot=?,actor_id_snapshot=?
        WHERE user_id=?''', (target['name'], target['username'], target_id, target_id))
    conn.execute('''UPDATE project_notes SET author_name_snapshot=?,author_username_snapshot=?
        WHERE author_id=?''', (target['name'], target['username'], target_id))
    for table in ('tender_revisions', 'catalog_price_history'):
        conn.execute(f'UPDATE {table} SET author_name_snapshot=? WHERE created_by=?', (target['name'], target_id))
    for field in ('created_by', 'updated_by', 'completed_by'):
        conn.execute(f'UPDATE projects SET {field}_name_snapshot=? WHERE {field}=?', (target['name'], target_id))
    owned = [r[0] for r in conn.execute('SELECT id FROM projects WHERE owner_id=?', (target_id,))]
    from .workspace import record_activity
    for pid in owned:
        conn.execute('UPDATE projects SET owner_id=? WHERE id=?', (actor['id'], pid))
        record_activity(conn, pid, actor, 'Reassigned owner after account deletion',
                        f"Former owner: {target['name']} ({target['username']})")
    for table in ('sessions', 'project_presence', 'project_note_reads', 'deadline_reads', 'project_assignments'):
        conn.execute(f'DELETE FROM {table} WHERE user_id=?', (target_id,))
    # Only this legacy operational assignment field is NOT NULL; its new actor is explicit.
    conn.execute('UPDATE project_assignments SET assigned_by=? WHERE assigned_by=?', (actor['id'], target_id))
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for table in tables:
        cols = {r['name']: r for r in conn.execute(f'PRAGMA table_info("{table}")')}
        for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall():
            if fk['table'] != 'users':
                continue
            field = fk['from']
            if cols[field]['notnull']:
                if conn.execute(f'SELECT 1 FROM "{table}" WHERE "{field}"=? LIMIT 1', (target_id,)).fetchone():
                    raise ValueError('A required account reference must be reassigned before deletion')
            else:
                conn.execute(f'UPDATE "{table}" SET "{field}"=NULL WHERE "{field}"=?', (target_id,))
    conn.execute('''INSERT INTO account_deletions(deleted_user_id,username,name,deleted_by,deleted_at,transferred_projects)
        VALUES (?,?,?,?,?,?)''', (target_id, target['username'], target['name'], actor['id'], utc_now(), len(owned)))
    conn.execute('DELETE FROM users WHERE id=?', (target_id,))
    return {'deleted_user_id': target_id, 'transferred_projects': len(owned)}
