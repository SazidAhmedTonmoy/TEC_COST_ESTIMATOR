"""Editable teams and live team-based project access."""
from .utils import utc_now
from .accounts import AccessError


def initialize_teams(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS app_migrations(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS teams(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS project_teams(
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            team_id INTEGER NOT NULL REFERENCES teams(id),
            assigned_by INTEGER REFERENCES users(id), assigned_at TEXT NOT NULL,
            PRIMARY KEY(project_id,team_id)
        );
        CREATE INDEX IF NOT EXISTS idx_project_teams_team ON project_teams(team_id,project_id);
    ''')
    additions={'users':{'team_id':'INTEGER REFERENCES teams(id)'},'projects':{
        'created_by':'INTEGER REFERENCES users(id)', 'needs_admin_review':'INTEGER NOT NULL DEFAULT 0',
        'admin_reviewed_at':'TEXT', 'admin_reviewed_by':'INTEGER REFERENCES users(id)',
        'revision':'INTEGER NOT NULL DEFAULT 0'},
        'project_lines':{'revision':'INTEGER NOT NULL DEFAULT 0'},
        'sources':{'imported_by':'INTEGER REFERENCES users(id)'}}
    for table,fields in additions.items():
        existing={r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}
        for name,definition in fields.items():
            if name not in existing:conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_users_team ON users(team_id,role)')
    conn.commit()
    conn.execute('BEGIN IMMEDIATE')
    if not conn.execute("SELECT 1 FROM app_migrations WHERE name='v1.8-team-roster'").fetchone():
        from .initial_roster import INITIAL_ROSTER
        now=utc_now()
        for name in ("Internal Team", "Eman's Team"):
            conn.execute('INSERT OR IGNORE INTO teams(name,created_at,updated_at) VALUES (?,?,?)',(name,now,now))
        team_ids={r['name']:r['id'] for r in conn.execute('SELECT id,name FROM teams')}
        # Apply the requested roster once. Later restarts preserve changed passwords,
        # renamed teams, role changes and membership edits.
        for entry in INITIAL_ROSTER:
            username,name,encoded,role,team=entry
            found=conn.execute('SELECT id FROM users WHERE username=? COLLATE NOCASE',(username,)).fetchone()
            values=(name,encoded,role,team_ids.get(team),now)
            if found:
                conn.execute('''UPDATE users SET name=?,password_hash=?,role=?,team_id=?,updated_at=?,
                    is_active=1,must_change_password=1 WHERE id=?''',(*values,found['id']))
                conn.execute('DELETE FROM sessions WHERE user_id=?',(found['id'],))
            else:
                conn.execute('''INSERT INTO users(name,password_hash,role,team_id,updated_at,username,
                    created_at,job_title,must_change_password) VALUES (?,?,?,?,?,?,?,'',1)''',(*values,username,now))
        # Preserve existing users outside the supplied roster and give regular
        # users a default team where no team was previously available.
        conn.execute("UPDATE users SET team_id=? WHERE role='user' AND team_id IS NULL",(team_ids['Internal Team'],))
        conn.execute("UPDATE users SET team_id=NULL WHERE role='admin'")
        conn.execute('''INSERT OR IGNORE INTO project_teams(project_id,team_id,assigned_by,assigned_at)
            SELECT a.project_id,u.team_id,a.assigned_by,a.assigned_at FROM project_assignments a
            JOIN users u ON u.id=a.user_id WHERE u.team_id IS NOT NULL''')
        conn.execute('''UPDATE projects SET created_by=(SELECT user_id FROM project_activity a
            WHERE a.project_id=projects.id AND a.action='Created project' ORDER BY a.id LIMIT 1)
            WHERE created_by IS NULL''')
        conn.execute('INSERT INTO app_migrations VALUES (?,?)',('v1.8-team-roster',now))
    # One-time testing convenience for the supplied roster; never reset passwords
    # or remove first-time setup from accounts created later.
    if not conn.execute("SELECT 1 FROM app_migrations WHERE name='v1.13-existing-roster-ready'").fetchone():
        from .initial_roster import INITIAL_ROSTER
        for username,*_ in INITIAL_ROSTER:
            conn.execute('UPDATE users SET must_change_password=0 WHERE username=? COLLATE NOCASE AND is_active=1',(username,))
        conn.execute('INSERT INTO app_migrations VALUES (?,?)',('v1.13-existing-roster-ready',utc_now()))
    conn.commit()


def validate_team(conn, role, team_id):
    if role=='admin': return None
    if team_id in (None,''):return None
    if type(team_id) is not int or not conn.execute('SELECT 1 FROM teams WHERE id=?',(team_id,)).fetchone():
        raise ValueError('Choose a valid team')
    return team_id


def list_teams(conn, user):
    where='' if user['role']=='admin' else ' WHERE id=?'
    args=() if user['role']=='admin' else (user.get('team_id'),)
    result=[]
    for row in conn.execute('SELECT * FROM teams'+where+' ORDER BY name COLLATE NOCASE',args):
        team=dict(row)
        team['members']=[dict(u) for u in conn.execute('''SELECT id,name,username,is_active FROM users
            WHERE team_id=? AND role='user' ORDER BY name COLLATE NOCASE''',(team['id'],))]
        result.append(team)
    return result


def save_team(conn, payload, actor, team_id=None):
    if actor['role']!='admin':raise AccessError(403,'Administrator access is required')
    if set(payload)-{'name','member_ids'}:raise ValueError('Unknown team field')
    current=conn.execute('SELECT * FROM teams WHERE id=?',(team_id,)).fetchone() if team_id else None
    if team_id and not current:raise LookupError('Team not found')
    name=str(payload.get('name',current['name'] if current else '')).strip()
    if not 1<=len(name)<=100:raise ValueError('Team name must contain 1 to 100 characters')
    now=utc_now()
    if current:conn.execute('UPDATE teams SET name=?,updated_at=? WHERE id=?',(name,now,team_id))
    else:team_id=conn.execute('INSERT INTO teams(name,created_at,updated_at) VALUES (?,?,?)',(name,now,now)).lastrowid
    if 'member_ids' in payload:
        ids=payload['member_ids']
        if not isinstance(ids,list) or len(ids)>500 or any(type(i) is not int or i<=0 for i in ids):
            raise ValueError('Choose valid team members')
        for uid in ids:
            member=conn.execute('SELECT role FROM users WHERE id=?',(uid,)).fetchone()
            if not member or member['role']!='user':raise ValueError('Only users can be team members; admins manage all teams')
        conn.execute('UPDATE users SET team_id=NULL,updated_at=? WHERE team_id=?',(now,team_id))
        for uid in set(ids):conn.execute('UPDATE users SET team_id=?,updated_at=? WHERE id=?',(team_id,now,uid))
    return next(t for t in list_teams(conn,actor) if t['id']==team_id)
