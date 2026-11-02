"""Read-only project journey from existing opportunity, Tender and Estimator records.

No duplicate project/quotation store and no lifecycle writes. Only an explicit
Estimator link is stored (on the opportunity JSON body); matching names are
never assumed to be links.
"""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from . import tenders
from .database import connect as catalog_connection

FINAL = {'won': 'Won', 'lost': 'Lost', 'closed': 'Closed', 'hold': 'Hold'}


def _linked_estimate(item):
    identifier = item.get('estimatorProjectId')
    if type(identifier) is not int or identifier < 1:
        return None
    with catalog_connection() as db:
        row = db.execute('SELECT id,name FROM projects WHERE id=?', (identifier,)).fetchone()
    return {'id': identifier, 'name': row['name'] if row else 'Previously linked estimate (no longer available)',
            'available': bool(row)}


def _linked_submissions(db, item):
    ids = list(dict.fromkeys(sid for sid in (item.get('submissionIds') or []) if isinstance(sid, str) and sid))[:150]
    if not ids:
        return []
    marks = ','.join('?' for _ in ids)
    result = []
    for row in db.execute('SELECT id,body FROM submissions WHERE id IN (' + marks + ')', ids):
        submission = json.loads(row['body'])
        if submission.get('opportunityId') not in (None, '', item['id']):
            continue
        result.append({**submission, 'id': row['id']})
    return sorted(result, key=lambda sub: sub['id'])


def _related(db, table, submissions):
    if not submissions:
        return []
    ids = [s['id'] for s in submissions]
    marks = ','.join('?' for _ in ids)
    results = []
    for row in db.execute('SELECT body FROM ' + table + ' WHERE submission_id IN (' + marks + ')', ids):
        try:
            record = json.loads(row['body'])
        except (TypeError, ValueError):
            continue
        if isinstance(record, dict):
            results.append(record)
    return results


def _outcome(submissions):
    if not submissions:
        return {'key': 'none', 'label': 'Not recorded', 'completed': False, 'detail': 'No Tender submission is linked yet.'}
    statuses = [str(s.get('status') or '').strip().lower() for s in submissions]
    final = [status for status in statuses if status in FINAL]
    if len(final) != len(statuses):
        recorded = len(final)
        return {'key': 'open', 'label': 'Awaiting outcome', 'completed': False,
                'detail': f'{recorded} of {len(statuses)} builder submissions have a recorded final outcome.'
                if recorded else 'Final quote outcome not recorded yet.'}
    distinct = set(final)
    if len(distinct) == 1:
        key = final[0]
        return {'key': key, 'label': FINAL[key], 'completed': True,
                'detail': f'{len(final)} builder submission(s) marked {FINAL[key]}.'}
    return {'key': 'mixed', 'label': 'Mixed outcomes', 'completed': True,
            'detail': 'Builder submissions have different final outcomes. Review them in Project Chase-up.'}


def _local_today(region):
    zone = 'Australia/Melbourne' if region == 'VIC' else 'Australia/Sydney'
    return datetime.now(ZoneInfo(zone)).strftime('%Y-%m-%dT%H:%M')


