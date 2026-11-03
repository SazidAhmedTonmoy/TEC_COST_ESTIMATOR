"""Administrator-only, deadline-period team overview across Tender and Estimator.

No individual names, user details or unbounded history are returned. The chosen
week/month covers closing deadlines for opportunities and the applicable
submission/review deadline for estimates. Each shared project counts for every
team explicitly assigned to it, not for every team member.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .accounts import AccessError
from .database import connect
from .opportunity_retention import active_sql
from . import tenders


def period_dates(mode, value, *, today=None):
    """Return inclusive ISO date bounds; reject noncanonical periods."""
    current = today or datetime.now(ZoneInfo('Australia/Sydney')).date()
    if mode not in ('week', 'month'):
        raise ValueError('Choose week or month.')
    if not value:
        if mode == 'month':
            value = current.strftime('%Y-%m')
        else:
            iso = current.isocalendar()
            value = f'{iso.year:04d}-W{iso.week:02d}'
    if not isinstance(value, str):
        raise ValueError('Choose a valid week or month.')
    if mode == 'month':
        if not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', value):
            raise ValueError('Choose a valid month in YYYY-MM format.')
        year, month = (int(part) for part in value.split('-'))
        first = date(year, month, 1)
        following = date(year + (month == 12), (month % 12) + 1, 1)
        last = following - timedelta(days=1)
        label = first.strftime('%B %Y')
    else:
        if not re.fullmatch(r'20\d{2}-W(0[1-9]|[1-4][0-9]|5[0-3])', value):
            raise ValueError('Choose a valid ISO week in YYYY-Www format.')
        year, week = int(value[:4]), int(value[6:])
        try:
            first = date.fromisocalendar(year, week, 1)
        except ValueError:
            raise ValueError('That ISO week does not exist.') from None
        last = first + timedelta(days=6)
        label = f'Week {week} · {first.strftime("%d %b")}–{last.strftime("%d %b %Y")}'
    return {'mode': mode, 'period': value, 'start': first.isoformat(),
            'end': last.isoformat(), 'label': label}


def summary(user, *, mode='month', period='', store=None, today=None):
    """Read-only admin view; validate role from current account DB, not session."""
    window = period_dates(mode, period, today=today)
    with connect() as conn:
        current = conn.execute('SELECT role,is_active FROM users WHERE id=?', (user.get('id'),)).fetchone()
        if not current or not current['is_active'] or current['role'] != 'admin':
            raise AccessError(403, 'Administrator access is required for team summary.')
        rows = [dict(r) for r in conn.execute('SELECT id,name FROM teams ORDER BY name COLLATE NOCASE')]
        totals = {r['id']: {**r, 'assigned_opportunities': 0, 'estimates_in_progress': 0,
                            'estimates_done': 0} for r in rows}
        active = ('draft', 'in_progress', 'in_review')
        done = ('submitted', 'closed')
        # Estimator: unique per project/team. The review due date supersedes the
        # submission due date while a project is actually In Review.
        for row in conn.execute('''SELECT pt.team_id, p.status, COUNT(DISTINCT p.id) AS count
            FROM project_teams pt JOIN projects p ON p.id=pt.project_id
            WHERE (CASE WHEN p.status='in_review' THEN p.review_deadline
                        ELSE p.submission_deadline END) BETWEEN ? AND ?
              AND p.status IN ('draft','in_progress','in_review','submitted','closed')
            GROUP BY pt.team_id,p.status''', (window['start'], window['end'])):
            entry = totals.get(row['team_id'])
            if entry is not None:
                entry['estimates_in_progress' if row['status'] in active else 'estimates_done'] += row['count']
        unassigned_estimates = conn.execute('''SELECT COUNT(*) FROM projects p
            WHERE p.status IN ('draft','in_progress','in_review','submitted','closed')
              AND (CASE WHEN p.status='in_review' THEN p.review_deadline ELSE p.submission_deadline END)
                 BETWEEN ? AND ?
              AND NOT EXISTS(SELECT 1 FROM project_teams pt WHERE pt.project_id=p.id)''',
            (window['start'], window['end'])).fetchone()[0]
    store = store or tenders.get_store()
    from .opportunities import initialize
    initialize(store)
    with store.connect() as conn:
        for row in conn.execute('''SELECT p.person_id AS team_id, COUNT(DISTINCT o.id) AS count
            FROM opportunity_people p JOIN opportunities o ON o.id=p.opportunity_id
            WHERE p.kind='assignedTeamIds' AND o.status IN ('pending','review','approved')
              AND o.deleted_at IS NULL AND o.due BETWEEN ? AND ? AND ''' +
            active_sql('opportunity', 'o.id') + ''' GROUP BY p.person_id''',
            (window['start'], window['end'])):
            if row['team_id'] in totals:
                totals[row['team_id']]['assigned_opportunities'] = row['count']
        unassigned_opportunities = conn.execute('''SELECT COUNT(*) FROM opportunities o
            WHERE o.status IN ('pending','review','approved') AND o.deleted_at IS NULL
              AND o.due BETWEEN ? AND ? AND ''' + active_sql('opportunity', 'o.id') + '''
              AND NOT EXISTS (SELECT 1 FROM opportunity_people p
                WHERE p.opportunity_id=o.id AND p.kind='assignedTeamIds')''',
            (window['start'], window['end'])).fetchone()[0]
    return {'teams': list(totals.values()), 'window': window,
            'unassigned_opportunities': unassigned_opportunities,
            'unassigned_estimates': unassigned_estimates,
            'definition': 'Counts use the selected closing/submission/review deadline. In progress = Not started, In progress or In review. Done = Submitted or Closed. Each project assigned to two teams counts once in each.'}
