"""Create and link a new Estimator project directly from an approved opportunity.

A single SQLite transaction writes both databases via ATTACH. This rolls back
ordinary request failures, while revision checking prevents duplicate requests.
As with all SQLite multi-database WAL transactions, a power loss can require
restoring a consistent backup. No new table, schema or tender quotation is created.
"""
from __future__ import annotations

from . import opportunities as op, tenders
from .database import connect as catalog_connection, write_lock
from .projects import create_project
from .workspace import register_project, update_workflow


def _source_notes(item):
    parts = [f'Tender Opportunity: {item["id"]}']
    for key, label in [('location', 'Location'), ('region', 'Region'),
                       ('category', 'Category'), ('budget', 'Overall project budget'),
                       ('link', 'Reference link'), ('remarks', 'Tender remarks')]:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f'{label}: {value.strip()}')
    if type(item.get('value')) in (int, float):
        parts.append(f'Estimated tender value (AUD): {item["value"]:,.2f}')
    if item.get('addedDate'):
        parts.append(f'Opportunity added: {item["addedDate"]}')
    if item.get('documentsAvailable') is not None:
        parts.append('Tender documents available: ' + ('Yes' if item['documentsAvailable'] else 'No'))
    if item.get('distanceKm') is not None:
        parts.append(f'Distance: {item["distanceKm"]} km')
    if item.get('distanceOrigin'):
        parts.append(f'Distance origin: {item["distanceOrigin"]}')
    return '\n'.join(parts)[:20000]


def create_estimate(store, payload, user):
    op.initialize(store)
    _, users = op.directory()
    actor = op._actor(user, users)
    identifier = op._identifier(payload.get('id'))
    # Lock serialises catalog writers. ATTACH lets normal SQLite rollback
    # cover the opportunity link, its audit and the new Estimator project.
    with write_lock:
        with catalog_connection() as db:
            db.execute('ATTACH DATABASE ? AS tender_link', (str(store.path),))
            db.execute('BEGIN IMMEDIATE')
            item = op._find(db, identifier)
            op._revision(item, payload)
            if item.get('status') != 'approved':
                raise tenders.ValidationError('Only an Approved opportunity can become an estimate.', 409)
            if item.get('estimatorProjectId'):
                raise tenders.ValidationError('This opportunity already has a linked Estimator project. Open the existing estimate instead.', 409)
            team_ids = item.get('assignedTeamIds') or []
            if not team_ids:
                raise tenders.ValidationError('Assign an approved team to this opportunity before creating its estimate.', 409)
            active_teams = {row['id'] for row in db.execute('SELECT id FROM teams')}
            if any(type(tid) is not int or tid not in active_teams for tid in team_ids):
                raise tenders.ValidationError('An assigned team no longer exists. Update the opportunity assignment first.', 409)
            if actor['role'] != 'admin' and not set(actor.get('team_ids') or []).intersection(team_ids):
                raise tenders.ValidationError('Only the assigned approved team or an administrator can create this estimate.', 403)
            # Copy server-held opportunity values, not client-supplied editable
            # details. This also works for already-expired Approved deadlines.
            name = str(item.get('project') or '').strip()
            if not name:
                raise tenders.ValidationError('This opportunity needs a project name before creating an estimate.', 409)
            project = create_project(db, {
                'name': name,
                'builders': item.get('builders') or [],
                'notes': _source_notes(item),
                'currency': 'AUD',
            })
            project_id = project['project']['id']
            register_project(db, project_id, actor)
            update_workflow(db, project_id, {
                'team_ids': sorted(set(team_ids)),
                'scope_of_work': str(item.get('workingScope') or '')[:20000],
                'submission_deadline': item.get('due') or None,
            }, actor)
            moment = tenders.timestamp()
            item.update(estimatorProjectId=project_id, revision=item['revision'] + 1,
                        updatedAt=moment, updatedBy=actor['id'], updatedByName=actor['name'])
            op._write(db, item)
            event = op._activity(store, db, actor, 'Created and linked Estimator project', item, {
                'estimatorProjectId': project_id, 'estimatorProjectName': name,
                'assignedTeamIds': sorted(set(team_ids)),
            })
            op._notify(db, op._recipients(item, users), f'estimate-created:{event}',
                       'updated', item, f'{actor["name"]} created and linked a new Estimator project.')
            db.commit()
    result = op.detail(store, identifier, user)
    result['createdEstimatorProjectId'] = project_id
    return result
