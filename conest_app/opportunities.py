"""Opportunity workflow, audit history and per-person Tender notifications.

Opportunity data lives with tenders; account/team membership is resolved live
from the Estimator database. Every change is authorized inside the server and
uses an optimistic revision inside one SQLite write transaction.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from . import tenders
from .database import connect as account_connection

DEFAULT_REGIONS = {
    'NSW': ('63-79 Parramatta Rd Silverwater, NSW 2128', 'Australia/Sydney'),
    'VIC': ('CBD, Melbourne', 'Australia/Melbourne'),
}
STATUSES = ('pending', 'approved', 'rejected', 'expired')
AUTHORITY_FIELDS = ('assignedTeamIds', 'assignedUserIds', 'editorTeamIds', 'editorUserIds')
SYSTEM = {'id': 0, 'name': 'System', 'role': 'system', 'team_id': None}
_initialization_lock = threading.RLock()


def initialize(store):
    if getattr(store, '_opportunities_ready', False):
        return
    with _initialization_lock:
        if getattr(store, '_opportunities_ready', False):
            return
        from .opportunity_schema import initialize as initialize_schema
        initialize_schema(store, DEFAULT_REGIONS)
        store._opportunity_sweep_lock = threading.Lock()
        store._opportunity_sweep_at = 0
        store._opportunities_ready = True


@contextmanager
def _transaction(store):
    # Opportunity activity does not alter tender submissions. Keeping its writes
    # separate avoids discarding the tender dataset cache on every inbox read.
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        yield db


def generation(store):
    initialize(store)
    with store.connect() as db:
        return db.execute('SELECT value FROM opportunity_generation').fetchone()[0]


def directory():
    """Safe directory fields only; membership/role is never trusted from a form."""
    with account_connection() as db:
        teams = [dict(r) for r in db.execute('SELECT id,name FROM teams ORDER BY name COLLATE NOCASE')]
        users = [dict(r) for r in db.execute('''SELECT id,name,team_id AS teamId,role
            FROM users WHERE is_active=1 ORDER BY name COLLATE NOCASE''')]
    return teams, users


def _actor(user, users):
    found = next((u for u in users if u['id'] == user.get('id')), None)
    if not found:
        raise tenders.ValidationError('Your account is no longer active. Sign in again.', 403)
    return {**found, 'team_id': found['teamId']}


def permissions(item, actor):
    manage = actor['role'] == 'admin' or item.get('createdBy') == actor['id']
    edit = manage or actor['id'] in item.get('editorUserIds', []) or (
        actor.get('team_id') is not None and actor['team_id'] in item.get('editorTeamIds', []))
    return {'edit': bool(edit), 'manage': bool(manage),
            'approve': bool(actor['role'] == 'admin' or actor.get('team_id') is not None)}


def _require(item, actor, permission):
    if not permissions(item, actor)[permission]:
        messages = {
            'manage': 'Only the creator or an administrator can assign, delete, or manage access.',
            'edit': 'Only the creator, an administrator, or an authorised editor can edit this opportunity.',
            'approve': 'An administrator or a user who belongs to a team must make this decision.',
        }
        raise tenders.ValidationError(messages[permission], 403)


def _identifier(value, label='Opportunity ID'):
    return tenders.text(value, label, required=True, limit=100)


def _find(db, identifier, include_deleted=False):
    row = db.execute('SELECT * FROM opportunities WHERE id=?', (identifier,)).fetchone()
    if not row or (row['deleted_at'] and not include_deleted):
        raise tenders.ValidationError('This opportunity no longer exists.', 404)
    return {**json.loads(row['body']), 'revision': row['revision']}


def _revision(item, payload):
    if type(payload.get('revision')) is not int or item['revision'] != payload['revision']:
        raise tenders.ValidationError('This opportunity changed in another window. Reopen it before saving.', 409)


def _number(value, label):
    if value in ('', None):
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or value > 1e15:
        raise tenders.ValidationError(f'{label} must be a valid non-negative number or left blank.')
    return value


def _ids(value, label, valid):
    if not isinstance(value, list) or len(value) > 1000 or any(type(v) is not int for v in value):
        raise tenders.ValidationError(f'Choose valid {label}.')
    if set(value) - valid:
        raise tenders.ValidationError(f'One or more {label} no longer exist. Refresh and choose again.')
    return sorted(set(value))


def _region_code(value):
    value = tenders.text(value, 'Region', required=True, limit=50).upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9 ._-]{0,49}', value):
        raise tenders.ValidationError('Use letters, numbers, spaces or hyphens for the region.')
    return value


def _today(db, region, now=None):
    row = db.execute('SELECT timezone FROM opportunity_regions WHERE code=?', (region,)).fetchone()
    zone = ZoneInfo(row[0] if row else 'Australia/Sydney')
    return (now or datetime.now(timezone.utc)).astimezone(zone).date()


def _normalise(db, payload, current=None):
    base = dict(current or {})
    base.update({k: v for k, v in payload.items() if k not in ('sourceData',)})
    fields = {
        'project': tenders.text(base.get('project'), 'Project name', required=True, limit=500),
        'region': _region_code(base.get('region') or 'NSW'),
        'location': tenders.text(base.get('location'), 'Location', limit=1000),
        'workingScope': tenders.text(base.get('workingScope'), 'Working scope', limit=20000),
        'remarks': tenders.text(base.get('remarks'), 'Notes', limit=20000),
        'contact': tenders.text(base.get('contact'), 'Contact', limit=500),
        'email': tenders.text(base.get('email'), 'Email', limit=254),
        'category': tenders.text(base.get('category'), 'Category', limit=500),
        'budget': tenders.text(base.get('budget'), 'Budget', limit=500),
        'addedDate': tenders.date_value(base.get('addedDate')),
        'due': tenders.date_value(base.get('due')),
        'value': _number(base.get('value'), 'Tender value'),
        'distanceKm': _number(base.get('distanceKm'), 'Distance'),
    }
    if fields['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', fields['email']):
        raise tenders.ValidationError('Enter a valid email address or leave Email blank.')
    from .builders import validate_builders
    try:
        fields['builders'] = validate_builders(base.get('builders', []))
    except ValueError as exc:
        raise tenders.ValidationError(str(exc)) from None
    origin = tenders.text(base.get('distanceOrigin'), 'Distance origin', limit=1000)
    row = db.execute('SELECT origin FROM opportunity_regions WHERE code=?', (fields['region'],)).fetchone()
    if row:
        if current and current.get('region') != fields['region'] and 'distanceOrigin' not in payload:
            origin = ''
        fields['distanceOrigin'] = origin or row['origin']
    else:
        if not origin:
            raise tenders.ValidationError('Enter the distance origin for this new region.')
        fields['distanceOrigin'] = origin
    if fields['distanceKm'] is not None and current and (
        current.get('location') != fields['location'] or current.get('distanceOrigin') != fields['distanceOrigin']
    ) and 'distanceKm' not in payload:
        fields['distanceKm'] = None
    return fields


def _register_directory(db, item):
    db.execute('INSERT OR IGNORE INTO opportunity_regions(code,origin) VALUES(?,?)',
               (item['region'], item['distanceOrigin']))
    for name in item['builders']:
        key = tenders.builder_key(name)
        if key:
            db.execute('INSERT OR IGNORE INTO opportunity_builders(builder_key,name) VALUES(?,?)', (key, name))


def _write(db, item, new=False):
    _register_directory(db, item)
    values = (json.dumps(item, ensure_ascii=False), item['revision'], item['status'], item['region'],
              item['due'], tenders.project_key(item['project']), item.get('createdBy'),
              item.get('deletedAt'), item['updatedAt'])
    if new:
        db.execute('INSERT INTO opportunities(id,body,revision,status,region,due,project_key,created_by,deleted_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (item['id'], *values))
    else:
        db.execute('UPDATE opportunities SET body=?,revision=?,status=?,region=?,due=?,project_key=?,created_by=?,deleted_at=?,updated_at=? WHERE id=?',
                   (*values, item['id']))
    db.execute('DELETE FROM opportunity_people WHERE opportunity_id=?', (item['id'],))
    for kind in AUTHORITY_FIELDS:
        db.executemany('INSERT INTO opportunity_people(opportunity_id,kind,person_id) VALUES(?,?,?)',
                       [(item['id'], kind, uid) for uid in item.get(kind, [])])
    db.execute('UPDATE opportunity_generation SET value=value+1')


def _activity(store, db, actor, action, item, details=None, timestamp=None):
    details = {'opportunityId': item['id'], **(details or {})}
    moment = timestamp or tenders.timestamp()
    cursor = db.execute('''INSERT INTO opportunity_activity
        (opportunity_id,actor_id,actor_name,project,action,details,created_at)
        VALUES(?,?,?,?,?,?,?)''', (item['id'], actor['id'], actor['name'], item['project'], action,
                                 json.dumps(details, ensure_ascii=False), moment))
    # Keep existing contribution integrations working. Consumers with a separate
    # opportunity panel can exclude details.opportunityId to avoid double counting.
    store.activity(db, actor['id'], actor['name'], action,
                   {'project': item['project']}, details)
    return cursor.lastrowid


def _recipients(item, users, include_admin=True):
    individual = set(item.get('assignedUserIds', [])) | set(item.get('editorUserIds', []))
    individual.add(item.get('createdBy'))
    teams = set(item.get('assignedTeamIds', [])) | set(item.get('editorTeamIds', []))
    return {u['id'] for u in users if u['id'] in individual or u['teamId'] in teams
            or (include_admin and u['role'] == 'admin')}


def _notify(db, recipient_ids, event_key, kind, item, message, created_at=None):
    moment = created_at or tenders.timestamp()
    for uid in recipient_ids:
        db.execute('''INSERT OR IGNORE INTO tender_notifications
            (id,user_id,kind,target_kind,target_id,title,message,due,created_at,event_key)
            VALUES(?,?,?,?,?,?,?,?,?,?)''', (str(uuid.uuid4()), uid, kind, 'opportunity', item['id'],
                item['project'], message, item.get('due', ''), moment, event_key))


def _new_item(db, fields, actor):
    now = tenders.timestamp()
    return {**fields, 'id': str(uuid.uuid4()), 'revision': 0, 'status': 'pending',
            'createdBy': actor['id'] or None, 'createdByName': actor['name'],
            'createdAt': now, 'updatedAt': now, 'updatedBy': actor['id'] or None,
            'updatedByName': actor['name'], 'decisionBy': None, 'decisionByName': '',
            'decisionAt': '', 'decisionReason': '',
            **{kind: [] for kind in AUTHORITY_FIELDS}}


def _authority(payload, current, actor, teams, users):
    result = {}
    manage = permissions(current, actor)['manage']
    for field in AUTHORITY_FIELDS:
        if field not in payload:
            result[field] = current.get(field, [])
            continue
        valid = {x['id'] for x in (teams if 'Team' in field else users)}
        ids = _ids(payload[field], 'teams' if 'Team' in field else 'people', valid)
        if ids != current.get(field, []) and not manage:
            raise tenders.ValidationError('Only the creator or an administrator can change assignments or editor access.', 403)
        result[field] = ids
    return result


def _assignment_events(store, db, actor, before, item, users):
    assigned = {key: item[key] for key in AUTHORITY_FIELDS[:2] if before.get(key, []) != item[key]}
    access = {key: item[key] for key in AUTHORITY_FIELDS[2:] if before.get(key, []) != item[key]}
    if assigned:
        event = _activity(store, db, actor, 'Assigned opportunity', item,
                          {'before': {k: before.get(k, []) for k in assigned}, 'after': assigned})
        recipients = _recipients(item, users) | _recipients(before, users)
        _notify(db, recipients, f'assignment:{event}', 'assignment', item,
                f'{actor["name"]} updated the team or person assigned to this opportunity.')
    if access:
        event = _activity(store, db, actor, 'Updated opportunity access', item,
                          {'before': {k: before.get(k, []) for k in access}, 'after': access})
        _notify(db, _recipients(item, users) | _recipients(before, users), f'access:{event}', 'access', item,
                f'{actor["name"]} updated who can edit this opportunity.')


def save(store, payload, user):
    initialize(store)
    teams, users = directory()
    actor = _actor(user, users)
    identifier = tenders.text(payload.get('id'), 'Opportunity ID', limit=100)
    with _transaction(store) as db:
        if identifier:
            before = _find(db, identifier)
            _require(before, actor, 'edit')
            _revision(before, payload)
            fields = _normalise(db, payload, before)
            item = {**before, **fields}
        else:
            fields = _normalise(db, payload)
            before = {}
            item = _new_item(db, fields, actor)
        item.update(_authority(payload, item, actor, teams, users))
        changed = {k: item.get(k) for k in fields if before.get(k) != item.get(k)}
        authority_changed = any(before.get(k, []) != item[k] for k in AUTHORITY_FIELDS)
        if identifier and not changed and not authority_changed:
            return _detail(db, item, actor)
        moment = tenders.timestamp()
        item.update(updatedAt=moment, updatedBy=actor['id'], updatedByName=actor['name'])
        if identifier:
            item['revision'] += 1
        expired = bool(item['due'] and date.fromisoformat(item['due']) < _today(db, item['region']))
        if item['status'] == 'expired' and not expired:
            item.update(status='pending', decisionBy=None, decisionByName='', decisionAt='', decisionReason='')
            _activity(store, db, actor, 'Reopened opportunity', item, {'reason': 'Deadline extended'})
        elif item['status'] in ('pending', 'approved') and expired:
            item['status'] = 'expired'
        _write(db, item, new=not identifier)
        if changed or not identifier:
            action = 'Updated opportunity' if identifier else 'Created opportunity'
            event = _activity(store, db, actor, action, item,
                              {'before': {k: before.get(k) for k in changed}, 'after': changed})
            creation = 'added an opportunity awaiting approval' if item['status'] == 'pending' else 'added an expired opportunity'
            _notify(db, _recipients(item, users), f'change:{event}', 'updated' if identifier else 'created', item,
                    f'{actor["name"]} {"updated this opportunity" if identifier else creation}.')
        _assignment_events(store, db, actor, before, item, users)
        if item['status'] == 'expired' and before.get('status') != 'expired':
            _record_time_event(store, db, item, users, 'expired', 'Expired opportunity',
                               'The deadline has passed. This opportunity is now expired.')
        return _detail(db, item, actor)


def update_authority(store, payload, user, kind):
    allowed = AUTHORITY_FIELDS[:2] if kind == 'assign' else AUTHORITY_FIELDS[2:]
    initialize(store)
    teams, users = directory()
    actor = _actor(user, users)
    identifier = _identifier(payload.get('id'))
    with _transaction(store) as db:
        before = _find(db, identifier)
        _require(before, actor, 'manage')
        _revision(before, payload)
        if any(k in payload and payload[k] != before.get(k, []) for k in AUTHORITY_FIELDS if k not in allowed):
            raise tenders.ValidationError('Use the appropriate assignment or access action.')
        item = {**before, **_authority(payload, before, actor, teams, users)}
        if all(item[k] == before.get(k, []) for k in AUTHORITY_FIELDS):
            return _detail(db, item, actor)
        item.update(revision=item['revision'] + 1, updatedAt=tenders.timestamp(),
                    updatedBy=actor['id'], updatedByName=actor['name'])
        _write(db, item)
        _assignment_events(store, db, actor, before, item, users)
        return _detail(db, item, actor)


def decide(store, payload, user):
    initialize(store)
    _, users = directory()
    actor = _actor(user, users)
    identifier = _identifier(payload.get('id'))
    decision = payload.get('decision')
    if decision not in ('pending', 'approved', 'rejected'):
        raise tenders.ValidationError('Choose Approve, Reject, or Request approval.')
    reason = tenders.text(payload.get('reason'), 'Decision note', limit=4000)
    if decision == 'rejected' and not reason:
        raise tenders.ValidationError('Please explain why this opportunity was rejected.')
    with _transaction(store) as db:
        item = _find(db, identifier)
        _require(item, actor, 'manage' if decision == 'pending' else 'approve')
        _revision(item, payload)
        if item['due'] and date.fromisoformat(item['due']) < _today(db, item['region']):
            raise tenders.ValidationError('The deadline has passed. Extend the deadline before requesting or granting approval.', 409)
        if decision in ('approved', 'rejected') and item['status'] != 'pending':
            raise tenders.ValidationError('Only opportunities awaiting approval can be approved or rejected.', 409)
        if decision == 'pending' and item['status'] == 'pending':
            return _detail(db, item, actor)
        before = item['status']
        moment = tenders.timestamp()
        item.update(status=decision, revision=item['revision'] + 1, updatedAt=moment,
                    updatedBy=actor['id'], updatedByName=actor['name'],
                    decisionBy=actor['id'] if decision != 'pending' else None,
                    decisionByName=actor['name'] if decision != 'pending' else '',
                    decisionAt=moment if decision != 'pending' else '', decisionReason=reason)
        _write(db, item)
        action = {'approved': 'Approved opportunity', 'rejected': 'Rejected opportunity',
                  'pending': 'Requested opportunity approval'}[decision]
        event = _activity(store, db, actor, action, item, {'before': before, 'after': decision, 'reason': reason})
        message = f'{actor["name"]} {"requested approval for" if decision == "pending" else decision} this opportunity.'
        if reason:
            message += ' ' + reason
        _notify(db, _recipients(item, users), f'decision:{event}', decision, item, message)
        return _detail(db, item, actor)


def delete(store, payload, user):
    initialize(store)
    _, users = directory()
    actor = _actor(user, users)
    identifier = _identifier(payload.get('id'))
    with _transaction(store) as db:
        item = _find(db, identifier)
        _require(item, actor, 'manage')
        _revision(item, payload)
        moment = tenders.timestamp()
        item.update(deletedAt=moment, updatedAt=moment, updatedBy=actor['id'],
                    updatedByName=actor['name'], revision=item['revision'] + 1)
        _write(db, item)
        event = _activity(store, db, actor, 'Deleted opportunity', item,
                          {'snapshot': {k: v for k, v in item.items() if k != 'sourceData'}})
        _notify(db, _recipients(item, users), f'deleted:{event}', 'deleted', item,
                f'{actor["name"]} deleted this opportunity. The audit record has been retained.')
    return {'ok': True, 'id': identifier}


def _public(item, actor):
    return {**item, 'permissions': permissions(item, actor)}


def _detail(db, item, actor):
    return {'opportunity': _public(item, actor), **_activity_page(db, item['id'])}


def _activity_page(db, identifier, before=None, limit=200):
    clause = 'opportunity_id=?'
    args = [identifier]
    if before not in (None, ''):
        try:
            cursor = int(before)
        except (ValueError, TypeError):
            raise tenders.ValidationError('Invalid activity cursor.') from None
        if cursor < 1:
            raise tenders.ValidationError('Invalid activity cursor.')
        clause += ' AND id<?'
        args.append(cursor)
    size = _page(limit, 100, 200)
    rows = db.execute('''SELECT id,actor_id AS actorId,actor_name AS actorName,action,details,
        created_at AS createdAt FROM opportunity_activity WHERE ''' + clause +
        ' ORDER BY id DESC LIMIT ?', (*args, size + 1)).fetchall()
    total = db.execute('SELECT COUNT(*) FROM opportunity_activity WHERE opportunity_id=?', (identifier,)).fetchone()[0]
    has_more = len(rows) > size
    rows = rows[:size]
    return {'activity': [{**dict(r), 'details': json.loads(r['details'])} for r in rows],
            'activityTotal': total, 'total': total, 'hasMoreActivity': has_more,
            'nextActivityCursor': rows[-1]['id'] if has_more and rows else None}


def activity_history(store, params, user):
    initialize(store)
    _, users = directory()
    actor = _actor(user, users)
    with store.connect() as db:
        db.execute('BEGIN')
        item = _find(db, _identifier(params.get('id')), include_deleted=True)
        if item.get('deletedAt'):
            _require(item, actor, 'manage')
        return _activity_page(db, item['id'], params.get('before'), params.get('limit', 100))


def detail(store, identifier, user):
    initialize(store)
    process_due(store)
    _, users = directory()
    actor = _actor(user, users)
    with store.connect() as db:
        item = _find(db, _identifier(identifier), include_deleted=True)
        if item.get('deletedAt'):
            _require(item, actor, 'manage')
        return _detail(db, item, actor)


def _page(value, default, maximum):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(1, min(maximum, value))


def _query(filters, include_status=True, users=None):
    where = ['o.deleted_at IS NULL']
    args = []
    status = filters.get('status', '')
    if include_status and status and status != 'all':
        if status not in STATUSES:
            raise tenders.ValidationError('Choose a valid opportunity status.')
        where.append('o.status=?')
        args.append(status)
    region = filters.get('region', '')
    if region and region != 'all':
        where.append('o.region=?')
        args.append(_region_code(region))
    team = filters.get('teamId', '')
    if team == 'unassigned':
        where.append("NOT EXISTS(SELECT 1 FROM opportunity_people p WHERE p.opportunity_id=o.id AND p.kind='assignedTeamIds')")
    elif team and team != 'all':
        if not str(team).isdigit():
            raise tenders.ValidationError('Choose a valid team.')
        where.append("EXISTS(SELECT 1 FROM opportunity_people p WHERE p.opportunity_id=o.id AND p.kind='assignedTeamIds' AND p.person_id=?)")
        args.append(int(team))
    person = filters.get('userId', '')
    if person and person != 'all':
        if not str(person).isdigit():
            raise tenders.ValidationError('Choose a valid person.')
        if users is None:
            _, users = directory()
        selected = next((u for u in users if u['id'] == int(person)), None)
        selected_team = selected['teamId'] if selected else None
        where.append("EXISTS(SELECT 1 FROM opportunity_people p WHERE p.opportunity_id=o.id AND ((p.kind='assignedUserIds' AND p.person_id=?) OR (p.kind='assignedTeamIds' AND p.person_id=?)))")
        args.extend([int(person), selected_team])
    search = tenders.text(filters.get('q'), 'Search', limit=300)
    if search:
        # Parameterized LIKE with escaped wildcards: user input is plain text.
        escaped = '%' + search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        where.append("(json_extract(o.body,'$.project') LIKE ? ESCAPE '\\' OR json_extract(o.body,'$.location') LIKE ? ESCAPE '\\' OR json_extract(o.body,'$.builders') LIKE ? ESCAPE '\\' OR json_extract(o.body,'$.workingScope') LIKE ? ESCAPE '\\')")
        args.extend([escaped] * 4)
    return ' AND '.join(where), args


def list_opportunities(store, filters, user):
    initialize(store)
    process_due(store)
    teams, users = directory()
    actor = _actor(user, users)
    page = _page(filters.get('page'), 1, 100000)
    size = _page(filters.get('pageSize'), 30, 100)
    where, args = _query(filters, users=users)
    count_where, count_args = _query(filters, include_status=False, users=users)
    with store.connect() as db:
        db.execute('BEGIN')
        total = db.execute('SELECT COUNT(*) FROM opportunities o WHERE ' + where, args).fetchone()[0]
        page = min(page, max(1, (total + size - 1) // size))
        order = {'due': "CASE WHEN due='' THEN 1 ELSE 0 END,due,updated_at DESC,id",
                 'updated': 'updated_at DESC,id', 'name': 'project_key,id'}.get(filters.get('sort'),
                     "CASE WHEN due='' THEN 1 ELSE 0 END,due,updated_at DESC,id")
        rows = db.execute('SELECT body,revision FROM opportunities o WHERE ' + where +
                          ' ORDER BY ' + order + ' LIMIT ? OFFSET ?',
                          (*args, size, (page - 1) * size)).fetchall()
        counts = {status: 0 for status in STATUSES}
        counts.update({r['status']: r['n'] for r in db.execute('SELECT status,COUNT(*) n FROM opportunities o WHERE ' +
                       count_where + ' GROUP BY status', count_args)})
        counts['all'] = sum(counts.values())
        regions = [dict(r) for r in db.execute('SELECT code,origin,timezone FROM opportunity_regions ORDER BY code')]
        saved_builders = [r[0] for r in db.execute('SELECT name FROM opportunity_builders ORDER BY name COLLATE NOCASE')]
        assigned = {r['person_id']: r['n'] for r in db.execute('''SELECT p.person_id,COUNT(*) n
            FROM opportunity_people p JOIN opportunities o ON o.id=p.opportunity_id
            WHERE p.kind='assignedTeamIds' AND o.deleted_at IS NULL GROUP BY p.person_id''')}
        unassigned = db.execute("SELECT COUNT(*) FROM opportunities o WHERE o.deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM opportunity_people p WHERE p.opportunity_id=o.id AND p.kind='assignedTeamIds')").fetchone()[0]
    builders = {tenders.builder_key(name): name for name in saved_builders}
    for submission in store.all_data()['submissions']:
        name = submission.get('builder', '')
        if name:
            builders.setdefault(tenders.builder_key(name), name)
    # Include builders already entered in Estimator projects as well.
    with account_connection() as db:
        for row in db.execute("SELECT DISTINCT client FROM projects WHERE client IS NOT NULL AND client!=''"):
            for name in str(row[0]).splitlines():
                if name.strip():
                    builders.setdefault(tenders.builder_key(name), name.strip())
    return {'items': [_public({**json.loads(r['body']), 'revision': r['revision']}, actor) for r in rows],
            'total': total, 'page': page, 'pageSize': size, 'counts': counts,
            'regions': regions, 'teams': teams, 'users': users,
            'builders': sorted(builders.values(), key=str.casefold),
            'teamCounts': [{**team, 'count': assigned.get(team['id'], 0)} for team in teams],
            'unassignedCount': unassigned,
            'canApprove': actor['role'] == 'admin' or actor.get('team_id') is not None}


def regions(store, user, payload=None):
    initialize(store)
    _, users = directory()
    actor = _actor(user, users)
    if payload is not None:
        if actor['role'] != 'admin':
            raise tenders.ValidationError('Only an administrator can change region defaults.', 403)
        code = _region_code(payload.get('code'))
        origin = tenders.text(payload.get('origin'), 'Distance origin', required=True, limit=1000)
        zone = tenders.text(payload.get('timezone') or 'Australia/Sydney', 'Time zone', limit=100)
        try:
            ZoneInfo(zone)
        except Exception:
            raise tenders.ValidationError('Choose a valid IANA time zone, for example Australia/Sydney.') from None
        with _transaction(store) as db:
            db.execute('INSERT INTO opportunity_regions(code,origin,timezone) VALUES(?,?,?) ON CONFLICT(code) DO UPDATE SET origin=excluded.origin,timezone=excluded.timezone',
                       (code, origin, zone))
            db.execute('UPDATE opportunity_generation SET value=value+1')
            _activity(store, db, actor, 'Updated opportunity region', {'id': '', 'project': 'Region ' + code},
                      {'region': code, 'origin': origin, 'timezone': zone})
    with store.connect() as db:
        return {'regions': [dict(r) for r in db.execute('SELECT code,origin,timezone FROM opportunity_regions ORDER BY code')]}


def _record_time_event(store, db, item, users, kind, action, message, now=None):
    key = f'opportunity:{item["id"]}:{item["due"]}:{kind}'
    moment = (now.isoformat() if now else tenders.timestamp())
    if not db.execute('INSERT OR IGNORE INTO opportunity_events(event_key,created_at) VALUES(?,?)', (key, moment)).rowcount:
        return
    _activity(store, db, SYSTEM, action, item, {'due': item['due']}, timestamp=moment)
    _notify(db, _recipients(item, users), key, kind, item, message, created_at=moment)


def process_due(store, force=False, now=None):
    """Idempotent request/startup sweep; safe to also call from the server timer."""
    initialize(store)
    monotonic = time.monotonic()
    if not force and monotonic - store._opportunity_sweep_at < 60:
        return
    if not store._opportunity_sweep_lock.acquire(blocking=False):
        return
    try:
        if not force and time.monotonic() - store._opportunity_sweep_at < 60:
            return
        _, users = directory()
        instant = now or datetime.now(timezone.utc)
        with _transaction(store) as db:
            rows = db.execute("SELECT body,revision FROM opportunities WHERE deleted_at IS NULL AND status IN ('pending','approved') AND due!=''").fetchall()
            for row in rows:
                item = {**json.loads(row['body']), 'revision': row['revision']}
                days = (date.fromisoformat(item['due']) - _today(db, item['region'], instant)).days
                if days < 0:
                    item.update(status='expired', revision=item['revision'] + 1,
                                updatedAt=instant.isoformat(), expiredAt=instant.isoformat())
                    _write(db, item)
                    _record_time_event(store, db, item, users, 'expired', 'Expired opportunity',
                                       'The deadline has passed. This opportunity is now expired.', instant)
                elif days <= 7:
                    kind = 'due-today' if days == 0 else 'due-soon' if days <= 1 else 'upcoming'
                    message = 'The opportunity deadline is today.' if days == 0 else f'The opportunity deadline is in {days} day{"s" if days != 1 else ""}.'
                    _record_time_event(store, db, item, users, kind, 'Opportunity deadline reminder', message, instant)
            # Tender reminders belong in the same inbox; opening the bell must
            # never mark the underlying reminder as completed.
            for row in db.execute('SELECT body FROM reminders').fetchall():
                reminder = json.loads(row[0])
                if reminder.get('done') or not reminder.get('due'):
                    continue
                due = datetime.fromisoformat(reminder['due']).replace(tzinfo=ZoneInfo('Australia/Sydney'))
                remaining = (due - instant).total_seconds()
                if remaining > 7 * 86400:
                    continue
                submission_row = db.execute('SELECT body FROM submissions WHERE id=?', (reminder['submissionId'],)).fetchone()
                if not submission_row:
                    continue
                submission = json.loads(submission_row[0])
                stage = 'overdue' if remaining < 0 else 'upcoming'
                key = f'reminder:{reminder["id"]}:{reminder["due"]}:{stage}'
                # Reminders are shared in the existing Tender workspace; use
                # per-user rows/read receipts rather than one global read flag.
                for person in users:
                    db.execute('''INSERT OR IGNORE INTO tender_notifications
                        (id,user_id,kind,target_kind,target_id,title,message,due,created_at,event_key)
                        VALUES(?,?,?,?,?,?,?,?,?,?)''', (str(uuid.uuid4()), person['id'], 'reminder', 'submission',
                            reminder['submissionId'], submission.get('project', 'Tender reminder'),
                            ('Overdue reminder: ' if remaining < 0 else 'Upcoming reminder: ') + reminder.get('note', 'Follow up'),
                            reminder['due'], instant.isoformat(), key))
        store._opportunity_sweep_at = time.monotonic()
    finally:
        store._opportunity_sweep_lock.release()


def notifications(store, filters, user):
    initialize(store)
    process_due(store)
    _, users = directory()
    actor = _actor(user, users)
    page = _page(filters.get('page'), 1, 100000)
    size = _page(filters.get('pageSize'), 30, 100)
    with store.connect() as db:
        db.execute('BEGIN')
        total = db.execute('SELECT COUNT(*) FROM tender_notifications WHERE user_id=?', (actor['id'],)).fetchone()[0]
        unread = db.execute('SELECT COUNT(*) FROM tender_notifications WHERE user_id=? AND read_at IS NULL', (actor['id'],)).fetchone()[0]
        page = min(page, max(1, (total + size - 1) // size))
        rows = db.execute('''SELECT * FROM tender_notifications WHERE user_id=?
            ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?''', (actor['id'], size, (page - 1) * size)).fetchall()
        items = []
        for row in rows:
            item = {'id': row['id'], 'kind': row['kind'], 'title': row['title'], 'message': row['message'],
                    'due': row['due'], 'createdAt': row['created_at'], 'read': row['read_at'] is not None}
            item['opportunityId' if row['target_kind'] == 'opportunity' else 'submissionId'] = row['target_id']
            items.append(item)
    return {'items': items, 'unread': unread, 'unreadCount': unread, 'total': total, 'page': page, 'pageSize': size}


def mark_read(store, payload, user):
    initialize(store)
    _, users = directory()
    actor = _actor(user, users)
    all_items = payload.get('all', False)
    if type(all_items) is not bool:
        raise tenders.ValidationError('Choose valid notifications.')
    ids = payload.get('ids', [])
    if not isinstance(ids, list) or len(ids) > 500 or any(not isinstance(i, str) or len(i) > 100 for i in ids):
        raise tenders.ValidationError('Choose valid notifications.')
    with _transaction(store) as db:
        if all_items:
            db.execute('UPDATE tender_notifications SET read_at=? WHERE user_id=? AND read_at IS NULL',
                       (tenders.timestamp(), actor['id']))
        elif ids:
            db.execute('UPDATE tender_notifications SET read_at=? WHERE user_id=? AND read_at IS NULL AND id IN (' +
                       ','.join('?' for _ in ids) + ')', (tenders.timestamp(), actor['id'], *ids))
        unread = db.execute('SELECT COUNT(*) FROM tender_notifications WHERE user_id=? AND read_at IS NULL', (actor['id'],)).fetchone()[0]
    return {'ok': True, 'unread': unread, 'unreadCount': unread}


def existing_keys(store):
    initialize(store)
    with store.connect() as db:
        # Deleted records still count: replaying an old file must not resurrect them.
        return {r['region'] + '|' + r['project_key']: r['id']
                for r in db.execute('SELECT id,region,project_key FROM opportunities')}


def import_records(store, records, actor, source, seed_key=None, expected_generation=None):
    """Append-only batch import. Seed is internal; HTTP cannot request seed status."""
    initialize(store)
    if not isinstance(records, list) or len(records) > 10000:
        raise tenders.ValidationError('Import up to 10,000 opportunities at a time.')
    teams, users = directory()
    actor = {**SYSTEM, 'name': 'Workbook import'} if seed_key else _actor(actor, users)
    added, duplicates, identifiers = 0, 0, []
    with _transaction(store) as db:
        if seed_key and db.execute('SELECT 1 FROM settings WHERE id=?', (seed_key,)).fetchone():
            return {'added': 0, 'duplicates': 0, 'items': [], 'seeded': True}
        current_generation = db.execute('SELECT value FROM opportunity_generation').fetchone()[0]
        if expected_generation is not None and expected_generation != current_generation:
            raise tenders.ValidationError('The data changed after the preview. Preview the workbook again.', 409)
        keys = {(r['region'], r['project_key']) for r in db.execute('SELECT region,project_key FROM opportunities')}
        known_ids = {r[0] for r in db.execute('SELECT id FROM opportunities')}
        for record in records:
            source_id = record.get('sourceRecordId') or record.get('id')
            # Existing rows are deliberately ignored by append-only import.
            # Resolve their identity before validating fields we will not apply;
            # otherwise an edited old export can block unrelated new records.
            if isinstance(source_id, str) and source_id in known_ids:
                duplicates += 1
                continue
            key = (_region_code(record.get('region') or 'NSW'),
                   tenders.project_key(tenders.text(record.get('project'), 'Project name', required=True, limit=500)))
            if key in keys:
                duplicates += 1
                continue
            fields = _normalise(db, record)
            item = _new_item(db, fields, actor)
            item['source'] = source
            item['sourceStatus'] = record.get('sourceStatus', 'pending')
            item['sourceData'] = record.get('sourceData', {})
            if seed_key and item['sourceStatus'] in ('approved', 'rejected'):
                item['status'] = item['sourceStatus']
            expired = bool(item['due'] and date.fromisoformat(item['due']) < _today(db, item['region']))
            if expired and item['status'] in ('pending', 'approved'):
                item['status'] = 'expired'
            _write(db, item, new=True)
            _activity(store, db, actor, 'Imported opportunity', item,
                      {'source': source, 'sourceStatus': item['sourceStatus'],
                       'sourceApproverRecorded': False, 'seed': bool(seed_key)})
            if item['status'] == 'expired':
                _record_time_event(store, db, item, users, 'expired', 'Expired opportunity',
                                   'The imported deadline has passed. This opportunity is expired.')
            keys.add(key)
            known_ids.add(item['id'])
            identifiers.append(item['id'])
            added += 1
        if seed_key:
            db.execute('INSERT INTO settings VALUES(?,?)', (seed_key, json.dumps({'added': added, 'source': source})))
        else:
            _activity(store, db, actor, 'Imported opportunities Excel', {'id': '', 'project': source}, {
                'opportunityImport': True, 'filename': source, 'added': added, 'updated': 0, 'skipped': duplicates})
            if added:
                for uid in {u['id'] for u in users if u['role'] == 'admin'} | {actor['id']}:
                    db.execute('''INSERT INTO tender_notifications
                        (id,user_id,kind,target_kind,target_id,title,message,created_at,event_key)
                        VALUES(?,?,?,?,?,?,?,?,?)''', (str(uuid.uuid4()), uid, 'import', 'opportunity', identifiers[0],
                            'Opportunities imported', f'{actor["name"]} imported {added} opportunities from {source}.',
                            tenders.timestamp(), 'import:' + str(uuid.uuid4())))
    return {'added': added, 'duplicates': duplicates, 'items': identifiers, 'seeded': bool(seed_key)}
