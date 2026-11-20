"""Shared builder people, with project selections kept separate from the directory.

The additive sidecar tables also link legacy records without rewriting their
original JSON. A contact ID belongs to one builder; edits are revision checked.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from . import tenders

MARKER = 'shared-builder-contacts-v383'
FIELDS = ('name', 'phones', 'emails')


def phone_key(value):
    digits = re.sub(r'\D', '', value)
    if digits.startswith('0061') and len(digits) == 13:
        digits = '0' + digits[4:]
    elif digits.startswith('61') and len(digits) == 11:
        digits = '0' + digits[2:]
    return digits


def _detail(person):
    return {key: person.get(key, '' if key == 'name' else []) for key in FIELDS}


def _unique(values, field):
    result, seen = [], set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        key = value.casefold() if field == 'emails' else (phone_key(value) or 'text:' + tenders.project_key(value))
        if key not in seen:
            result.append(value)
            seen.add(key)
    return result


def _legacy_person(person):
    if not isinstance(person, dict):
        return None
    name = str(person.get('name') or '').strip()
    result = {'name': name}
    for field in ('phones', 'emails'):
        values = person.get(field, [])
        if not isinstance(values, list):
            values = [str(values)] if values else []
        result[field] = _unique(values, field)
    return result if name or result['phones'] or result['emails'] else None


def legacy_tender_contacts(item):
    if isinstance(item.get('contacts'), list):
        return [person for raw in item['contacts'] if (person := _legacy_person(raw))]
    name = str(item.get('contact') or '').strip()
    emails = re.split(r'[,;\n]+', str(item.get('email') or ''))
    phones = re.split(r'(?:\s{2,}|[;\n]+)', str(item.get('phone') or ''))
    person = _legacy_person({'name': name, 'emails': emails, 'phones': phones})
    return [person] if person else []


def _legacy_submission_contacts(item):
    people = legacy_tender_contacts(item)
    for raw in tenders.awarded_contacts_from(item):
        person = _legacy_person(raw)
        if person and person not in people:
            people.append(person)
    return people


def _contact(row):
    return {**json.loads(row['body']), 'id': row['id'], 'revision': row['revision']}


def _touch(db):
    db.execute('UPDATE tender_generation SET value=value+1')
    db.execute('UPDATE opportunity_generation SET value=value+1')


def _validate_person(raw, current=None):
    if not isinstance(raw, dict):
        raise tenders.ValidationError('Each contact must contain a name, phone numbers and email addresses.')
    old_name = (current or {}).get('name', '')
    name_limit = max(200, len(old_name)) if raw.get('name') == old_name else 200
    result = {'name': tenders.text(raw.get('name'), 'Contact name', limit=name_limit)}
    if raw.get('id') is not None:
        result['id'] = tenders.text(raw.get('id'), 'Contact ID', required=True, limit=100)
    if 'revision' in raw:
        if type(raw['revision']) is not int or raw['revision'] < 0:
            raise tenders.ValidationError('Invalid contact revision.')
        result['revision'] = raw['revision']
    for field, singular, limit in (('phones', 'phone', 45), ('emails', 'email', 254)):
        values = raw.get(field, [])
        old_values = (current or {}).get(field, [])
        # Merging several historical records can produce more than the normal
        # new-entry limit. Keep that complete list editable without truncation.
        retained = isinstance(values, list) and current is not None and all(value in old_values for value in values)
        if not isinstance(values, list) or (len(values) > 12 and not retained):
            raise tenders.ValidationError(f'Choose up to 12 {field} per contact.')
        cleaned, seen = [], set()
        for value in values:
            value_limit = max(limit, len(value)) if isinstance(value, str) and value in old_values else limit
            v = tenders.text(value, 'Contact ' + singular, limit=value_limit)
            if not v:
                continue
            # Imported source values remain editable without blocking an
            # unrelated change; new/replaced values are always validated.
            unchanged = v in old_values
            if not unchanged and field == 'emails' and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', v):
                raise tenders.ValidationError('Enter a valid email address for the contact.')
            if not unchanged and field == 'phones' and (not re.fullmatch(r'[+0-9(). /-]{5,45}', v) or not phone_key(v)):
                raise tenders.ValidationError('Enter a valid phone number for the contact.')
            key = v.casefold() if field == 'emails' else (phone_key(v) or 'text:' + tenders.project_key(v))
            if key in seen:
                raise tenders.ValidationError('Remove the duplicate contact ' + singular + '.')
            cleaned.append(v)
            seen.add(key)
        result[field] = cleaned
    return result


def _candidate(people, person):
    """Reuse one unambiguous person without merging namesakes or office phones."""
    name = tenders.project_key(person['name'])
    emails = {v.casefold() for v in person['emails']}
    phones = {key for v in person['phones'] if (key := phone_key(v))}
    matches = []
    for old in people:
        old_name = tenders.project_key(old['name'])
        old_emails = {v.casefold() for v in old['emails']}
        old_phones = {key for v in old['phones'] if (key := phone_key(v))}
        if name and old_name and name != old_name:
            continue
        same_email = bool(emails & old_emails)
        same_phone = bool(phones & old_phones)
        conflicting_emails = bool(emails and old_emails and not same_email)
        conflicting_phones = bool(phones and old_phones and not same_phone)
        if same_email or (same_phone and not conflicting_emails):
            matches.append(old)
        elif name and name == old_name and not conflicting_emails and not conflicting_phones:
            # A name-only entry can be enriched, but two records with different
            # known identifiers never collapse solely because names match.
            if not (emails or phones) or not (old_emails or old_phones):
                matches.append(old)
    return matches[0] if len(matches) == 1 else None


def sync_contacts(db, builder, raw, *, legacy=False, touch=True):
    """Upsert selected people and return canonical records; never delete others."""
    builder = tenders.text(builder, 'Builder', required=True, limit=1000)
    key = tenders.builder_key(builder)
    if not key:
        raise tenders.ValidationError('Enter a valid builder name.')
    retained_list = isinstance(raw, list) and len(raw) <= 100 and all(isinstance(person, dict) and person.get('id') for person in raw)
    if not isinstance(raw, list) or (not legacy and len(raw) > 20 and not retained_list):
        raise tenders.ValidationError('Choose up to 20 contacts per builder.')
    people = [_contact(row) for row in db.execute('SELECT * FROM builder_contacts WHERE builder_key=?', (key,))]
    selected, selected_ids, changed = [], set(), False
    for value in raw:
        current = None
        if isinstance(value, dict) and value.get('id'):
            identifier = tenders.text(value.get('id'), 'Contact ID', required=True, limit=100)
            if db.execute('SELECT 1 FROM builder_contact_deletions WHERE id=?', (identifier,)).fetchone():
                raise tenders.ValidationError('This contact was deleted. Refresh the contact list before saving.', 409)
        if not legacy and isinstance(value, dict) and value.get('id'):
            identifier = tenders.text(value.get('id'), 'Contact ID', required=True, limit=100)
            row = db.execute('SELECT * FROM builder_contacts WHERE id=?', (identifier,)).fetchone()
            if not row or row['builder_key'] != key:
                raise tenders.ValidationError('This contact does not belong to the selected builder.', 400)
            current = _contact(row)
        person = _legacy_person(value) if legacy else _validate_person(value, current)
        if not person or not (person['name'] or person['phones'] or person['emails']):
            continue
        if current is not None:
            if _detail(person) != _detail(current):
                if type(person.get('revision')) is not int or person['revision'] != current['revision']:
                    raise tenders.ValidationError('This contact changed in another window. Refresh and choose it again before saving.', 409)
                current = {**_detail(person), 'id': current['id'], 'revision': current['revision'] + 1}
                db.execute('UPDATE builder_contacts SET body=?,revision=? WHERE id=?',
                           (json.dumps(_detail(current), ensure_ascii=False), current['revision'], current['id']))
                changed = True
        else:
            current = _candidate(people, person)
            if current is not None:
                merged = {'name': current['name'] or person['name'],
                          'phones': _unique(current['phones'] + person['phones'], 'phones'),
                          'emails': _unique(current['emails'] + person['emails'], 'emails')}
                if merged != _detail(current):
                    current = {**merged, 'id': current['id'], 'revision': current['revision'] + 1}
                    db.execute('UPDATE builder_contacts SET body=?,revision=? WHERE id=?',
                               (json.dumps(merged, ensure_ascii=False), current['revision'], current['id']))
                    changed = True
            else:
                current = {**_detail(person), 'id': str(uuid.uuid4()), 'revision': 0}
                db.execute('INSERT INTO builder_contacts(id,builder_key,builder,body,revision) VALUES(?,?,?,?,0)',
                           (current['id'], key, builder, json.dumps(_detail(current), ensure_ascii=False)))
                changed = True
        people = [p for p in people if p['id'] != current['id']] + [current]
        if current['id'] not in selected_ids:
            selected.append(current)
            selected_ids.add(current['id'])
    if changed and touch:
        _touch(db)
    # A later occurrence may have enriched a person already selected earlier.
    latest = {person['id']: person for person in people}
    return [latest[person['id']] for person in selected]


def _links(db, kind, identifier, builder):
    return [_contact(row) for row in db.execute('''SELECT c.* FROM builder_contact_links l
        JOIN builder_contacts c ON c.id=l.contact_id
        WHERE l.source_kind=? AND l.source_id=? AND l.builder_key=?
        ORDER BY l.position''', (kind, identifier, tenders.builder_key(builder)))]


def _set_links(db, kind, identifier, builder, people):
    key = tenders.builder_key(builder)
    ids = [person['id'] for person in people]
    previous = [row[0] for row in db.execute('''SELECT contact_id FROM builder_contact_links
        WHERE source_kind=? AND source_id=? AND builder_key=? ORDER BY position''', (kind, identifier, key))]
    if previous == ids:
        return False
    db.execute('DELETE FROM builder_contact_links WHERE source_kind=? AND source_id=? AND builder_key=?', (kind, identifier, key))
    db.executemany('''INSERT INTO builder_contact_links(source_kind,source_id,builder_key,position,contact_id)
        VALUES(?,?,?,?,?)''', [(kind, identifier, key, position, person['id']) for position, person in enumerate(people)])
    return True


def _linked_opportunity(db, item):
    identifier = item.get('opportunityId')
    if identifier:
        row = db.execute('SELECT * FROM opportunities WHERE id=? AND deleted_at IS NULL', (identifier,)).fetchone()
        if row:
            return row
    # Older explicitly linked records have only the reverse submissionIds list.
    matches = []
    for row in db.execute('SELECT * FROM opportunities WHERE deleted_at IS NULL'):
        if item.get('id') in (json.loads(row['body']).get('submissionIds') or []):
            matches.append(row)
    return matches[0] if len(matches) == 1 else None


def _apply_submission_fields(item, people):
    first = people[0] if people else {}
    item.update(contacts=people, awardContacts=people,
                contact=first.get('name', ''), email=next(iter(first.get('emails', [])), ''),
                **tenders.awarded_legacy_fields(people))


def submission_view(db, item):
    result = dict(item)
    people = _links(db, 'submission', item['id'], item.get('builder', ''))
    # Missing selections are deliberately empty after a removal. An id-less
    # original row only falls back when no structured list was ever saved.
    if not people and 'contacts' not in item and 'awardContacts' not in item:
        people = _legacy_submission_contacts(item)
    _apply_submission_fields(result, people)
    return result


def opportunity_view(db, item):
    result = dict(item)
    result['builderContacts'] = [{'builder': builder,
        'contacts': _links(db, 'opportunity', item['id'], builder)} for builder in item.get('builders', [])]
    return result


def validate_groups(raw, builders):
    if not isinstance(raw, list) or len(raw) > 100:
        raise tenders.ValidationError('Choose contacts for up to 100 builders.')
    available = {tenders.builder_key(name): name for name in builders}
    groups, seen = [], set()
    for group in raw:
        if not isinstance(group, dict):
            raise tenders.ValidationError('Invalid builder contact group.')
        builder = tenders.text(group.get('builder'), 'Builder', required=True, limit=1000)
        key = tenders.builder_key(builder)
        if key not in available or key in seen:
            raise tenders.ValidationError('Choose contacts only for builders selected on this project, once each.')
        contacts = group.get('contacts', [])
        retained_list = isinstance(contacts, list) and len(contacts) <= 100 and all(isinstance(person, dict) and person.get('id') for person in contacts)
        if not isinstance(contacts, list) or (len(contacts) > 20 and not retained_list):
            raise tenders.ValidationError('Choose up to 20 contacts per builder.')
        groups.append({'builder': available[key], 'contacts': contacts})
        seen.add(key)
    return groups


def save_submission_selection(store, db, item, people, actor_id=None, actor_name='', *, propagate=True):
    changed = _set_links(db, 'submission', item['id'], item['builder'], people)
    # A changed builder must not leave links to the previous company.
    db.execute("DELETE FROM builder_contact_links WHERE source_kind='submission' AND source_id=? AND builder_key!=?",
               (item['id'], tenders.builder_key(item['builder'])))
    _apply_submission_fields(item, people)
    if not propagate or not changed:
        return
    row = _linked_opportunity(db, item)
    if not row:
        return
    opportunity = json.loads(row['body'])
    if tenders.builder_key(item['builder']) not in {tenders.builder_key(v) for v in opportunity.get('builders', [])}:
        return
    if _set_links(db, 'opportunity', row['id'], item['builder'], people):
        opportunity = opportunity_view(db, opportunity)
        opportunity.update(revision=row['revision'] + 1, updatedAt=tenders.timestamp(),
                           updatedBy=actor_id, updatedByName=actor_name)
        db.execute('UPDATE opportunities SET body=?,revision=?,updated_at=? WHERE id=?',
                   (json.dumps(opportunity, ensure_ascii=False), opportunity['revision'], opportunity['updatedAt'], row['id']))
        db.execute('UPDATE opportunity_generation SET value=value+1')
        from . import opportunities as op
        op._activity(store, db, {'id': actor_id or 0, 'name': actor_name or 'System'},
                     'Updated shared builder contacts', opportunity, {'builder': item['builder'], 'submissionId': item['id']})


def save_opportunity_selection(store, db, item, groups, actor):
    canonical = []
    grouped = {tenders.builder_key(group['builder']): group for group in groups}
    for builder in item.get('builders', []):
        group = grouped.get(tenders.builder_key(builder), {'contacts': []})
        people = sync_contacts(db, builder, group['contacts'])
        changed = _set_links(db, 'opportunity', item['id'], builder, people)
        canonical.append({'builder': builder, 'contacts': people})
        if not changed:
            continue
        for row in db.execute('SELECT * FROM submissions').fetchall():
            submission = json.loads(row['body'])
            if tenders.builder_key(submission.get('builder')) != tenders.builder_key(builder):
                continue
            if submission.get('opportunityId') != item['id'] and row['id'] not in (item.get('submissionIds') or []):
                continue
            if _set_links(db, 'submission', row['id'], builder, people):
                _apply_submission_fields(submission, people)
                submission.update(revision=row['revision'] + 1, updatedAt=tenders.timestamp(),
                                  updatedBy=actor['id'], updatedByName=actor['name'])
                db.execute('UPDATE submissions SET body=?,revision=? WHERE id=?',
                           (json.dumps(submission, ensure_ascii=False), submission['revision'], row['id']))
                store.activity(db, actor['id'], actor['name'], 'Updated shared builder contacts', submission,
                               {'opportunityId': item['id']})
                db.execute('UPDATE tender_generation SET value=value+1')
    keep = {tenders.builder_key(name) for name in item.get('builders', [])}
    for row in db.execute("SELECT DISTINCT builder_key FROM builder_contact_links WHERE source_kind='opportunity' AND source_id=?", (item['id'],)).fetchall():
        if row['builder_key'] not in keep:
            db.execute("DELETE FROM builder_contact_links WHERE source_kind='opportunity' AND source_id=? AND builder_key=?", (item['id'], row['builder_key']))
    item['builderContacts'] = canonical


def register_imported_submission(store, db, item, previous, changed_fields, actor):
    """Share imported primary contact data while preserving additional people."""
    if previous and not {'contact', 'email', 'builder'}.intersection(changed_fields):
        return
    people = []
    if previous and tenders.builder_key(previous.get('builder')) == tenders.builder_key(item.get('builder')):
        people = submission_view(db, previous)['contacts']
    primary = dict(people[0]) if people else {'name': '', 'phones': [], 'emails': []}
    primary['name'] = item.get('contact') or ''
    emails = [v.strip() for v in re.split(r'[,;\n]+', item.get('email') or '') if v.strip()]
    primary['emails'] = _unique(emails + primary.get('emails', [])[1:], 'emails')
    selected = sync_contacts(db, item['builder'], [primary] + people[1:], legacy=True)
    save_submission_selection(store, db, item, selected, actor['id'], actor['name'])


def share_linked_project_contacts(store, db, item, submissions, actor):
    """Merge selections only when an explicit opportunity/project link is made."""
    groups = opportunity_view(db, item)['builderContacts']
    by_builder = {tenders.builder_key(group['builder']): group for group in groups}
    for submission in submissions:
        builder = submission['builder']
        key = tenders.builder_key(builder)
        if key not in by_builder:
            item.setdefault('builders', []).append(builder)
            group = {'builder': builder, 'contacts': []}
            groups.append(group)
            by_builder[key] = group
        group = by_builder[key]
        seen = {person['id'] for person in group['contacts']}
        for person in submission_view(db, submission)['contacts']:
            if person.get('id') not in seen:
                group['contacts'].append(person)
                seen.add(person.get('id'))
    save_opportunity_selection(store, db, item, groups, actor)


def initialize(store):
    if getattr(store, '_builder_contacts_ready', False):
        return
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('''CREATE TABLE IF NOT EXISTS builder_contacts (
            id TEXT PRIMARY KEY, builder_key TEXT NOT NULL, builder TEXT NOT NULL,
            body TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0)''')
        db.execute('CREATE INDEX IF NOT EXISTS builder_contacts_builder ON builder_contacts(builder_key)')
        db.execute('''CREATE TABLE IF NOT EXISTS builder_contact_links (
            source_kind TEXT NOT NULL, source_id TEXT NOT NULL, builder_key TEXT NOT NULL,
            position INTEGER NOT NULL, contact_id TEXT NOT NULL REFERENCES builder_contacts(id),
            PRIMARY KEY(source_kind,source_id,builder_key,position))''')
        db.execute('CREATE INDEX IF NOT EXISTS builder_contact_links_contact ON builder_contact_links(contact_id)')
        db.execute('''CREATE TABLE IF NOT EXISTS builder_contact_deletions (
            id TEXT PRIMARY KEY, builder_key TEXT NOT NULL,
            deleted_at TEXT NOT NULL, deleted_by INTEGER NOT NULL)''')
        if not db.execute('SELECT 1 FROM settings WHERE id=?', (MARKER,)).fetchone():
            submissions = [json.loads(row['body']) for row in db.execute('SELECT body FROM submissions')]
            for item in submissions:
                if not item.get('builder'):
                    continue
                people = sync_contacts(db, item['builder'], _legacy_submission_contacts(item), legacy=True, touch=False)
                _set_links(db, 'submission', item['id'], item['builder'], people)
            from .opportunity_retention import active_sql
            for row in db.execute('SELECT id,body FROM opportunities WHERE deleted_at IS NULL AND ' + active_sql('opportunity', 'opportunities.id')).fetchall():
                item = json.loads(row['body'])
                groups = item.get('builderContacts') if isinstance(item.get('builderContacts'), list) else []
                for builder in item.get('builders', []):
                    people = []
                    for group in groups:
                        if isinstance(group, dict) and tenders.builder_key(group.get('builder')) == tenders.builder_key(builder):
                            people += group.get('contacts') or []
                    if len(item.get('builders', [])) == 1:
                        people += legacy_tender_contacts(item)
                    for submission in submissions:
                        if tenders.builder_key(submission.get('builder')) != tenders.builder_key(builder):
                            continue
                        if submission.get('opportunityId') == row['id'] or submission['id'] in (item.get('submissionIds') or []):
                            people += _links(db, 'submission', submission['id'], builder)
                    canonical = sync_contacts(db, builder, people, legacy=True, touch=False)
                    _set_links(db, 'opportunity', row['id'], builder, canonical)
                    for submission in submissions:
                        if tenders.builder_key(submission.get('builder')) == tenders.builder_key(builder) and (
                                submission.get('opportunityId') == row['id'] or submission['id'] in (item.get('submissionIds') or [])):
                            _set_links(db, 'submission', submission['id'], builder, canonical)
            db.execute('INSERT INTO settings(id,body) VALUES(?,?)', (MARKER, json.dumps({'createdAt': tenders.timestamp()})))
            _touch(db)
    store._builder_contacts_ready = True


def _delete_access(user):
    """Resolve live membership and actual project assignments, never UI flags."""
    from .database import connect as account_connection
    from .builders import read_builders
    if not isinstance(user, dict) or type(user.get('id')) is not int:
        raise tenders.ValidationError('An active account is required.', 403)
    with account_connection() as db:
        row = db.execute('SELECT id,name,role,is_active,team_id FROM users WHERE id=?', (user['id'],)).fetchone()
        if not row or not row['is_active']:
            raise tenders.ValidationError('Your account is no longer active. Sign in again.', 403)
        actor = dict(row)
        teams = {row[0] for row in db.execute('SELECT id FROM teams')}
        memberships = {row[0] for row in db.execute('SELECT team_id FROM user_team_memberships WHERE user_id=?', (actor['id'],))} & teams
        if not memberships and actor['team_id'] in teams:
            memberships.add(actor['team_id'])
        # project_user_access is the current table of explicit editors. The
        # older project_assignments table is historical and is not a grant.
        clauses = ['EXISTS (SELECT 1 FROM project_user_access a WHERE a.project_id=p.id AND a.user_id=?)']
        args = [actor['id']]
        if memberships:
            clauses.append('EXISTS (SELECT 1 FROM project_teams a WHERE a.project_id=p.id AND a.team_id IN (' + ','.join('?' for _ in memberships) + '))')
            args.extend(sorted(memberships))
        projects = db.execute('SELECT p.id,p.client FROM projects p WHERE ' + ' OR '.join(clauses), args).fetchall()
        project_ids = {row['id'] for row in projects}
        builder_keys = {tenders.builder_key(name) for row in projects for name in read_builders({'client': row['client']})}
    return {'actor': actor, 'memberships': memberships, 'projectIds': project_ids, 'builderKeys': builder_keys}


def _deletable_builders(db, access):
    from .opportunity_retention import active_sql
    allowed = set(access['builderKeys'])
    actor_id = access['actor']['id']
    for row in db.execute('SELECT body FROM opportunities WHERE deleted_at IS NULL AND ' + active_sql('opportunity', 'opportunities.id')):
        item = json.loads(row['body'])
        assigned_teams = {value for value in (item.get('assignedTeamIds') or []) if type(value) is int}
        assigned_people = {value for value in (item.get('assignedUserIds') or []) if type(value) is int}
        project_id = item.get('estimatorProjectId')
        linked_project = type(project_id) is int and project_id in access['projectIds']
        if (actor_id in assigned_people or assigned_teams & access['memberships'] or linked_project):
            allowed.update(tenders.builder_key(name) for name in (item.get('builders') or []) if isinstance(name, str) and name.strip())
    return allowed


def directory(store, user=None):
    initialize(store)
    access = _delete_access(user) if user is not None else None
    from .opportunity_retention import active_sql
    with store.connect() as db:
        db.execute('BEGIN')
        allowed = _deletable_builders(db, access) if access and access['actor']['role'] != 'admin' else set()
        builders = {row['builder_key']: {'builder': row['name'], 'contacts': []} for row in db.execute(
            'SELECT builder_key,name FROM opportunity_builders WHERE ' + active_sql('builder', 'opportunity_builders.builder_key'))}
        for row in db.execute('SELECT body FROM submissions'):
            name = json.loads(row['body']).get('builder', '')
            if name:
                builders.setdefault(tenders.builder_key(name), {'builder': name, 'contacts': []})
        for row in db.execute('SELECT * FROM builder_contacts ORDER BY builder COLLATE NOCASE,id'):
            group = builders.setdefault(row['builder_key'], {'builder': row['builder'], 'contacts': []})
            person = _contact(row)
            if access is not None:
                person['canDelete'] = access['actor']['role'] == 'admin' or row['builder_key'] in allowed
            group['contacts'].append(person)
        for group in builders.values():
            group['contacts'].sort(key=lambda person: (person['name'].casefold(), ';'.join(person['emails']).casefold(), person['id']))
        return {'builders': sorted(builders.values(), key=lambda group: group['builder'].casefold())}


def save(store, payload, user):
    initialize(store)
    from . import opportunities as op
    _, users = op.directory()
    actor = op._actor(user, users)
    builder = tenders.text(payload.get('builder'), 'Builder', required=True, limit=1000)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        before = db.total_changes
        people = sync_contacts(db, builder, payload.get('contacts', []))
        if db.total_changes != before:
            store.activity(db, actor['id'], actor['name'], 'Updated builder contacts', details={'builder': builder, 'contactIds': [p['id'] for p in people]})
    return directory(store, user)


def _mentions_deleted(people, deleted, *, match_legacy=True):
    if not isinstance(people, list):
        return False
    for raw in people:
        if not isinstance(raw, dict):
            continue
        if raw.get('id') == deleted['id']:
            return True
        if match_legacy and not raw.get('id'):
            person = _legacy_person(raw)
            if person and _candidate([deleted], person) is not None:
                return True
    return False


def _without_deleted_snapshot(people, deleted, *, match_legacy=True):
    """Filter one person without normalising other historical snapshot fields."""
    if not isinstance(people, list):
        return people
    return [person for person in people
            if not _mentions_deleted([person], deleted, match_legacy=match_legacy)]


def delete(store, payload, user):
    """Delete one shared person and every current assignment in one transaction."""
    initialize(store)
    access = _delete_access(user)
    actor = access['actor']
    identifier = tenders.text(payload.get('id'), 'Contact ID', required=True, limit=100)
    revision = payload.get('revision')
    if type(revision) is not int or revision < 0:
        raise tenders.ValidationError('Choose the current contact before deleting it.', 409)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM builder_contacts WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise tenders.ValidationError('This contact no longer exists. Refresh the contact list.', 404)
        key, builder, deleted = row['builder_key'], row['builder'], _contact(row)
        if actor['role'] != 'admin' and key not in _deletable_builders(db, access):
            raise tenders.ValidationError('Only an administrator or a user assigned to this builder’s opportunities or projects can delete its contacts.', 403)
        if revision != row['revision']:
            raise tenders.ValidationError('This contact changed in another window. Refresh it before deleting.', 409)
        linked = {(r['source_kind'], r['source_id']) for r in db.execute('SELECT source_kind,source_id FROM builder_contact_links WHERE contact_id=?', (identifier,))}
        # Retired/deleted Opportunities were intentionally not migrated to
        # sidecar links. Distinguish those original snapshots from selections
        # that were canonical even when deleting their final link below.
        canonical_opportunity_groups = {(r['source_id'], r['builder_key']) for r in db.execute(
            "SELECT DISTINCT source_id,builder_key FROM builder_contact_links WHERE source_kind='opportunity'")}
        db.execute('DELETE FROM builder_contact_links WHERE contact_id=?', (identifier,))
        moment = tenders.timestamp()
        changed_submissions, changed_opportunities = [], []
        for source in db.execute('SELECT * FROM submissions').fetchall():
            item = json.loads(source['body'])
            item['id'] = source['id']
            same_builder = tenders.builder_key(item.get('builder')) == key
            explicit = any(_mentions_deleted(item.get(field), deleted) for field in ('contacts', 'awardContacts')) if same_builder else any(
                isinstance(person, dict) and person.get('id') == identifier
                for field in ('contacts', 'awardContacts') for person in (item.get(field) if isinstance(item.get(field), list) else []))
            legacy_people = []
            if not isinstance(item.get('contacts'), list):
                legacy_people += legacy_tender_contacts(item)
            if not isinstance(item.get('awardContacts'), list):
                legacy_people += tenders.awarded_contacts_from(item)
            legacy = same_builder and _mentions_deleted(legacy_people, deleted)
            if ('submission', source['id']) not in linked and not explicit and not legacy:
                continue
            # Read links directly: fallback to original legacy JSON would
            # otherwise resurrect a deleted final contact on old submissions.
            people = _links(db, 'submission', source['id'], item.get('builder', ''))
            _apply_submission_fields(item, people)
            if 'phone' in item:
                item['phone'] = next(iter(people[0]['phones']), '') if people else ''
            item.update(revision=source['revision'] + 1, updatedAt=moment, updatedBy=actor['id'], updatedByName=actor['name'])
            db.execute('UPDATE submissions SET body=?,revision=? WHERE id=?', (json.dumps(item, ensure_ascii=False), item['revision'], source['id']))
            store.activity(db, actor['id'], actor['name'], 'Deleted shared builder contact', item,
                           {'contactId': identifier, 'builder': builder})
            changed_submissions.append(source['id'])
        from . import opportunities as op
        for source in db.execute('SELECT * FROM opportunities').fetchall():
            item = json.loads(source['body'])
            # Some preserved legacy bodies omit id; the SQL primary key is
            # authoritative for link cleanup, revision writes and audit rows.
            item['id'] = source['id']
            groups = item.get('builderContacts') if isinstance(item.get('builderContacts'), list) else []
            names = item.get('builders') if isinstance(item.get('builders'), list) else []
            single_builder = len(names) == 1 and isinstance(names[0], str) and tenders.builder_key(names[0]) == key
            explicit = any(isinstance(group, dict) and isinstance(group.get('builder'), str)
                           and _mentions_deleted(group.get('contacts'), deleted,
                               match_legacy=tenders.builder_key(group['builder']) == key) for group in groups)
            legacy_array = _mentions_deleted(item.get('contacts'), deleted, match_legacy=single_builder)
            legacy_scalar = single_builder and _mentions_deleted(legacy_tender_contacts(
                {field: item.get(field) for field in ('contact', 'email', 'phone')}), deleted)
            legacy = legacy_array or legacy_scalar
            if ('opportunity', source['id']) not in linked and not explicit and not legacy:
                continue
            updated_groups, has_target_group = [], False
            for group in groups:
                if not isinstance(group, dict) or not isinstance(group.get('builder'), str):
                    updated_groups.append(group)
                    continue
                group_key = tenders.builder_key(group['builder'])
                has_target_group |= group_key == key
                affected = _mentions_deleted(group.get('contacts'), deleted, match_legacy=group_key == key)
                canonical = (source['id'], group_key) in canonical_opportunity_groups
                if affected or (canonical and group_key == key and ('opportunity', source['id']) in linked):
                    people = (_links(db, 'opportunity', source['id'], group['builder']) if canonical else
                              _without_deleted_snapshot(group.get('contacts'), deleted, match_legacy=group_key == key))
                    updated_groups.append({**group, 'contacts': people})
                else:
                    updated_groups.append(group)
            # Migrated legacy records may have sidecar selections without a
            # builderContacts JSON property. Only materialise the affected
            # canonical group; unrelated archived snapshots stay untouched.
            if not has_target_group and (source['id'], key) in canonical_opportunity_groups:
                current_name = next((name for name in names if isinstance(name, str) and tenders.builder_key(name) == key), None)
                if current_name:
                    updated_groups.append({'builder': current_name, 'contacts': _links(db, 'opportunity', source['id'], current_name)})
            if 'builderContacts' in item or updated_groups:
                item['builderContacts'] = updated_groups
            if legacy_array:
                item['contacts'] = _without_deleted_snapshot(item['contacts'], deleted, match_legacy=single_builder)
            if legacy_scalar:
                remaining = item.get('contacts') if isinstance(item.get('contacts'), list) else []
                if not remaining:
                    remaining = next((group.get('contacts', []) for group in updated_groups if isinstance(group, dict)
                                      and isinstance(group.get('builder'), str) and tenders.builder_key(group['builder']) == key), [])
                first = _legacy_person(remaining[0]) if isinstance(remaining, list) and remaining else None
                replacements = {'contact': first['name'] if first else '',
                                'email': next(iter(first['emails']), '') if first else '',
                                'phone': next(iter(first['phones']), '') if first else ''}
                for field, value in replacements.items():
                    if field in item:
                        item[field] = value
            item.update(revision=source['revision'] + 1, updatedAt=moment, updatedBy=actor['id'], updatedByName=actor['name'])
            db.execute('UPDATE opportunities SET body=?,revision=?,updated_at=? WHERE id=?',
                       (json.dumps(item, ensure_ascii=False), item['revision'], moment, source['id']))
            op._activity(store, db, actor, 'Deleted shared builder contact', item,
                         {'contactId': identifier, 'builder': builder})
            changed_opportunities.append(source['id'])
        db.execute('INSERT INTO builder_contact_deletions(id,builder_key,deleted_at,deleted_by) VALUES(?,?,?,?)', (identifier, key, moment, actor['id']))
        db.execute('DELETE FROM builder_contacts WHERE id=?', (identifier,))
        store.activity(db, actor['id'], actor['name'], 'Deleted builder directory contact',
                       details={'contactId': identifier, 'builder': builder,
                                'submissionIds': changed_submissions, 'opportunityIds': changed_opportunities})
        _touch(db)
    return {'ok': True, 'deletedId': identifier, **directory(store, user)}


def export_workbook(store):
    """Literal Excel cells prevent contact data being interpreted as formulas."""
    from .tender_export import NS, MIME, cell, styles
    rows = [[group['builder'], person['name'], '\n'.join(person['phones']), '\n'.join(person['emails'])]
            for group in directory(store)['builders'] for person in group['contacts']]
    generated = 'Exported ' + datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')
    values = [['TEC Flow — Builder Contacts', '', '', ''], [generated, '', '', ''],
              ['Builder', 'Contact person', 'Phone numbers', 'Email addresses'], *rows]
    content = ''.join('<row r="' + str(i) + '" ht="' + str(32 if i <= 3 else max(34, min(210, 18 * max(str(v).count('\n') + 1 for v in row) + 12))) + '" customHeight="1">' +
                      ''.join(cell(f'{chr(64 + j)}{i}', v, 1 if i == 1 else 2 if i == 2 else 3 if i == 3 else 5 if i % 2 == 0 else 6)
                              for j, v in enumerate(row, 1)) + '</row>' for i, row in enumerate(values, 1))
    last = max(3, len(values))
    sheet = f'''<worksheet xmlns="{NS}"><dimension ref="A1:D{last}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="42" customWidth="1"/><col min="2" max="2" width="28" customWidth="1"/><col min="3" max="3" width="30" customWidth="1"/><col min="4" max="4" width="45" customWidth="1"/></cols><sheetData>{content}</sheetData><autoFilter ref="A3:D{last}"/><mergeCells count="2"><mergeCell ref="A1:D1"/><mergeCell ref="A2:D2"/></mergeCells><pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/><pageSetup orientation="landscape" paperSize="9" fitToWidth="1" fitToHeight="0"/></worksheet>'''
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="{MIME}.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="{MIME}.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="{MIME}.worksheet+xml"/></Types>')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Builder Contacts" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/styles.xml', styles())
        archive.writestr('xl/worksheets/sheet1.xml', sheet)
    return output.getvalue()
