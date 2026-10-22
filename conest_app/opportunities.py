"""Opportunity workflow, audit history and per-person Tender notifications.

Opportunity data lives with tenders; account/team membership is resolved live
from the Estimator database. Every change is authorized inside the server and
uses an optimistic revision inside one SQLite write transaction.
"""
from __future__ import annotations

import json
import ipaddress
import math
import re
import threading
import time
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from . import tenders
from .database import connect as account_connection
from .opportunity_retention import active_sql, reactivate_builder

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
    # Ordinary opportunity activity does not alter tender submissions. Keeping
    # its writes separate avoids discarding that cache on every inbox read.
    # The quotation handoff explicitly increments tender_generation on success.
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
    decision = bool(actor['role'] == 'admin' or actor.get('team_id') is not None)
    return {'edit': bool(edit), 'manage': bool(manage), 'approve': decision, 'quote': decision}


def _require(item, actor, permission):
    if not permissions(item, actor)[permission]:
        messages = {
            'manage': 'Only the creator or an administrator can assign, delete, or manage access.',
            'edit': 'Only the creator, an administrator, or an authorised editor can edit this opportunity.',
            'approve': 'An administrator or a user who belongs to a team must make this decision.',
            'quote': 'An administrator or a user who belongs to a team must record the quote.',
        }
        raise tenders.ValidationError(messages[permission], 403)


def _identifier(value, label='Opportunity ID'):
    return tenders.text(value, label, required=True, limit=100)


def _decode_opportunity(row):
    """Read a legacy creator from stored SQL without rewriting source JSON.

    Parent migration can recover created_by from an original creator_id column.
    The JSON document remains intact until a real edit, so every active read
    that supplies permissions, recipients or later writes must use this value
    when the document has no createdBy key. Explicit JSON ownership is retained.
    """
    item = json.loads(row['body'])
    if 'createdBy' not in item:
        item['createdBy'] = row['created_by']
    return {**item, 'revision': row['revision']}


def _find(db, identifier, include_deleted=False):
    row = db.execute('SELECT * FROM opportunities WHERE id=? AND ' +
                     active_sql('opportunity', 'opportunities.id'), (identifier,)).fetchone()
    if not row or (row['deleted_at'] and not include_deleted):
        raise tenders.ValidationError('This opportunity no longer exists.', 404)
    return _decode_opportunity(row)


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


def _deadline_passed(db, item):
    return bool(item.get('due') and date.fromisoformat(item['due']) < _today(db, item['region']))


def _is_quoted(item):
    return item.get('quoteStatus') == 'quoted' or bool(item.get('submissionIds'))


