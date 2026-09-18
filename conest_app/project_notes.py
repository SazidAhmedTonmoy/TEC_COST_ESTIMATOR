"""Shared, attributed project notes."""
from .workspace import require_project, record_activity, permissions
from .utils import utc_now


def initialize_notes(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS project_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        author_id INTEGER NOT NULL REFERENCES users(id),
        body TEXT NOT NULL, created_at TEXT NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_notes_project ON project_notes(project_id,id DESC)')
    conn.execute('''CREATE TABLE IF NOT EXISTS project_note_reads(
        note_id INTEGER NOT NULL REFERENCES project_notes(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        read_at TEXT NOT NULL, PRIMARY KEY(note_id,user_id))''')
    columns={r['name'] for r in conn.execute('PRAGMA table_info(project_activity)')}
    for name in ('team_name_snapshot','role_snapshot'):
        if name not in columns:conn.execute(f'ALTER TABLE project_activity ADD COLUMN {name} TEXT')



def list_notes(conn, project_id, user):
    project = require_project(conn,project_id,user,'view')
    editable = permissions(conn, project, user)['can_edit']
    return [{**dict(r), 'can_delete': editable} for r in conn.execute('''SELECT n.id,n.body,n.created_at,COALESCE(n.author_name_snapshot,u.name) AS author_name,COALESCE(n.author_username_snapshot,u.username) AS username
        FROM project_notes n LEFT JOIN users u ON u.id=n.author_id WHERE n.project_id=? ORDER BY n.id DESC''',(project_id,))]


def add_note(conn, project_id, user, payload):
    require_project(conn,project_id,user,'edit')
    body=payload.get('body')
    if not isinstance(body,str) or not 1<=len(body.strip())<=10000:
        raise ValueError('Enter a note of 1 to 10,000 characters')
    conn.execute('INSERT INTO project_notes(project_id,author_id,body,created_at) VALUES (?,?,?,?)',
                 (project_id,user['id'],body.strip(),utc_now()))
    record_activity(conn,project_id,user,'Added project note',touch=False)
    return list_notes(conn,project_id,user)


def delete_note(conn, project_id, note_id, user):
    require_project(conn,project_id,user,'edit')
    note=conn.execute('SELECT id FROM project_notes WHERE id=? AND project_id=?',(note_id,project_id)).fetchone()
    if not note:raise LookupError('Note not found')
    conn.execute('DELETE FROM project_notes WHERE id=?',(note_id,))
    record_activity(conn,project_id,user,'Removed project note',f'Note {note_id}',touch=False)
    return list_notes(conn,project_id,user)


def note_status(conn, project_id, user):
    require_project(conn,project_id,user,'view')
    count=conn.execute('''SELECT COUNT(*) FROM project_notes n WHERE n.project_id=? AND (n.author_id IS NULL OR n.author_id<>?)
        AND NOT EXISTS(SELECT 1 FROM project_note_reads r WHERE r.note_id=n.id AND r.user_id=?)''',
        (project_id,user['id'],user['id'])).fetchone()[0]
    return {'unread_count':count}


def mark_notes_read(conn, project_id, user, payload):
    require_project(conn,project_id,user,'view')
    ids=payload.get('note_ids')
    if not isinstance(ids,list) or len(ids)>10000 or any(type(i) is not int or i<=0 for i in ids):
        raise ValueError('Choose valid note IDs')
    for nid in set(ids):
        note=conn.execute('SELECT project_id FROM project_notes WHERE id=?',(nid,)).fetchone()
        if not note:continue  # A displayed note may have been deleted meanwhile.
        if note['project_id']!=project_id:raise ValueError('Note belongs to another project')
        conn.execute('INSERT OR IGNORE INTO project_note_reads(note_id,user_id,read_at) VALUES (?,?,?)',
                     (nid,user['id'],utc_now()))
    return note_status(conn,project_id,user)
