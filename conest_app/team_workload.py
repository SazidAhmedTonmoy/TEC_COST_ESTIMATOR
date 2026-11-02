"""Read-only per-person Estimator workload; team access is not personal assignment.

Counts are for OPEN Estimator projects, not Tender opportunities/submissions.
A project is attributed to its owner or a current explicit individual editor.
Team-wide sharing is reported separately rather than counted once per colleague.
"""
from collections import defaultdict
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo

from .accounts import AccessError

ACTIVE = ('draft', 'in_progress', 'in_review')


def workload(conn, actor, *, today=None, window_days=7):
    """Workload visible to the active user's team, or all teams for admins."""
    current = conn.execute('SELECT id,role,team_id,is_active FROM users WHERE id=?',
                           (actor['id'],)).fetchone()
    if not current or not current['is_active']:
        raise AccessError(403, 'An active account is required')
    today = today or datetime.now(ZoneInfo('Australia/Sydney')).date()
    if not isinstance(today, date) or not 1 <= window_days <= 30:
        raise ValueError('Invalid workload date range')
    last = today + timedelta(days=window_days)
    teams = [dict(row) for row in conn.execute(
        'SELECT id,name FROM teams ORDER BY name COLLATE NOCASE')]
    if current['role'] != 'admin':
        teams = [t for t in teams if t['id'] == current['team_id']]
    members = [dict(row) for row in conn.execute('''
        SELECT id,name,team_id FROM users WHERE role='user' AND is_active=1
        ORDER BY name COLLATE NOCASE,id''')]
    if current['role'] != 'admin':
        # An unassigned account has no team membership: never expose other
        # unaffiliated users' personal workload through the null team ID.
        if current['team_id'] is None:
            members = [m for m in members if m['id'] == current['id']]
        else:
            members = [m for m in members if m['team_id'] == current['team_id']]
    if any(m['team_id'] is None for m in members):
        teams.append({'id': None, 'name': 'No team'})
    allowed_ids = {m['id'] for m in members}
    by_team = defaultdict(list)
    for member in members:
        member.update(active_estimates=0, upcoming_deadlines=0, overdue_deadlines=0)
        by_team[member['team_id']].append(member)
    attribution = defaultdict(set)
    team_projects = defaultdict(set)
    for record in conn.execute('SELECT project_id,user_id FROM project_user_access'):
        if record['user_id'] in allowed_ids:
            attribution[record['project_id']].add(record['user_id'])
    team_ids = {t['id'] for t in teams if t['id'] is not None}
    for record in conn.execute('SELECT project_id,team_id FROM project_teams'):
        if record['team_id'] in team_ids:
            team_projects[record['project_id']].add(record['team_id'])
    member_index = {member['id']: member for member in members}
    members_of_team = {tid: {m['id'] for m in group} for tid,group in by_team.items()}
    per_team = {t['id']: {'id': t['id'], 'name': t['name'], 'members': by_team[t['id']],
                           'active_estimates': 0, 'shared_unassigned': 0} for t in teams}
    for project in conn.execute('''SELECT id,owner_id,status,submission_deadline,review_deadline
        FROM projects WHERE status IN ('draft','in_progress','in_review')'''):
        pid = project['id']
        owners = set(attribution.get(pid, ()))
        if project['owner_id'] in allowed_ids:
            owners.add(project['owner_id'])
        deadline = project['review_deadline'] if project['status'] == 'in_review' else project['submission_deadline']
        valid_deadline = bool(deadline and len(deadline) == 10)
        soon = valid_deadline and today.isoformat() <= deadline <= last.isoformat()
        overdue = valid_deadline and deadline < today.isoformat()
        for uid in owners:
            member_index[uid]['active_estimates'] += 1
            member_index[uid]['upcoming_deadlines'] += int(soon)
            member_index[uid]['overdue_deadlines'] += int(overdue)
        relevant_teams = set(team_projects.get(pid, ()))
        relevant_teams.update(member_index[uid]['team_id'] for uid in owners)
        for tid in relevant_teams:
            if tid in per_team:
                per_team[tid]['active_estimates'] += 1
                if tid in team_projects.get(pid, ()) and not owners.intersection(members_of_team.get(tid, ())):
                    per_team[tid]['shared_unassigned'] += 1
    return {'teams': list(per_team.values()), 'window_days': window_days,
            'as_of': today.isoformat(),
            'definition': 'Open Estimator projects assigned to the owner or named individual editor. Team-shared projects without a named colleague are counted separately.'}