def normalise_link(value):
    """Validate an optional web address without following it or fetching content."""
    if value is None:
        return ''
    if not isinstance(value, str):
        raise tenders.ValidationError('Link must be text.')
    # urllib removes some control characters while parsing. Reject them before
    # trimming or parsing so the saved URL cannot differ from the user's input.
    if any(unicodedata.category(char) in ('Cc', 'Cf') for char in value):
        raise tenders.ValidationError('Link cannot contain control characters.')
    value = value.strip()
    if not value:
        return ''
    if any(char.isspace() for char in value) or any(char in value for char in '\\<>"'):
        raise tenders.ValidationError('Link cannot contain spaces, backslashes, or quotation marks.')
    message = 'Enter a valid http:// or https:// Link without a username or password.'
    explicit = bool(re.match(r'^https?://', value, re.I))
    if value.startswith('//'):
        value = 'https:' + value
    elif not explicit:
        # A bare domain with an optional port is convenient to paste. Other
        # schemes (including malformed http: addresses) must not become hosts.
        scheme = re.match(r'^([a-z][a-z0-9+.-]*):', value, re.I)
        bare_port = re.match(r'^[^/?#:@]+:[0-9]+(?:[/?#]|$)', value)
        if scheme and not bare_port:
            raise tenders.ValidationError(message)
        value = 'https://' + value
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (parsed.scheme.lower() not in ('http', 'https') or not host or
                parsed.username is not None or parsed.password is not None or
                '%' in host or parsed.netloc.endswith(':')):
            raise ValueError()
        port = parsed.port  # Reading this also rejects malformed/out-of-range ports.
        if ':' in host:
            host = '[' + ipaddress.IPv6Address(host).compressed + ']'
        else:
            host = host.encode('idna').decode('ascii').lower()
            labels = host.rstrip('.').split('.')
            if (len(host.rstrip('.')) > 253 or any(not re.fullmatch(
                    r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels)):
                raise ValueError()
            if not explicit and len(labels) == 1 and host != 'localhost':
                raise ValueError()
        result = urlunsplit((parsed.scheme.lower(), host + (':' + str(port) if port is not None else ''),
                             parsed.path, parsed.query, parsed.fragment))
    except (ValueError, UnicodeError):
        raise tenders.ValidationError(message) from None
    if len(result) > 2048:
        raise tenders.ValidationError('Link must be 2,048 characters or shorter.')
    return result


def _normalise(db, payload, current=None):
    base = dict(current or {})
    # Shared contact details are legacy source information. Ignore new writes,
    # while save() preserves any historical values already in the stored body.
    base.update({k: v for k, v in payload.items() if k not in ('sourceData', 'contact', 'email')})
    fields = {
        'project': tenders.text(base.get('project'), 'Project name', required=True, limit=500),
        'region': _region_code(base.get('region') or 'NSW'),
        'location': tenders.text(base.get('location'), 'Location', limit=1000),
        'workingScope': tenders.text(base.get('workingScope'), 'Working scope', limit=20000),
        'remarks': tenders.text(base.get('remarks'), 'Notes', limit=20000),
        'link': normalise_link(base.get('link')),
        'category': tenders.text(base.get('category'), 'Category', limit=500),
        'budget': tenders.text(base.get('budget'), 'Budget', limit=500),
        'addedDate': tenders.date_value(base.get('addedDate')),
        'due': tenders.date_value(base.get('due')),
        'value': _number(base.get('value'), 'Tender value'),
        'distanceKm': _number(base.get('distanceKm'), 'Distance'),
    }
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
            reactivate_builder(db, key, item['updatedAt'])


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
    previous = set() if new else {(row['kind'], row['person_id']) for row in db.execute(
        'SELECT kind,person_id FROM opportunity_people WHERE opportunity_id=?', (item['id'],))}
    assigned = {(kind, uid) for kind in AUTHORITY_FIELDS for uid in item.get(kind, [])}
    # An ordinary edit or decision must not replace unchanged assignment rows.
    db.executemany('DELETE FROM opportunity_people WHERE opportunity_id=? AND kind=? AND person_id=?',
                   [(item['id'], kind, uid) for kind, uid in previous - assigned])
    db.executemany('INSERT INTO opportunity_people(opportunity_id,kind,person_id) VALUES(?,?,?)',
                   [(item['id'], kind, uid) for kind, uid in assigned - previous])
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
    # Source workbook IDs never identify a new row. Check every physical row,
    # including the retired reset cohort, before allocating a fresh identity.
    for _ in range(8):
        identifier = str(uuid.uuid4())
        if not db.execute('SELECT 1 FROM opportunities WHERE id=?', (identifier,)).fetchone():
            break
    else:
        raise tenders.ValidationError('A unique opportunity ID could not be created. Try again.', 503)
    return {**fields, 'id': identifier, 'revision': 0, 'status': 'pending',
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


def _approve_assignment_requested(payload, item, actor):
    """Explicit authorised team assignment is a decision, including past dates."""
    return bool('assignedTeamIds' in payload and item.get('assignedTeamIds') and
                item['status'] != 'approved' and permissions(item, actor)['manage'])


def _set_approved(item, actor, moment):
    item.update(status='approved', decisionBy=actor['id'], decisionByName=actor['name'],
                decisionAt=moment, decisionReason='', approvedBy=actor['id'],
                approvedByName=actor['name'], approvedAt=moment)
    if item.get('quoteStatus') == 'not_quoted':
        item['quoteStatus'] = ''


def _assignment_approval_event(store, db, actor, before, item, users):
    event = _activity(store, db, actor, 'Approved opportunity', item, {
        'before': before.get('status', 'pending'), 'after': 'approved',
        'reason': 'Team assigned', 'automatic': True,
        'assignedTeamIds': item['assignedTeamIds'],
    })
    _notify(db, _recipients(item, users), f'decision:{event}', 'approved', item,
            f'{actor["name"]} approved this opportunity by assigning a team.')


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
        auto_approve = _approve_assignment_requested(payload, item, actor)
        if identifier and not changed and not authority_changed and not auto_approve:
            return _detail(db, item, actor)
        moment = tenders.timestamp()
        item.update(updatedAt=moment, updatedBy=actor['id'], updatedByName=actor['name'])
        if identifier:
            item['revision'] += 1
        expired = bool(item['due'] and date.fromisoformat(item['due']) < _today(db, item['region']))
        if auto_approve:
            _set_approved(item, actor, moment)
        elif item['status'] == 'expired' and not expired:
            item.update(status='pending', decisionBy=None, decisionByName='', decisionAt='', decisionReason='')
            _activity(store, db, actor, 'Reopened opportunity', item, {'reason': 'Deadline extended'})
        elif item['status'] == 'pending' and expired:
            item['status'] = 'expired'
        _write(db, item, new=not identifier)
        if changed or not identifier:
            action = 'Updated opportunity' if identifier else 'Created opportunity'
            event = _activity(store, db, actor, action, item,
                              {'before': {k: before.get(k) for k in changed}, 'after': changed})
            creation = {'pending': 'added an opportunity awaiting approval',
                        'approved': 'added an approved opportunity',
                        'expired': 'added an expired opportunity'}.get(item['status'], 'added an opportunity')
            _notify(db, _recipients(item, users), f'change:{event}', 'updated' if identifier else 'created', item,
                    f'{actor["name"]} {"updated this opportunity" if identifier else creation}.')
        _assignment_events(store, db, actor, before, item, users)
        if auto_approve:
            _assignment_approval_event(store, db, actor, before, item, users)
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
        auto_approve = kind == 'assign' and _approve_assignment_requested(payload, item, actor)
        if all(item[k] == before.get(k, []) for k in AUTHORITY_FIELDS) and not auto_approve:
            return _detail(db, item, actor)
        item.update(revision=item['revision'] + 1, updatedAt=tenders.timestamp(),
                    updatedBy=actor['id'], updatedByName=actor['name'])
        if auto_approve:
            _set_approved(item, actor, item['updatedAt'])
        _write(db, item)
        _assignment_events(store, db, actor, before, item, users)
        if auto_approve:
            _assignment_approval_event(store, db, actor, before, item, users)
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
    with _transaction(store) as db:
        item = _find(db, identifier)
        _require(item, actor, 'manage' if decision == 'pending' else 'approve')
        _revision(item, payload)
        if _is_quoted(item) and decision != 'approved':
            raise tenders.ValidationError('This opportunity has already been quoted. Update its outcome in Project Chase-up.', 409)
        if item['status'] == decision:
            return _detail(db, item, actor)
        if decision == 'pending' and item['due'] and date.fromisoformat(item['due']) < _today(db, item['region']):
            raise tenders.ValidationError('Approve this opportunity to proceed after its deadline, or extend the deadline before requesting approval.', 409)
        before = item['status']
        # Older approved projects may already be followed up elsewhere. A
        # normal rejection after expiry must not invent a Not quoted outcome.
        not_quoted = decision == 'rejected' and before == 'approved' and not _deadline_passed(db, item)
        moment = tenders.timestamp()
        item.update(status=decision, revision=item['revision'] + 1, updatedAt=moment,
                    updatedBy=actor['id'], updatedByName=actor['name'],
                    decisionBy=actor['id'] if decision != 'pending' else None,
                    decisionByName=actor['name'] if decision != 'pending' else '',
                    decisionAt=moment if decision != 'pending' else '', decisionReason=reason)
        if decision == 'approved':
            _set_approved(item, actor, moment)
            item['decisionReason'] = reason
        elif not_quoted:
            item.update(quoteStatus='not_quoted', notQuotedBy=actor['id'],
                        notQuotedByName=actor['name'], notQuotedAt=moment)
        elif decision == 'pending' and item.get('quoteStatus') == 'not_quoted':
            item['quoteStatus'] = ''
        _write(db, item)
        action = {'approved': 'Approved opportunity', 'rejected': 'Rejected opportunity',
                  'pending': 'Requested opportunity approval'}[decision]
        event = _activity(store, db, actor, action, item, {'before': before, 'after': decision, 'reason': reason,
                                                        **({'quoteStatus': 'not_quoted'} if not_quoted else {})})
        message = f'{actor["name"]} {"requested approval for" if decision == "pending" else decision} this opportunity.'
        if reason:
            message += ' ' + reason
        _notify(db, _recipients(item, users), f'decision:{event}', decision, item, message)
        return _detail(db, item, actor)


def quote(store, payload, user):
    from .opportunity_quoting import quote as record_quote
    return record_quote(store, payload, user)


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
    where = ['o.deleted_at IS NULL', active_sql('opportunity', 'o.id')]
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
        where.append("(json_extract(o.body,'$.project') LIKE ? ESCAPE '\\' OR json_extract(o.body,'$.location') LIKE ? ESCAPE '\\' OR json_extract(o.body,'$.builders') LIKE ? ESCAPE '\\' OR json_extract(o.body,'$.workingScope') LIKE ? ESCAPE '\\' OR json_extract(o.body,'$.link') LIKE ? ESCAPE '\\')")
        args.extend([escaped] * 5)
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
        rows = db.execute('SELECT body,revision,created_by FROM opportunities o WHERE ' + where +
                          ' ORDER BY ' + order + ' LIMIT ? OFFSET ?',
                          (*args, size, (page - 1) * size)).fetchall()
        counts = {status: 0 for status in STATUSES}
        counts.update({r['status']: r['n'] for r in db.execute('SELECT status,COUNT(*) n FROM opportunities o WHERE ' +
                       count_where + ' GROUP BY status', count_args)})
        counts['all'] = sum(counts.values())
        regions = [dict(r) for r in db.execute('SELECT code,origin,timezone FROM opportunity_regions ORDER BY code')]
        saved_builders = [r[0] for r in db.execute('SELECT name FROM opportunity_builders WHERE ' +
                          active_sql('builder', 'opportunity_builders.builder_key') + ' ORDER BY name COLLATE NOCASE')]
        assigned = {r['person_id']: r['n'] for r in db.execute('''SELECT p.person_id,COUNT(*) n
            FROM opportunity_people p JOIN opportunities o ON o.id=p.opportunity_id
            WHERE p.kind='assignedTeamIds' AND o.deleted_at IS NULL AND ''' +
            active_sql('opportunity', 'o.id') + ' GROUP BY p.person_id')}
        unassigned = db.execute("SELECT COUNT(*) FROM opportunities o WHERE o.deleted_at IS NULL AND " +
            active_sql('opportunity', 'o.id') + " AND NOT EXISTS (SELECT 1 FROM opportunity_people p WHERE p.opportunity_id=o.id AND p.kind='assignedTeamIds')").fetchone()[0]
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
    return {'items': [_public(_decode_opportunity(r), actor) for r in rows],
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
        utc_day = instant.astimezone(timezone.utc).date()
        with _transaction(store) as db:
            # Keep permanent approvals out of the expiry work queue. The UTC
            # buffer includes every region's local day; exact regional dates
            # below still decide expiry/reminders, including daylight saving.
            rows = db.execute("SELECT body,revision,created_by FROM opportunities WHERE deleted_at IS NULL "
                              "AND due!='' AND due<=? AND (status='pending' OR "
                              "(status='approved' AND due>=? AND COALESCE(json_extract(body,'$.quoteStatus'),'')!='quoted')) AND " +
                              active_sql('opportunity', 'opportunities.id'),
                              ((utc_day + timedelta(days=8)).isoformat(), (utc_day - timedelta(days=1)).isoformat())).fetchall()
            region_days = {}
            for row in rows:
                item = _decode_opportunity(row)
                if item['region'] not in region_days:
                    region_days[item['region']] = _today(db, item['region'], instant)
                days = (date.fromisoformat(item['due']) - region_days[item['region']]).days
                if days < 0 and item['status'] == 'pending':
                    item.update(status='expired', revision=item['revision'] + 1,
                                updatedAt=instant.isoformat(), expiredAt=instant.isoformat())
                    _write(db, item)
                    _record_time_event(store, db, item, users, 'expired', 'Expired opportunity',
                                       'The deadline has passed. This opportunity is now expired.', instant)
                elif 0 <= days <= 7 and item.get('quoteStatus') != 'quoted':
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


def _visible_notifications_sql():
    # Include the parent predicate so an older worker's late notification for a
    # retired opportunity cannot reappear after the reset snapshot was taken.
    return (active_sql('notification', 'tender_notifications.id') +
            " AND (target_kind!='opportunity' OR " +
            active_sql('opportunity', 'tender_notifications.target_id') + ')')


def notifications(store, filters, user):
    initialize(store)
    process_due(store)
    _, users = directory()
    actor = _actor(user, users)
    page = _page(filters.get('page'), 1, 100000)
    size = _page(filters.get('pageSize'), 30, 100)
    visible = _visible_notifications_sql()
    with store.connect() as db:
        db.execute('BEGIN')
        total = db.execute('SELECT COUNT(*) FROM tender_notifications WHERE user_id=? AND ' + visible, (actor['id'],)).fetchone()[0]
        unread = db.execute('SELECT COUNT(*) FROM tender_notifications WHERE user_id=? AND read_at IS NULL AND ' + visible, (actor['id'],)).fetchone()[0]
        page = min(page, max(1, (total + size - 1) // size))
        rows = db.execute('SELECT * FROM tender_notifications WHERE user_id=? AND ' + visible +
            ' ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?', (actor['id'], size, (page - 1) * size)).fetchall()
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
    visible = _visible_notifications_sql()
    with _transaction(store) as db:
        if all_items:
            db.execute('UPDATE tender_notifications SET read_at=? WHERE user_id=? AND read_at IS NULL AND ' + visible,
                       (tenders.timestamp(), actor['id']))
        elif ids:
            db.execute('UPDATE tender_notifications SET read_at=? WHERE user_id=? AND read_at IS NULL AND id IN (' +
                       ','.join('?' for _ in ids) + ') AND ' + visible, (tenders.timestamp(), actor['id'], *ids))
        unread = db.execute('SELECT COUNT(*) FROM tender_notifications WHERE user_id=? AND read_at IS NULL AND ' + visible, (actor['id'],)).fetchone()[0]
    return {'ok': True, 'unread': unread, 'unreadCount': unread}


def existing_keys(store):
    initialize(store)
    with store.connect() as db:
        # Ordinary deletions still prevent replay. The owner's reset cohort can
        # be imported again, always with new IDs and the old rows left intact.
        return {r['region'] + '|' + r['project_key']: r['id']
                for r in db.execute('SELECT id,region,project_key FROM opportunities WHERE ' +
                                    active_sql('opportunity', 'opportunities.id'))}


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
        current = db.execute('SELECT id,region,project_key FROM opportunities WHERE ' +
                             active_sql('opportunity', 'opportunities.id')).fetchall()
        keys = {(r['region'], r['project_key']) for r in current}
        replay_ids = {r['id'] for r in current}
        for record in records:
            source_id = record.get('sourceRecordId') or record.get('id')
            # Existing rows are deliberately ignored by append-only import.
            # Resolve their identity before validating fields we will not apply;
            # otherwise an edited old export can block unrelated new records.
            if isinstance(source_id, str) and source_id in replay_ids:
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
            if expired and item['status'] == 'pending':
                item['status'] = 'expired'
            _write(db, item, new=True)
            _activity(store, db, actor, 'Imported opportunity', item,
                      {'source': source, 'sourceStatus': item['sourceStatus'],
                       'sourceApproverRecorded': False, 'seed': bool(seed_key)})
            if item['status'] == 'expired':
                _record_time_event(store, db, item, users, 'expired', 'Expired opportunity',
                                   'The imported deadline has passed. This opportunity is expired.')
            keys.add(key)
            replay_ids.add(item['id'])
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
