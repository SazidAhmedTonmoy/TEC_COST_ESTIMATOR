"""Atomic opportunity-to-Tender handoff, including duplicate-submit protection."""
from __future__ import annotations

import json

from . import opportunities as op, tenders
from .builders import validate_builders


def _fields(db, payload, item, actor, teams):
    value = op._number(payload.get('value'), 'Electrical services submission value')
    if value is None:
        raise tenders.ValidationError('Enter the electrical services submission value. Zero is allowed.')
    note = tenders.text(payload.get('note'), 'Submission note', limit=4000)
    quote_no = tenders.text(payload.get('quoteNo'), 'Quote number', limit=200)
    submitted = tenders.date_value(payload.get('submittedDate'))
    if not submitted:
        # Replaying a request without a date on another day must still identify
        # the same already-recorded quote rather than silently create another.
        submitted = item.get('submittedDate') if item.get('quoteStatus') == 'quoted' else ''
        submitted = submitted or op._today(db, item['region']).isoformat()
    try:
        selected = validate_builders(payload.get('builders', item.get('builders', [])))
    except ValueError as exc:
        raise tenders.ValidationError(str(exc)) from None
    available = {tenders.builder_key(name): name for name in item.get('builders', [])}
    names = {}
    for name in selected:
        key = tenders.builder_key(name)
        if not key or key not in available:
            raise tenders.ValidationError('Select builders already on this opportunity. Edit the opportunity to add another builder first.')
        names.setdefault(key, available[key])
    if not names:
        raise tenders.ValidationError('Select at least one builder to receive this quote.')
    team_ids = {team['id'] for team in teams}
    if 'submittedByTeamId' in payload:
        team_id = payload['submittedByTeamId']
    elif item.get('quoteStatus') == 'quoted':
        team_id = item.get('submittedByTeamId')
    else:
        assigned = [identifier for identifier in item.get('assignedTeamIds', []) if identifier in team_ids]
        team_id = assigned[0] if len(assigned) == 1 else actor.get('team_id')
    if team_id is not None and (type(team_id) is not int or team_id not in team_ids):
        raise tenders.ValidationError('Choose an existing submission team or leave it unassigned.')
    return {'value': value, 'note': note, 'quoteNo': quote_no, 'submittedDate': submitted,
            'submittedByTeamId': team_id,
            'builders': [names[key] for key in sorted(names)]}


def _previous_fields(item):
    return {'value': item.get('quotedValue'), 'note': item.get('quoteNote', ''),
            'quoteNo': item.get('quoteNo', ''), 'submittedDate': item.get('submittedDate', ''),
            'submittedByTeamId': item.get('submittedByTeamId'),
            'builders': item.get('quotedBuilders', [])}


def quote(store, payload, user):
    op.initialize(store)
    teams, users = op.directory()
    actor = op._actor(user, users)
    identifier = op._identifier(payload.get('id'))
    # This transaction changes both workspaces. Its final generation increment
    # invalidates the Tender cache in every worker only when a quote is created.
    # An exact retry therefore performs no writes, including generation writes.
    with op._transaction(store) as db:
        item = op._find(db, identifier)
        op._require(item, actor, 'quote')
        if item['status'] != 'approved':
            raise tenders.ValidationError('Approve or assign a team to this opportunity before recording a quote.', 409)
        fields = _fields(db, payload, item, actor, teams)
        if item.get('quoteStatus') == 'quoted':
            ids = item.get('submissionIds', [])
            if fields != _previous_fields(item):
                raise tenders.ValidationError('This opportunity has already been quoted. Edit its existing submissions in Project Chase-up.', 409)
            if not ids or any(not db.execute('SELECT 1 FROM submissions WHERE id=?', (sid,)).fetchone() for sid in ids):
                raise tenders.ValidationError('A linked submission has been removed. Review this project in Project Chase-up before making further changes.', 409)
            # A retried original request may carry its pre-handoff revision.
            # The exact recorded payload is idempotent; nothing is overwritten.
            return {**op._detail(db, item, actor), 'submissionIds': ids,
                    'quoted': True, 'alreadyQuoted': True}
        op._revision(item, payload)

        project_key = tenders.project_key(item['project'])
        existing = [json.loads(row['body']) for row in db.execute('SELECT body FROM submissions')]
        if any(tenders.project_key(row.get('project')) == project_key for row in existing):
            # Normal Tender editing synchronises shared project fields across
            # builders. Do not let a conversion overwrite an unrelated group.
            raise tenders.ValidationError('This project already exists in Projects / Project Chase-up. Open that project and edit or add its builder submissions there; no existing data was changed.', 409)
        team_name = next((team['name'] for team in teams if team['id'] == fields['submittedByTeamId']), '')
        moment = tenders.timestamp()
        ids = []
        for builder in fields['builders']:
            result = store.save_submission({
                'project': item['project'], 'builder': builder, 'value': fields['value'],
                'status': 'Open', 'builderStatus': '', 'location': item.get('location', ''),
                'region': item['region'], 'due': item.get('due', ''),
                'contact': '', 'email': '', 'pricing': '', 'remarks': fields['note'],
                'quoteNo': fields['quoteNo'], 'submittedByTeam': team_name,
                '_actor_id': actor['id'], 'author': actor['name'],
            }, _db=db)
            sid = result['id']
            row = db.execute('SELECT body FROM submissions WHERE id=?', (sid,)).fetchone()
            submission = json.loads(row['body'])
            submission.update(
                opportunityId=item['id'], opportunityLink=item.get('link', ''),
                workingScope=item.get('workingScope', ''), opportunityRemarks=item.get('remarks', ''),
                submittedDate=fields['submittedDate'], submittedByTeamId=fields['submittedByTeamId'],
                quotedBy=actor['id'], quotedByName=actor['name'], quotedAt=moment,
            )
            db.execute('UPDATE submissions SET body=? WHERE id=?', (json.dumps(submission, ensure_ascii=False), sid))
            ids.append(sid)

        item.update(status='approved', quoteStatus='quoted', submissionIds=ids,
                    quotedValue=fields['value'], quoteNote=fields['note'], quoteNo=fields['quoteNo'],
                    submittedDate=fields['submittedDate'], submittedByTeamId=fields['submittedByTeamId'],
                    quotedBuilders=fields['builders'], quotedBy=actor['id'], quotedByName=actor['name'],
                    quotedAt=moment, updatedAt=moment, updatedBy=actor['id'],
                    updatedByName=actor['name'], revision=item['revision'] + 1)
        op._write(db, item)
        event = op._activity(store, db, actor, 'Quoted opportunity', item, {
            'submissionIds': ids, 'value': fields['value'], 'note': fields['note'],
            'quoteNo': fields['quoteNo'], 'submittedDate': fields['submittedDate'],
            'submittedByTeamId': fields['submittedByTeamId'], 'builders': fields['builders'],
        })
        op._notify(db, op._recipients(item, users), f'quoted:{event}', 'quoted', item,
                   f'{actor["name"]} recorded the electrical services quote. The project is now in Project Chase-up.')
        db.execute('UPDATE tender_generation SET value=value+1')
        return {**op._detail(db, item, actor), 'submissionIds': ids, 'quoted': True}
