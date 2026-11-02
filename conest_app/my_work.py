"""Read-only, user-scoped action inbox for both TEC ConEst workspaces.

Derives actions from the existing Opportunity / Tender tables. It does not
create shadow workflow records and never trusts team identifiers from clients.
"""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import opportunities, tenders
from .opportunity_retention import active_sql


_FINAL_SUBMISSION_STATUSES = {'won', 'lost', 'close', 'closed'}


def _opportunity_scope(actor, users, scope):
    """Return parameterized SQL for the active user's personal or team work."""
    team_id = actor.get('team_id')
    if scope == 'team' and actor['role'] == 'admin' and team_id is None:
        return '1=1', []  # Explicit All teams switch, admin only.
    if scope == 'team':
        teammates = [u['id'] for u in users if u.get('teamId') == team_id]
        marks = ','.join('?' for _ in teammates)
        if not team_id or not teammates:
            return '0=1', []
        clause = ("(EXISTS (SELECT 1 FROM opportunity_people p WHERE p.opportunity_id=o.id "
                  "AND p.kind='assignedTeamIds' AND p.person_id=?) "
                  "OR EXISTS (SELECT 1 FROM opportunity_people p WHERE p.opportunity_id=o.id "
                  "AND p.kind='assignedUserIds' AND p.person_id IN (" + marks + ')) '
                  'OR o.created_by IN (' + marks + '))')
        return clause, [team_id, *teammates, *teammates]
    clause = ("(o.created_by=? OR EXISTS (SELECT 1 FROM opportunity_people p "
              "WHERE p.opportunity_id=o.id AND p.kind='assignedUserIds' AND p.person_id=?)")
    args = [actor['id'], actor['id']]
    if team_id is not None:
        clause += (" OR EXISTS (SELECT 1 FROM opportunity_people p WHERE p.opportunity_id=o.id "
                   "AND p.kind='assignedTeamIds' AND p.person_id=?)")
        args.append(team_id)
    return clause + ')', args


def _submission_in_scope(submission, actor, users, scope, scoped_opportunity_ids, team_name):
    # Every linked submission inherits the parent opportunity's responsibility.
    if submission.get('opportunityId') in scoped_opportunity_ids:
        return True
    if scope == 'team' and actor['role'] == 'admin' and actor.get('team_id') is None:
        return True
    if scope == 'team':
        creator_ids = {u['id'] for u in users if u.get('teamId') == actor.get('team_id')}
        return (submission.get('createdBy') in creator_ids or
                (actor.get('team_id') is not None and
                 (submission.get('submittedByTeamId') == actor['team_id'] or
                  bool(team_name and str(submission.get('submittedByTeam', '')).casefold() == team_name.casefold()))))
    return (submission.get('createdBy') == actor['id'] or
            (actor.get('team_id') is not None and
             (submission.get('submittedByTeamId') == actor['team_id'] or
              bool(team_name and str(submission.get('submittedByTeam', '')).casefold() == team_name.casefold()))))


