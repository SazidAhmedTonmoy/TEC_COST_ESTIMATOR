"""Opportunity classification, duplicate review and existing-project links."""
from __future__ import annotations
import hashlib
import json
import unicodedata
from . import opportunities as op, tenders
from .opportunity_retention import active_sql

CATEGORIES = ('Commercial', 'Education', 'Healthcare', 'Hospitality', 'Industrial',
              'Infrastructure', 'Mixed Use', 'Public / Community', 'Residential',
              'Retail', 'Sport / Recreation', 'Other')

def match_key(value):
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in
                    unicodedata.normalize('NFKC', str(value or '')).casefold()).split())

def categories(db):
    values = {match_key(name): name for name in CATEGORIES}
    for row in db.execute("SELECT json_extract(body,'$.category') FROM opportunities o WHERE deleted_at IS NULL AND " + active_sql('opportunity', 'o.id') + ' ORDER BY id'):
        name = str(row[0] or '').strip()
        if name:
            values.setdefault(match_key(name), name)
    return sorted(values.values(), key=str.casefold)

def canonical_category(db, value):
    value = tenders.text(value, 'Category', limit=500)
    if not value: return ''
    standard = next((name for name in CATEGORIES if match_key(name) == match_key(value)), None)
    return standard or next((name for name in categories(db) if match_key(name) == match_key(value)), value)

def duplicate_matches(db, project, location, exclude=''):
    name, address = match_key(project), match_key(location)
    if address in ('nil', 'n a', 'na', 'not recorded', 'not specified', 'unknown', 'tbc'): address = ''
    matches = []
    for row in db.execute('SELECT id,body,revision FROM opportunities o WHERE deleted_at IS NULL AND id!=? AND ' + active_sql('opportunity', 'o.id'), (exclude,)):
        item = json.loads(row['body'])
        same_name = bool(name and name == match_key(item.get('project')))
        same_address = bool(address and address == match_key(item.get('location')))
        if same_name or same_address:
            matches.append({'id': row['id'], 'project': item.get('project', ''),
                'location': item.get('location', ''), 'status': item.get('status', ''),
                'builders': item.get('builders', []), 'region': item.get('region', ''),
                'reason': 'Same project name and address' if same_name and same_address else
                          'Same project name' if same_name else 'Same address', 'revision': row['revision']})
    matches.sort(key=lambda item: item['id'])
    token = hashlib.sha256(json.dumps([name, address, exclude, matches], sort_keys=True).encode()).hexdigest() if matches else ''
    return {'duplicates': matches[:20], 'duplicateCount': len(matches), 'duplicateToken': token}

def check_duplicates(store, params, user):
    op.initialize(store)
    op._actor(user, op.directory()[1])
    project = tenders.text(params.get('project'), 'Project name', limit=500)
    address = tenders.text(params.get('location'), 'Location', limit=1000)
    exclude = tenders.text(params.get('id'), 'Opportunity ID', limit=100)
    with store.connect() as db:
        return duplicate_matches(db, project, address, exclude)

def project_choices(store, params, user):
    op.initialize(store)
    actor = op._actor(user, op.directory()[1])
    with store.connect() as db:
        item = op._find(db, op._identifier(params.get('id')))
        op._require(item, actor, 'quote')
        if item['status'] != 'approved':
            raise tenders.ValidationError('Only approved opportunities can be linked.', 409)
    query = match_key(tenders.text(params.get('q'), 'Search', limit=300))
    groups = {}
    for row in store.all_data()['submissions']:
        key = tenders.project_key(row.get('project'))
        group = groups.setdefault(key, {'submissionId': row['id'], 'project': row.get('project', ''),
            'builders': [], 'locations': [], 'regions': [], 'value': None, 'count': 0, 'blocked': False})
        group['count'] += 1
        for field, source in [('builders', 'builder'), ('locations', 'location'), ('regions', 'region')]:
            if row.get(source) and row[source] not in group[field]: group[field].append(row[source])
        if row.get('value') is not None: group['value'] = max(group['value'] or 0, row['value'])
        if row.get('opportunityId') and row['opportunityId'] != item['id']: group['blocked'] = True
    choices = [g for g in groups.values() if not query or query in match_key(' '.join([g['project'], *g['locations'], *g['builders']]))]
    choices.sort(key=lambda g: (tenders.project_key(g['project']) != tenders.project_key(item['project']), g['project'].casefold()))
    return {'items': choices[:50], 'total': len(choices)}

def link_project(store, payload, user):
    op.initialize(store)
    teams, users = op.directory()
    actor = op._actor(user, users)
    with op._transaction(store) as db:
        item = op._find(db, op._identifier(payload.get('id')))
        op._require(item, actor, 'quote')
        if item['status'] != 'approved':
            raise tenders.ValidationError('Approve this opportunity before linking it.', 409)
        target = db.execute('SELECT body FROM submissions WHERE id=?', (op._identifier(payload.get('submissionId'), 'Tender submission'),)).fetchone()
        if not target: raise tenders.ValidationError('This tender project no longer exists. Refresh the list.', 409)
        target = json.loads(target['body'])
        key = tenders.project_key(target['project'])
        rows = [json.loads(row['body']) for row in db.execute('SELECT body FROM submissions')]
        rows = [row for row in rows if tenders.project_key(row.get('project')) == key]
        ids = sorted(row['id'] for row in rows)
        if any(row.get('opportunityId') not in (None, '', item['id']) for row in rows):
            raise tenders.ValidationError('This tender project is linked to another opportunity. No data was changed.', 409)
        if item.get('submissionIds'):
            if sorted(item['submissionIds']) == ids and all(row.get('opportunityId') == item['id'] for row in rows):
                return {**op._detail(db, item, actor), 'alreadyLinked': True}
            raise tenders.ValidationError('This opportunity already has a linked project. No data was changed.', 409)
        op._revision(item, payload)
        moment = tenders.timestamp()
        for row in rows:
            row.update(opportunityId=item['id'])
            db.execute('UPDATE submissions SET body=?,revision=revision+1 WHERE id=?', (json.dumps(row, ensure_ascii=False), row['id']))
        values = [row['value'] for row in rows if row.get('value') is not None]
        item.update(submissionIds=ids, quoteStatus='quoted', linkedProjectName=target['project'],
            linkedAt=moment, linkedBy=actor['id'], linkedByName=actor['name'],
            quotedValue=max(values) if values else None, quotedBuilders=sorted({row['builder'] for row in rows}),
            updatedAt=moment, updatedBy=actor['id'], updatedByName=actor['name'], revision=item['revision']+1)
        op._write(db, item)
        event = op._activity(store, db, actor, 'Linked existing tender project', item,
                            {'project': target['project'], 'submissionIds': ids})
        op._notify(db, op._recipients(item, users), f'linked:{event}', 'updated', item,
                   f'{actor["name"]} linked the existing tender project {target["project"]}.')
        db.execute('UPDATE tender_generation SET value=value+1')
        return op._detail(db, item, actor)