def build(db, item):
    """Build an accurate, bounded summary from the current linked submission IDs."""
    submissions = _linked_submissions(db, item)
    chases = _related(db, 'chases', submissions)
    reminders = _related(db, 'reminders', submissions)
    chases.sort(key=lambda c: (str(c.get('date') or ''), str(c.get('createdAt') or '')), reverse=True)
    pending = sorted((r for r in reminders if not r.get('done')), key=lambda r: str(r.get('due') or '9999'))
    overdue = [r for r in pending if str(r.get('due') or '')[:16] <= _local_today(item.get('region', 'NSW'))]
    outcome = _outcome(submissions)
    quoted = (item.get('quoteStatus') == 'quoted' or bool(item.get('linkedAt')) or bool(item.get('submissionIds')))
    submission_values = [s['value'] for s in submissions if type(s.get('value')) in (int, float)]
    quotation_value = item.get('quotedValue') if item.get('quotedValue') is not None else (max(submission_values) if submission_values else None)
    not_quoted = item.get('quoteStatus') == 'not_quoted'
    status = item.get('status', 'pending')
    if status == 'rejected':
        next_action = ('No quotation required', 'The opportunity was not pursued or was rejected.')
    elif status == 'expired':
        next_action = ('Review expired opportunity', 'Approve the opportunity or update its deadline before reconsidering.')
    elif status == 'review':
        next_action = ('Complete review', 'Approve or reject after reviewing scope, documents and team capacity.')
    elif status == 'pending':
        next_action = ('Make approval decision', 'Approve, reject or move the opportunity to In Review.')
    elif not quoted:
        next_action = ('Prepare and record a quote', 'Link an existing Tender project or record the submitted electrical quotation.')
    elif outcome['completed']:
        next_action = ('Outcome recorded', 'Review the final builder outcomes in Project Chase-up.')
    elif not submissions:
        next_action = ('Review missing submission', 'A quotation is recorded, but its Tender submission cannot be found.')
    elif overdue:
        next_action = ('Follow-up overdue', 'Open Project Chase-up to review and complete the outstanding reminder.')
    elif pending:
        next_action = ('Follow-up scheduled', 'View the next scheduled follow-up in Project Chase-up.')
    else:
        next_action = ('Schedule a follow-up', 'Contact the builder and schedule the next follow-up in Project Chase-up.')

    latest_chase = chases[0] if chases else None
    followup = pending[0] if pending else None
    linked_estimator = _linked_estimate(item)
    return {
        'position': next_action[0],
        'nextAction': {'title': next_action[0], 'description': next_action[1],
                       'submissionId': submissions[0]['id'] if submissions else None},
        'created': {'at': item.get('createdAt') or '', 'by': item.get('createdByName') or 'Imported source'},
        'decision': {'status': status, 'at': item.get('decisionAt') or '', 'by': item.get('decisionByName') or ''},
        'quotation': {'status': 'quoted' if quoted else 'not_quoted' if not_quoted else 'pending',
                      'value': quotation_value, 'quoteNo': item.get('quoteNo') or '',
                      'submittedDate': item.get('submittedDate') or '',
                      'linkedTenderName': item.get('linkedProjectName') or
                                          (submissions[0].get('project') if submissions else ''),
                      'submissionCount': len(submissions),
                      'missingSubmissions': bool(quoted and not submissions)},
        'chaseUp': {'started': bool(submissions), 'updates': len(chases),
                    'pendingReminders': len(pending), 'overdueReminders': len(overdue),
                    'latest': ({'date': latest_chase.get('date') or '',
                                'note': latest_chase.get('note') or '',
                                'method': latest_chase.get('method') or '',
                                'author': latest_chase.get('author') or ''}
                               if latest_chase else None),
                    'nextFollowUp': ({'due': followup.get('due') or '', 'note': followup.get('note') or ''}
                                     if followup else None)},
        'outcome': outcome, 'estimatorProject': linked_estimator,
    }


def estimator_choices(store, params, user):
    from . import opportunities as op
    op.initialize(store)
    actor = op._actor(user, op.directory()[1])
    with store.connect() as db:
        item = op._find(db, op._identifier(params.get('id')))
        op._require(item, actor, 'edit')
    query = tenders.text(params.get('q'), 'Estimate search', limit=200)
    with catalog_connection() as db:
        actor_row = db.execute('SELECT is_active FROM users WHERE id=?', (actor['id'],)).fetchone()
        if not actor_row or not actor_row['is_active']:
            raise tenders.ValidationError('An active account is required.', 403)
        rows = db.execute('SELECT id,name FROM projects WHERE name LIKE ? ESCAPE \'\\\' COLLATE NOCASE '
                          'ORDER BY updated_at DESC,id DESC LIMIT 50',
                          ('%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%',)).fetchall()
    return {'items': [{'id': row['id'], 'name': row['name']} for row in rows]}


def link_estimator(store, payload, user):
    from . import opportunities as op
    op.initialize(store)
    teams, users = op.directory()
    actor = op._actor(user, users)
    identifier = op._identifier(payload.get('id'))
    project_id = payload.get('estimatorProjectId')
    if project_id is not None and (type(project_id) is not int or project_id < 1):
        raise tenders.ValidationError('Choose a valid Estimator project or clear the existing link.')
    name = ''
    if project_id is not None:
        with catalog_connection() as catalog:
            row = catalog.execute('SELECT id,name FROM projects WHERE id=?', (project_id,)).fetchone()
            if not row:
                raise tenders.ValidationError('The selected Estimator project no longer exists.', 409)
            name = row['name']
    with op._transaction(store) as db:
        item = op._find(db, identifier)
        op._require(item, actor, 'edit')
        op._revision(item, payload)
        previous = item.get('estimatorProjectId')
        if previous == project_id:
            return op._detail(db, item, actor)
        moment = tenders.timestamp()
        if project_id is None:
            item.pop('estimatorProjectId', None)
        else:
            item['estimatorProjectId'] = project_id
        item.update(revision=item['revision'] + 1, updatedAt=moment,
                    updatedBy=actor['id'], updatedByName=actor['name'])
        op._write(db, item)
        action = 'Linked Estimator project' if project_id is not None else 'Unlinked Estimator project'
        event = op._activity(store, db, actor, action, item,
                             {'previousProjectId': previous, 'estimatorProjectId': project_id,
                              'estimatorProjectName': name})
        op._notify(db, op._recipients(item, users), f'estimate-link:{event}', 'updated', item,
                   f'{actor["name"]} {"linked an Estimator project" if project_id else "removed the Estimator project link"}.')
        return op._detail(db, item, actor)