def summary(store, user, scope='mine', now=None):
    """Return scoped counts and prioritized navigation targets, no mutations.

    'mine' = created by me, assigned directly to me, or assigned to my team.
    'team' = assigned to my team/teammates or created by a teammate. An admin
    without a team can deliberately choose an all-teams overview.
    """
    if scope not in ('mine', 'team'):
        raise tenders.ValidationError('Choose My Work or My Team.', 400)
    opportunities.initialize(store)
    teams, users = opportunities.directory()
    actor = opportunities._actor(user, users)
    moment = now or datetime.now(ZoneInfo('Australia/Sydney'))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo('Australia/Sydney'))
    moment = moment.astimezone(ZoneInfo('Australia/Sydney'))
    today = moment.date()
    team_id = actor.get('team_id')
    team_name = next((t['name'] for t in teams if t['id'] == team_id), '')
    team_available = team_id is not None or actor['role'] == 'admin'
    if scope == 'team' and not team_available:
        raise tenders.ValidationError('You are not assigned to a team.', 403)

    where, args = _opportunity_scope(actor, users, scope)
    with store.connect() as db:
        rows = db.execute('''SELECT o.body,o.created_by,o.revision FROM opportunities o
            WHERE o.deleted_at IS NULL AND ''' + active_sql('opportunity', 'o.id') +
            ' AND ' + where, args).fetchall()
        reminder_rows = db.execute('''SELECT r.body AS reminder_body,s.body AS submission_body
            FROM reminders r JOIN submissions s ON s.id=r.submission_id''').fetchall()

    scoped_ids = set()
    metrics = {'needsApproval': 0, 'needsQuote': 0, 'dueSoon': 0, 'followUpsDue': 0}
    actions = []
    for row in rows:
        item = opportunities._decode_opportunity(row)
        scoped_ids.add(item['id'])
        status = item.get('status', '')
        if status not in ('pending', 'review', 'approved'):
            continue
        quoted = opportunities._is_quoted(item) or bool(item.get('linkedAt'))
        needs_quote = status == 'approved' and not quoted
        can_approve = opportunities.permissions(item, actor)['approve']
        due = str(item.get('due') or '')[:10]
        days = None
        if due:
            try:
                days = (datetime.strptime(due, '%Y-%m-%d').date() - today).days
            except ValueError:
                pass
        active_deadline = status in ('pending', 'review') or needs_quote
        urgency = active_deadline and days is not None and 0 <= days <= 3
        if status == 'pending' and can_approve:
            metrics['needsApproval'] += 1
        if needs_quote:
            metrics['needsQuote'] += 1
        if urgency:
            metrics['dueSoon'] += 1
        # One actionable row per opportunity. Urgency overrides a generic task.
        if urgency:
            title = 'Deadline today' if days == 0 else 'Deadline approaching'
            priority = (1, days)
        elif status == 'pending' and can_approve:
            title, priority = 'Review approval', (2, 0)
        elif status == 'review':
            title, priority = 'Review opportunity', (3, 0)
        elif needs_quote:
            title, priority = 'Prepare quotation', (4, 0)
        else:
            continue
        actions.append({'kind': 'opportunity', 'id': item['id'], 'title': title,
                        'project': item.get('project', 'Untitled opportunity'),
                        'status': status, 'due': due, 'daysLeft': days,
                        'team': team_name if scope == 'team' else '',
                        '_priority': priority})

    for row in reminder_rows:
        try:
            reminder = json.loads(row['reminder_body'])
            submission = json.loads(row['submission_body'])
        except (TypeError, ValueError):
            continue
        if reminder.get('done') or not _submission_in_scope(submission, actor, users, scope,
                                                              scoped_ids, team_name):
            continue
        if str(submission.get('status', '')).strip().casefold() in _FINAL_SUBMISSION_STATUSES:
            continue
        due = str(reminder.get('due') or '')
        if not due or due[:16] > moment.strftime('%Y-%m-%dT%H:%M'):
            continue
        metrics['followUpsDue'] += 1
        actions.append({'kind': 'chase', 'id': submission.get('id') or reminder.get('submissionId'),
                        'title': 'Follow-up due',
                        'project': submission.get('project', 'Tender submission'),
                        'status': 'follow-up', 'due': due,
                        'detail': str(reminder.get('note') or submission.get('builder') or '')[:180],
                        '_priority': (0, due)})

    # Stable priorities, earliest first within each priority, bounded payload.
    actions.sort(key=lambda item: (item['_priority'], str(item.get('due') or ''), str(item['id'])))
    for item in actions:
        item.pop('_priority', None)
    return {'scope': scope, 'teamAvailable': team_available,
            'scopeLabel': ('My work' if scope == 'mine' else
                           ('All teams' if not team_id else team_name)),
            'asOf': moment.isoformat(), 'counts': metrics,
            'actions': actions[:8], 'actionCount': len(actions)}
