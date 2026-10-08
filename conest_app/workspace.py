"""Shared team projects, the admin review queue, and attributable activity."""
from __future__ import annotations
from datetime import date
from .accounts import AccessError, public_user
from .utils import utc_now
from .builders import project_with_builders, stored_builders

STATUSES = ('draft', 'in_progress', 'in_review', 'submitted', 'closed')


def initialize_workspace(conn):
    columns = {r['name'] for r in conn.execute('PRAGMA table_info(projects)')}
    additions = {
        'owner_id': 'INTEGER REFERENCES users(id)', 'scope_of_work': "TEXT NOT NULL DEFAULT ''",
        'submission_deadline': 'TEXT', 'status': "TEXT NOT NULL DEFAULT 'draft'", 'published_at': 'TEXT',
        'completed_at': 'TEXT', 'completed_by': 'INTEGER REFERENCES users(id)',
        'updated_by': 'INTEGER REFERENCES users(id)',
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f'ALTER TABLE projects ADD COLUMN {name} {definition}')
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS project_assignments (
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id), assigned_by INTEGER NOT NULL REFERENCES users(id),
            assigned_at TEXT NOT NULL, PRIMARY KEY(project_id,user_id));
        CREATE INDEX IF NOT EXISTS idx_assignments_user ON project_assignments(user_id,project_id);
        CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner_id);
        CREATE TABLE IF NOT EXISTS project_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            project_name TEXT NOT NULL, user_id INTEGER REFERENCES users(id), action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_activity_actor ON project_activity(user_id,created_at);
        CREATE INDEX IF NOT EXISTS idx_activity_project ON project_activity(project_id,id DESC);
    ''')
    admin_id = conn.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()[0]
    conn.execute('UPDATE projects SET owner_id=? WHERE owner_id IS NULL', (admin_id,))
    conn.commit()


def get_project(conn, project_id):
    row = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
    if not row: raise LookupError('Project not found')
    return dict(row)


def check_revision(record, payload):
    if 'expected_revision' in payload:
        expected = payload['expected_revision']
        if type(expected) is not int or expected != record['revision']:
            raise AccessError(409, 'Someone else has changed this record. Refresh it and apply your edit again.')


def permissions(conn, project, user):
    # Read access is company-wide for signed-in active accounts. Write access
    # remains project-specific and uses LIVE account/team membership, not flags
    # from the browser or a stale session snapshot.
    actor = conn.execute('SELECT role,is_active FROM users WHERE id=?', (user['id'],)).fetchone()
    active = bool(actor and actor['is_active'])
    assigned = active and bool(conn.execute('''SELECT 1 FROM project_teams p JOIN users u ON u.team_id=p.team_id
        WHERE p.project_id=? AND u.id=? AND u.role='user' AND u.is_active=1''',
        (project['id'], user['id'])).fetchone())
    admin = active and actor['role'] == 'admin'
    owner = active and project['owner_id'] == user['id']
    individual = active and bool(conn.execute(
        'SELECT 1 FROM project_user_access WHERE project_id=? AND user_id=?',
        (project['id'], user['id'])).fetchone())
    editable = bool(admin or owner or assigned or individual)
    return {'can_view': active, 'can_edit': editable, 'can_manage': bool(admin or owner),
            'can_delete': bool(admin or owner), 'is_assigned': bool(assigned or individual),
            'is_team_assigned': bool(assigned), 'is_individually_assigned': bool(individual), 'is_owner': bool(owner)}


def require_project(conn, project_id, user, mode='edit'):
    project = get_project(conn, project_id)
    access = permissions(conn, project, user)
    if not access['can_view']: raise AccessError(404, 'Project not found')
    if not access['can_' + mode]:
        message = ('This project is read-only for you. Only its owner, assigned team members, individually assigned users or an administrator can edit it.'
                   if mode == 'edit' else 'Only the project creator or an administrator can do this')
        raise AccessError(403, message)
    return project


def decorate_project(conn, project, user, *, directory=None):
    result = project_with_builders(project)
    result.update(permissions(conn, result, user))
    for column, output in [('owner_id', 'owner_name'), ('created_by', 'created_by_name'),
                           ('updated_by', 'updated_by_name'), ('completed_by', 'completed_by_name')]:
        if directory is None:
            row = conn.execute('SELECT name FROM users WHERE id=?', (result.get(column),)).fetchone()
            name = row[0] if row else None
        else:
            name = directory['names'].get(result.get(column))
        result[output] = name if name is not None else result.get(column + '_name_snapshot')
    if directory is None:
        result['teams'] = [dict(r) for r in conn.execute('''SELECT t.id,t.name FROM project_teams p
            JOIN teams t ON t.id=p.team_id WHERE p.project_id=? ORDER BY t.name COLLATE NOCASE''', (result['id'],))]
        result['individual_users'] = [dict(r) for r in conn.execute('''SELECT u.id,u.name,u.username,u.is_active,t.name AS team_name
            FROM project_user_access a JOIN users u ON u.id=a.user_id LEFT JOIN teams t ON t.id=u.team_id
            WHERE a.project_id=? ORDER BY u.name COLLATE NOCASE,u.id''', (result['id'],))]
        result['contributors'] = project_contributors(conn,result['id'])
    else:
        for key in ('teams', 'individual_users', 'contributors'):
            result[key] = directory[key].get(result['id'], [])
    # Legacy publication records remain in the database for preservation only.
    result.pop('published_at', None)
    result['needs_admin_review'] = bool(result['needs_admin_review'])
    return result


def _project_directory(conn):
    """Batch display metadata once per list request; never cache access grants."""
    directory = {'names': dict(conn.execute('SELECT id,name FROM users')),
                 'teams': {}, 'individual_users': {}, 'contributors': {}}
    queries = {
        'teams': """SELECT p.project_id,t.id,t.name FROM project_teams p
            JOIN teams t ON t.id=p.team_id ORDER BY t.name COLLATE NOCASE""",
        'individual_users': """SELECT a.project_id,u.id,u.name,u.username,u.is_active,t.name AS team_name
            FROM project_user_access a JOIN users u ON u.id=a.user_id LEFT JOIN teams t ON t.id=u.team_id
            ORDER BY u.name COLLATE NOCASE,u.id""",
    }
    for key, sql in queries.items():
        for row in conn.execute(sql):
            record = dict(row)
            directory[key].setdefault(record.pop('project_id'), []).append(record)
    for record in project_contributors(conn, None):
        directory['contributors'].setdefault(record.pop('project_id'), []).append(record)
    return directory


def visible_projects(conn, user, include_totals=True):
    from .projects import project_totals
    actor = conn.execute('SELECT is_active FROM users WHERE id=?', (user['id'],)).fetchone()
    if not actor or not actor['is_active']:
        raise AccessError(403, 'An active account is required')
    rows = conn.execute('SELECT p.* FROM projects p ORDER BY p.updated_at DESC,p.id DESC').fetchall()
    directory = _project_directory(conn) if rows else None
    result = []
    for row in rows:
        project = decorate_project(conn, row, user, directory=directory)
        if include_totals:
            project['totals'] = project_totals(conn, project['id'])
            project['line_count'] = project['totals']['line_count']
        result.append(project)
    return result


def record_activity(conn, project_id, user, action, details='', touch=True):
    row = get_project(conn, project_id)
    now = utc_now()
    actor=conn.execute('SELECT u.role,t.name FROM users u LEFT JOIN teams t ON t.id=u.team_id WHERE u.id=?',(user['id'],)).fetchone()
    conn.execute('INSERT INTO project_activity(project_id,project_name,user_id,action,details,created_at,team_name_snapshot,role_snapshot) VALUES (?,?,?,?,?,?,?,?)',
                 (project_id, row['name'], user['id'], action, details, now, actor['name'], actor['role']))
    if touch:
        conn.execute('UPDATE projects SET updated_by=?,updated_at=?,revision=revision+1 WHERE id=?',
                     (user['id'], now, project_id))


def register_project(conn, project_id, user):
    """Creation, team sharing and the review flag commit in one transaction."""
    team = conn.execute('SELECT team_id FROM users WHERE id=?', (user['id'],)).fetchone()[0]
    conn.execute('UPDATE projects SET owner_id=?,created_by=?,needs_admin_review=? WHERE id=?',
                 (user['id'], user['id'], int(user['role']=='user'), project_id))
    record_activity(conn, project_id, user, 'Created project')
    if user['role']=='user' and team:
        conn.execute('INSERT INTO project_teams VALUES (?,?,?,?)', (project_id, team, user['id'], utc_now()))
        name = conn.execute('SELECT name FROM teams WHERE id=?', (team,)).fetchone()[0]
        record_activity(conn, project_id, user, 'Shared with creator’s team', name)


def review_project(conn, project_id, user):
    if user['role']!='admin': raise AccessError(403, 'Administrator access is required')
    project = get_project(conn, project_id)
    if project['needs_admin_review']:
        conn.execute('UPDATE projects SET needs_admin_review=0,admin_reviewed_at=?,admin_reviewed_by=? WHERE id=?',
                     (utc_now(), user['id'], project_id))
        record_activity(conn, project_id, user, 'Reviewed new project', touch=False)
    return decorate_project(conn, get_project(conn, project_id), user)


def project_activity(conn, project_id, user, before_id=None, limit=200):
    """Read every retained event through stable ID-keyset pagination."""
    require_project(conn, project_id, user, 'view')
    if before_id is not None and (type(before_id) is not int or before_id <= 0):
        raise ValueError('Choose a valid activity cursor')
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('Activity page size must be between 1 and 200')
    condition = ' AND a.id < ?' if before_id is not None else ''
    values = [project_id] + ([before_id] if before_id is not None else []) + [limit]
    return [dict(r) for r in conn.execute("""SELECT a.id,a.action,a.details,a.created_at,
        a.team_name_snapshot,a.role_snapshot,COALESCE(u.name,a.actor_name_snapshot,'Former user') AS name,
        COALESCE(u.username,a.actor_username_snapshot) AS username
        FROM project_activity a LEFT JOIN users u ON u.id=a.user_id
        WHERE a.project_id=?""" + condition + ' ORDER BY a.id DESC LIMIT ?', values)]


def _validate_access_ids(conn, ids, kind, project):
    if not isinstance(ids, list) or len(ids) > 500 or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError('Choose valid project ' + ('teams' if kind == 'team' else 'users'))
    chosen = set(ids)
    for uid in chosen:
        if kind == 'team':
            if not conn.execute('SELECT 1 FROM teams WHERE id=?', (uid,)).fetchone():
                raise ValueError('Team not found')
        else:
            member = conn.execute('SELECT is_active,role FROM users WHERE id=?', (uid,)).fetchone()
            if not member:
                raise ValueError('User not found')
            # Keep existing inactive grants visible/removable; never grant new
            # access to an inactive account. Reactivation remains admin-only.
            existing = conn.execute('SELECT 1 FROM project_user_access WHERE project_id=? AND user_id=?', (project['id'],uid)).fetchone()
            if not member['is_active'] and not existing:
                raise ValueError('Only active users can be assigned to a project')
            if member['role'] == 'admin' or uid == project['owner_id']:
                if not existing:
                    raise ValueError('The owner and administrators already have full project access')
    return chosen


def project_access_options(conn, project_id, user):
    """A minimal, project-scoped assignment directory; not admin account access."""
    project = require_project(conn, project_id, user, 'manage')
    teams = [dict(r) for r in conn.execute("""SELECT t.id,t.name,COUNT(u.id) AS active_members
        FROM teams t LEFT JOIN users u ON u.team_id=t.id AND u.is_active=1 AND u.role='user'
        GROUP BY t.id ORDER BY t.name COLLATE NOCASE""")]
    users = [dict(r) for r in conn.execute("""SELECT u.id,u.name,u.username,u.team_id,u.is_active,t.name AS team_name
        FROM users u LEFT JOIN teams t ON t.id=u.team_id
        WHERE (u.is_active=1 AND u.role='user' AND u.id<>?) OR u.id IN
            (SELECT user_id FROM project_user_access WHERE project_id=?)
        ORDER BY u.name COLLATE NOCASE,u.id""", (project['owner_id'],project_id))]
    return {'teams':teams, 'users':users}


def update_workflow(conn, project_id, payload, user):
    project = require_project(conn, project_id, user)
    check_revision(project, payload)
    allowed = {'name', 'scope_of_work', 'submission_deadline', 'review_deadline', 'status', 'team_ids', 'user_ids', 'expected_revision', 'award_status', 'builders'}
    if set(payload) - allowed: raise ValueError('Unknown project workflow field')
    if {'team_ids', 'user_ids'} & payload.keys() and not permissions(conn,project,user)['can_manage']:
        raise AccessError(403, 'Only the project owner or an administrator can change project access')
    # Validate all requested grants before performing any mutation.
    chosen_teams = _validate_access_ids(conn, payload['team_ids'], 'team', project) if 'team_ids' in payload else None
    chosen_users = _validate_access_ids(conn, payload['user_ids'], 'user', project) if 'user_ids' in payload else None
    if {'name', 'scope_of_work', 'submission_deadline', 'builders'} & payload.keys() and not permissions(conn,project,user)['can_manage']:
        raise AccessError(403, 'Only the project creator or an administrator can change its brief')
    name=payload.get('name',project['name'])
    if not isinstance(name,str) or not name.strip() or len(name.strip())>500:raise ValueError('Project title must be 1–500 characters')
    name=name.strip()
    builders = stored_builders(payload, project)
    scope = payload.get('scope_of_work', project['scope_of_work'])
    if not isinstance(scope, str) or len(scope)>20000: raise ValueError('Scope of Work must be text of up to 20,000 characters')
    deadline = payload.get('submission_deadline', project['submission_deadline']) or None
    if deadline:
        try:
            if len(deadline)!=10 or date.fromisoformat(deadline).isoformat()!=deadline: raise ValueError()
        except (ValueError, TypeError): raise ValueError('Submission deadline must be a valid date') from None
    status = payload.get('status', project['status'])
    if status not in STATUSES: raise ValueError('Invalid project status')
    review_deadline = payload.get('review_deadline', project['review_deadline']) or None
    if review_deadline is not None:
        try:
            if not isinstance(review_deadline, str) or len(review_deadline) != 10 or date.fromisoformat(review_deadline).isoformat() != review_deadline:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('Review deadline must be a valid date') from None
    if status == 'in_review' and not review_deadline:
        raise ValueError('Choose a review deadline for In review')
    if status != 'in_review':
        review_deadline = None
    review_cycle = project['review_cycle']
    if status == 'in_review' and (project['status'] != 'in_review' or review_deadline != project['review_deadline']):
        review_cycle += 1

    award = payload.get('award_status', project['award_status'])
    if award not in ('', 'won', 'lost'):
        raise ValueError('Choose Won, Lost or leave the project result unset')
    if name != project['name']:
        conn.execute('UPDATE projects SET name=? WHERE id=?',(name,project_id))
        record_activity(conn,project_id,user,'Renamed project',f"{project['name']} → {name}")
    if builders != (project['client'] or ''):
        conn.execute('UPDATE projects SET client=? WHERE id=?', (builders, project_id))
        record_activity(conn, project_id, user, 'Updated project builders', builders or 'No builder assigned')
    if award != project['award_status']:
        conn.execute('UPDATE projects SET award_status=?,award_updated_at=? WHERE id=?', (award, utc_now(), project_id))
        record_activity(conn, project_id, user, 'Changed project result',
                        f"{project['award_status'] or 'Not recorded'} -> {award or 'Not recorded'}")
    if 'team_ids' in payload:
        ids = chosen_teams
        previous = {r[0] for r in conn.execute('SELECT team_id FROM project_teams WHERE project_id=?',(project_id,))}
        if ids != previous:
            conn.execute('DELETE FROM project_teams WHERE project_id=?', (project_id,))
            for team_id in sorted(ids):
                conn.execute('INSERT INTO project_teams VALUES (?,?,?,?)', (project_id,team_id,user['id'],utc_now()))
            names = [conn.execute('SELECT name FROM teams WHERE id=?',(i,)).fetchone()[0] for i in sorted(ids)]
            record_activity(conn,project_id,user,'Changed project teams',', '.join(names) or 'No team assigned')
    if chosen_users is not None:
        previous = {r[0] for r in conn.execute('SELECT user_id FROM project_user_access WHERE project_id=?', (project_id,))}
        if chosen_users != previous:
            conn.execute('DELETE FROM project_user_access WHERE project_id=?', (project_id,))
            for uid in sorted(chosen_users):
                conn.execute('INSERT INTO project_user_access VALUES (?,?,?,?)', (project_id,uid,user['id'],utc_now()))
            added = [conn.execute('SELECT name FROM users WHERE id=?',(uid,)).fetchone()[0] for uid in sorted(chosen_users-previous)]
            removed = [conn.execute('SELECT name FROM users WHERE id=?',(uid,)).fetchone()[0] for uid in sorted(previous-chosen_users)]
            detail = '; '.join(part for part in [('Added: '+', '.join(added)) if added else '', ('Removed: '+', '.join(removed)) if removed else ''] if part)
            record_activity(conn,project_id,user,'Changed individual project access',detail)
    if status != project['status']:
        record_activity(conn,project_id,user,'Changed project status',f"{project['status']} → {status}")
    if review_deadline != project['review_deadline'] or review_cycle != project['review_cycle']:
        record_activity(conn,project_id,user,'Updated review deadline', review_deadline or 'Review closed')
    if scope != project['scope_of_work'] or deadline != project['submission_deadline']:
        record_activity(conn,project_id,user,'Updated project brief',f"Submission deadline: {deadline or 'Not set'}")
    conn.execute('''UPDATE projects SET scope_of_work=?,submission_deadline=?,status=?,review_deadline=?,review_cycle=?
        WHERE id=?''',(scope.strip(),deadline,status,review_deadline,review_cycle,project_id))
    return decorate_project(conn,get_project(conn,project_id),user)


def user_directory(conn):
    return [public_user(row) for row in conn.execute('''SELECT u.*,t.name AS team_name FROM users u
        LEFT JOIN teams t ON t.id=u.team_id ORDER BY u.is_active DESC,u.name COLLATE NOCASE''')]


def project_contributors(conn, project_id):
    selection = 'a.project_id,' if project_id is None else ''
    condition = 'a.project_id IS NOT NULL' if project_id is None else 'a.project_id=?'
    grouping = 'a.project_id,' if project_id is None else ''
    return [dict(r) for r in conn.execute(f'''SELECT {selection}COALESCE(u.id,a.actor_id_snapshot) AS id,COALESCE(u.name,a.actor_name_snapshot,'Former user') AS name,COALESCE(u.username,a.actor_username_snapshot) AS username,COUNT(*) AS actions,
        MAX(a.created_at) AS last_activity,GROUP_CONCAT(DISTINCT a.team_name_snapshot) AS teams,
        MAX(CASE WHEN a.role_snapshot='admin' THEN 1 ELSE 0 END) AS admin_contribution
        FROM project_activity a LEFT JOIN users u ON u.id=a.user_id
        WHERE {condition} AND a.action IN ('Created project','Updated estimate settings','Added estimate item',
        'Updated estimate item','Removed estimate item','Saved manual estimate item','Changed project status',
        'Updated project brief','Updated project builders','Added project note','Changed project result','Updated review deadline') GROUP BY {grouping}COALESCE(u.id,a.actor_id_snapshot) ORDER BY actions DESC,name''',
        () if project_id is None else (project_id,))]
