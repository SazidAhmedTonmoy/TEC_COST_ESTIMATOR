"""Shared contact deletion: live assignment authority and atomic cleanup."""
from contextlib import contextmanager
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from conest_app import accounts, builder_contacts, tenders
from conest_app.database import connect
from conest_app.projects import create_project
from conest_app.teams import set_user_teams
import support_http as helpers


class BuilderContactDeleteTests(unittest.TestCase):
    request = helpers.HttpPatchTests.request

    def setUp(self):
        tenders.close_store()
        helpers.HttpPatchTests.setUp(self)
        self.tender_env = patch.dict('os.environ', {
            'CONEST_TENDERS_DB_PATH': str(Path(self.tmp.name) / 'contact-delete.db')})
        self.tender_env.start()
        self.sequence = 0
        with connect() as db:
            self.admin = dict(db.execute('SELECT id,name,role,team_id FROM users WHERE id=?', (self.user_id,)).fetchone())
            now = tenders.timestamp()
            self.team = db.execute('INSERT INTO teams(name,created_at,updated_at) VALUES(?,?,?)', ('Contact assigned team', now, now)).lastrowid
            self.other_team = db.execute('INSERT INTO teams(name,created_at,updated_at) VALUES(?,?,?)', ('Contact other team', now, now)).lastrowid
            self.member = self.user(db, 'contact-member', self.team)
            self.second_member = self.user(db, 'contact-second', self.team)
            self.secondary_member = self.user(db, 'contact-secondary', self.other_team)
            set_user_teams(db, self.secondary_member['id'], [self.other_team, self.team], self.other_team)
            self.outsider = self.user(db, 'contact-outsider', self.other_team)
            self.direct = self.user(db, 'contact-direct', None)
            self.other_admin = self.user(db, 'contact-admin', None, role='admin')
        self.store = tenders.get_store()

    def tearDown(self):
        tenders.close_store()
        self.tender_env.stop()
        helpers.HttpPatchTests.tearDown(self)

    @staticmethod
    def user(db, name, team, role='user'):
        now = tenders.timestamp()
        identifier = db.execute('''INSERT INTO users(username,name,password_hash,role,team_id,is_active,must_change_password,created_at,updated_at)
            VALUES(?,?,?,?,?,1,0,?,?)''', (name, name, 'not-a-login-password', role, team, now, now)).lastrowid
        if team is not None:
            set_user_teams(db, identifier, [team], team)
        return {'id': identifier, 'name': name, 'role': role, 'team_id': team}

    @contextmanager
    def as_user(self, user):
        previous = self.cookie, self.csrf
        with connect() as db:
            token = accounts.start_session(db, user['id'])
        self.cookie, self.csrf = 'conest_session=' + token, accounts.csrf_token(token)
        try:
            yield
        finally:
            self.cookie, self.csrf = previous

    def post(self, path, payload):
        status, data = self.request('POST', '/api/tenders/' + path, payload)
        self.assertEqual(status, 200, data)
        return data

    def people(self, builder='Delete Builder'):
        status, data = self.request('GET', '/api/tenders/builder-contacts')
        self.assertEqual(status, 200, data)
        return next((group['contacts'] for group in data['builders'] if group['builder'] == builder), [])

    def person(self, name='Remove person', builder='Delete Builder'):
        self.post('builder-contacts', {'builder': builder,
            'contacts': [{'name': name, 'phones': ['0412 333 444'], 'emails': [name.lower().replace(' ', '.') + '@example.test']}]})
        return next(person for person in self.people(builder) if person['name'] == name)

    def opportunity(self, **fields):
        self.sequence += 1
        return self.post('opportunities/save', {'project': 'Deletion opportunity ' + str(self.sequence),
            'region': 'NSW', 'builders': ['Delete Builder'], 'due': '2099-12-01', **fields})['opportunity']

    def tender(self, **fields):
        self.sequence += 1
        return self.post('submissions', {'project': 'Deletion tender ' + str(self.sequence),
            'builder': 'Delete Builder', 'status': 'Open', 'builderStatus': 'Awarded', 'region': 'NSW',
            'due': '2099-12-01', 'value': 27500, 'quoteNo': 'Q-Delete-Test', **fields})['submission']

    def remove(self, person, status=200):
        actual, data = self.request('DELETE', '/api/tenders/builder-contacts', {'id': person['id'], 'revision': person['revision']})
        self.assertEqual(actual, status, data)
        return data

    def test_all_admins_and_every_assigned_team_member_including_secondary_membership(self):
        self.opportunity(assignedTeamIds=[self.team])
        for actor in (self.admin, self.other_admin, self.member, self.second_member, self.secondary_member):
            person = self.person('Person ' + str(actor['id']))
            with self.as_user(actor):
                current = next(p for p in self.people() if p['id'] == person['id'])
                self.assertTrue(current['canDelete'])
                result = self.remove(current)
                self.assertEqual(result['deletedId'], current['id'])
        # Administrator authority also applies to an unassigned directory entry.
        orphan = self.person('Unassigned directory', 'Orphan Builder')
        with self.as_user(self.other_admin):
            self.assertTrue(self.people('Orphan Builder')[0]['canDelete'])
            self.remove(orphan)

    def test_direct_opportunity_assignee_allowed_but_creator_and_other_team_are_not(self):
        person = self.person()
        self.opportunity(assignedTeamIds=[self.team], assignedUserIds=[self.direct['id']])
        with self.as_user(self.outsider):
            self.assertFalse(self.people()[0]['canDelete'])
            self.remove(person, 403)
        with self.as_user(self.direct):
            self.assertTrue(self.people()[0]['canDelete'])
            self.remove(person)
        creator_only = self.person('Creator only', 'Creator Builder')
        with self.as_user(self.direct):
            self.opportunity(builders=['Creator Builder'])
            self.assertFalse(self.people('Creator Builder')[0]['canDelete'])
            self.remove(creator_only, 403)

    def test_attribution_unrelated_project_and_obsolete_assignments_do_not_grant_delete(self):
        person = self.person()
        self.tender(contacts=[person], submittedByTeam='Contact assigned team')
        self.opportunity(builders=['Another Builder'], assignedTeamIds=[self.team])
        with connect() as db:
            project = create_project(db, {'name': 'Old assignment', 'builders': ['Delete Builder']})['project']
            db.execute('INSERT INTO project_assignments(project_id,user_id,assigned_by,assigned_at) VALUES(?,?,?,?)',
                       (project['id'], self.member['id'], self.admin['id'], tenders.timestamp()))
        with self.as_user(self.member):
            self.assertFalse(self.people()[0]['canDelete'])
            self.remove(person, 403)
        # Claimed roles/memberships in a caller object are never authority.
        with self.assertRaises(tenders.ValidationError) as caught:
            builder_contacts.delete(self.store, person, {**self.outsider, 'role': 'admin', 'team_ids': [self.team]})
        self.assertEqual(caught.exception.status, 403)

    def test_current_estimator_team_and_explicit_editor_assignments_grant_delete(self):
        with connect() as db:
            project = create_project(db, {'name': 'Assigned estimate', 'builders': ['Delete Builder']})['project']
            db.execute('INSERT INTO project_teams VALUES(?,?,?,?)', (project['id'], self.team, self.admin['id'], tenders.timestamp()))
            db.execute('INSERT INTO project_user_access VALUES(?,?,?,?)', (project['id'], self.direct['id'], self.admin['id'], tenders.timestamp()))
        for actor in (self.secondary_member, self.direct):
            person = self.person('Estimator person ' + str(actor['id']))
            with self.as_user(actor):
                self.assertTrue(next(p for p in self.people() if p['id'] == person['id'])['canDelete'])
                self.remove(person)
        person = self.person('Read access only')
        with self.as_user(self.outsider):
            self.assertFalse(self.people()[0]['canDelete'])
            self.remove(person, 403)

    def test_explicit_estimator_link_grants_access_but_matching_project_name_does_not(self):
        with connect() as db:
            project = create_project(db, {'name': 'Identical name', 'builders': ['Different Builder']})['project']
            db.execute('INSERT INTO project_teams VALUES(?,?,?,?)', (project['id'], self.team, self.admin['id'], tenders.timestamp()))
        opportunity = self.opportunity(project='Identical name')
        person = self.person()
        with self.as_user(self.member):
            self.assertFalse(self.people()[0]['canDelete'])
            self.remove(person, 403)
        self.post('opportunities/estimator-link', {'id': opportunity['id'], 'revision': opportunity['revision'], 'estimatorProjectId': project['id']})
        with self.as_user(self.member):
            self.assertTrue(self.people()[0]['canDelete'])
            self.remove(person)

    def test_membership_removal_and_deleted_opportunities_revoke_live_permission(self):
        person = self.person()
        item = self.opportunity(assignedTeamIds=[self.team], assignedUserIds=[self.direct['id']])
        with self.as_user(self.secondary_member):
            self.assertTrue(self.people()[0]['canDelete'])
            with connect() as db:
                set_user_teams(db, self.secondary_member['id'], [self.other_team], self.other_team)
            self.remove(person, 403)
            self.assertFalse(self.people()[0]['canDelete'])
        status, data = self.request('DELETE', '/api/tenders/opportunities', {'id': item['id'], 'revision': item['revision']})
        self.assertEqual(status, 200, data)
        with self.as_user(self.direct):
            self.assertFalse(self.people()[0]['canDelete'])
            self.remove(person, 403)

    def test_authentication_csrf_stale_revision_and_inactive_user_are_enforced(self):
        person = self.person()
        self.assertEqual(self.request('DELETE', '/api/tenders/builder-contacts', person, csrf=False)[0], 403)
        cookie, csrf = self.cookie, self.csrf
        self.cookie = self.csrf = ''
        self.assertEqual(self.request('DELETE', '/api/tenders/builder-contacts', person)[0], 401)
        self.cookie, self.csrf = cookie, csrf
        self.post('builder-contacts', {'builder': 'Delete Builder', 'contacts': [{**person, 'name': 'Revised person'}]})
        self.remove(person, 409)
        current = self.people()[0]
        self.assertEqual(current['name'], 'Revised person')
        with self.as_user(self.other_admin):
            with connect() as db:
                db.execute('UPDATE users SET is_active=0 WHERE id=?', (self.other_admin['id'],))
            self.remove(current, 401)
        self.remove(current)
        self.remove(current, 404)

    def test_global_delete_cleans_links_and_snapshots_and_preserves_other_project_data(self):
        removed = self.person()
        kept = self.person('Keep person')
        other_builder_person = self.person('Remove person', 'Other Builder')
        opportunity = self.opportunity(builders=['Delete Builder', 'Other Builder'], assignedTeamIds=[self.team],
            builderContacts=[{'builder': 'Delete Builder', 'contacts': [removed, kept]},
                             {'builder': 'Other Builder', 'contacts': [other_builder_person]}])
        quoted = self.post('opportunities/quote', {'id': opportunity['id'], 'revision': opportunity['revision'],
            'value': 27500, 'quoteNo': 'Q-Shared-Delete', 'submittedDate': '2099-11-20',
            'builders': ['Delete Builder', 'Other Builder']})
        status, data = self.request('GET', '/api/tenders/data')
        self.assertEqual(status, 200)
        source = next(s for s in data['submissions'] if s['id'] in quoted['submissionIds'] and s['builder'] == 'Delete Builder')
        source = self.post('submissions', {**source, 'builderStatus': 'Awarded'})['submission']
        source = self.post('open-awarded/contact', {'id': source['id'], 'revision': source['revision'],
            'awardedDate': '2099-11-22', 'estStartDate': '2100-02-01', 'awardProjectLink': 'https://example.test/award',
            'awardContacts': source['awardContacts']})['submission']
        self.post('reminders', {'submissionId': source['id'], 'due': '2099-12-02T09:00',
            'note': 'Keep this follow-up', 'repeatEvery14Days': True})
        unlinked = self.tender(contacts=[removed, kept])
        with self.store.connect() as db:
            originals = {r['id']: dict(r) for r in db.execute('SELECT * FROM submissions')}
            reminders = [tuple(r) for r in db.execute('SELECT * FROM reminders ORDER BY id')]
            chases = [tuple(r) for r in db.execute('SELECT * FROM chases ORDER BY id')]
        with self.as_user(self.second_member):
            self.remove(removed)
        self.assertEqual([p['id'] for p in self.people()], [kept['id']])
        self.assertEqual([p['id'] for p in self.people('Other Builder')], [other_builder_person['id']])
        status, data = self.request('GET', '/api/tenders/data')
        self.assertEqual(status, 200)
        rows = {s['id']: s for s in data['submissions']}
        for identifier in (source['id'], unlinked['id']):
            current = rows[identifier]
            old = json.loads(originals[identifier]['body'])
            self.assertEqual([p['id'] for p in current['contacts']], [kept['id']])
            self.assertEqual(current['awardContacts'], current['contacts'])
            self.assertEqual((current['contact'], current['email']), (kept['name'], kept['emails'][0]))
            self.assertGreater(current['revision'], originals[identifier]['revision'])
            for field in ('value', 'quoteNo', 'due', 'status', 'builderStatus', 'submittedDate',
                          'awardedDate', 'estStartDate', 'awardProjectLink'):
                self.assertEqual(current.get(field), old.get(field), field)
        status, result = self.request('GET', '/api/tenders/opportunities/detail?id=' + opportunity['id'])
        self.assertEqual(status, 200)
        updated = result['opportunity']
        selected = next(group['contacts'] for group in updated['builderContacts'] if group['builder'] == 'Delete Builder')
        self.assertEqual([p['id'] for p in selected], [kept['id']])
        self.assertGreater(updated['revision'], quoted['opportunity']['revision'])
        self.assertEqual(self.request('POST', '/api/tenders/opportunities/save', quoted['opportunity'])[0], 409)
        self.assertEqual(self.request('POST', '/api/tenders/submissions', source)[0], 409)
        self.assertEqual(self.request('POST', '/api/tenders/builder-contacts', {'builder': 'Delete Builder', 'contacts': [removed]})[0], 409)
        with self.store.connect() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM reminders ORDER BY id')], reminders)
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM chases ORDER BY id')], chases)
            self.assertFalse(db.execute('SELECT 1 FROM builder_contact_links WHERE contact_id=?', (removed['id'],)).fetchone())
            self.assertTrue(db.execute('SELECT 1 FROM builder_contact_deletions WHERE id=?', (removed['id'],)).fetchone())
            self.assertTrue(db.execute("SELECT 1 FROM tender_activity WHERE action='Deleted builder directory contact'").fetchone())
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())
            for identifier in (source['id'], unlinked['id']):
                self.assertNotIn(removed['id'], db.execute('SELECT body FROM submissions WHERE id=?', (identifier,)).fetchone()[0])
        # Deleting the final person leaves explicit empty selections through
        # repeated worker restarts; no legacy name/email fallback can reappear.
        self.remove(kept)
        path = self.store.path
        tenders.close_store()
        for _ in range(2):
            reopened = tenders.Store(path)
            self.assertEqual(next(group['contacts'] for group in builder_contacts.directory(reopened)['builders'] if group['builder'] == 'Delete Builder'), [])
            current = next(s for s in reopened.all_data()['submissions'] if s['id'] == source['id'])
            self.assertEqual(current['contacts'], [])
            self.assertEqual(current['awardContacts'], [])
            self.assertEqual((current['contact'], current['email'], current['awardContactName'], current['awardContactEmail'], current['awardContactPhone']), ('', '', '', '', ''))
            reopened.close()
        self.store = tenders.get_store()

    def test_legacy_last_contact_is_cleared_without_fallback_resurrection(self):
        person = self.person('Legacy person')
        raw = {'id': 'legacy-delete', 'project': 'Legacy deletion', 'builder': 'Delete Builder',
            'contact': person['name'], 'email': person['emails'][0], 'phone': person['phones'][0],
            'awardContactName': person['name'], 'awardContactPhone': person['phones'][0], 'awardContactEmail': person['emails'][0],
            'status': 'Open', 'builderStatus': 'Awarded', 'value': 25, 'due': '', 'revision': 4}
        with self.store.connect() as db:
            db.execute('INSERT INTO submissions(id,body,revision) VALUES(?,?,4)', (raw['id'], json.dumps(raw)))
            builder_contacts._set_links(db, 'submission', raw['id'], raw['builder'], [person])
        self.remove(person)
        with self.store.connect() as db:
            row = db.execute('SELECT body,revision FROM submissions WHERE id=?', (raw['id'],)).fetchone()
            saved = json.loads(row['body'])
            self.assertEqual(row['revision'], 5)
            self.assertEqual(saved['contacts'], [])
            self.assertEqual(saved['awardContacts'], [])
            for field in ('contact', 'email', 'phone', 'awardContactName', 'awardContactPhone', 'awardContactEmail'):
                self.assertEqual(saved[field], '')
            self.assertEqual(builder_contacts.submission_view(db, saved)['contacts'], [])

    def test_failed_audit_rolls_back_contact_links_snapshots_and_tombstone(self):
        person = self.person()
        self.tender(contacts=[person])
        with self.store.connect() as db:
            before = {table: [tuple(row) for row in db.execute('SELECT * FROM ' + table)]
                      for table in ('builder_contacts', 'builder_contact_links', 'submissions', 'builder_contact_deletions', 'tender_generation')}
        with patch.object(self.store, 'activity', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'audit unavailable'):
                builder_contacts.delete(self.store, person, self.admin)
        with self.store.connect() as db:
            for table, rows in before.items():
                self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM ' + table)], rows, table)

    def test_unmigrated_archived_opportunity_cleanup_preserves_other_contact_snapshots(self):
        removed = self.person()
        retained = {'name': 'Archived keeper', 'phones': ['0422 100 100'],
                    'emails': ['archived.keeper@example.test'], 'sourceNote': 'Keep this original snapshot'}
        other_builder = {'name': removed['name'], 'phones': list(removed['phones']),
                         'emails': list(removed['emails']), 'sourceNote': 'Different company'}
        grouped = self.opportunity(builders=['Delete Builder', 'Other Builder'])
        legacy = self.opportunity()
        moment = tenders.timestamp()
        with self.store.connect() as db:
            grouped.update(deletedAt=moment, builderContacts=[
                {'builder': 'Delete Builder', 'contacts': [removed, retained], 'sourceNote': 'Original group'},
                {'builder': 'Other Builder', 'contacts': [other_builder]}])
            db.execute('UPDATE opportunities SET body=?,deleted_at=? WHERE id=?', (json.dumps(grouped), moment, grouped['id']))
            legacy.update(contacts=[removed, retained], contact=removed['name'],
                          email=removed['emails'][0], phone=removed['phones'][0])
            # Older preserved Opportunity bodies can lack a JSON id even
            # though their SQL row and retirement membership have valid IDs.
            db.execute('UPDATE opportunities SET body=? WHERE id=?', (json.dumps({k: v for k, v in legacy.items() if k != 'id'}), legacy['id']))
            db.execute('INSERT INTO opportunity_reset_entries(kind,record_key,retired_at) VALUES(?,?,?)',
                       ('opportunity', legacy['id'], moment))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM builder_contact_links WHERE source_kind='opportunity' AND source_id IN (?,?)",
                                        (grouped['id'], legacy['id'])).fetchone()[0], 0)
        self.remove(removed)
        with self.store.connect() as db:
            saved = json.loads(db.execute('SELECT body FROM opportunities WHERE id=?', (grouped['id'],)).fetchone()[0])
            self.assertEqual(saved['builderContacts'][0], {'builder': 'Delete Builder', 'contacts': [retained], 'sourceNote': 'Original group'})
            self.assertEqual(saved['builderContacts'][1], grouped['builderContacts'][1])
            saved_legacy = json.loads(db.execute('SELECT body FROM opportunities WHERE id=?', (legacy['id'],)).fetchone()[0])
            self.assertEqual(saved_legacy['id'], legacy['id'])
            self.assertEqual(saved_legacy['contacts'], [retained])
            self.assertNotEqual(saved_legacy['contact'], removed['name'])
            self.assertNotEqual(saved_legacy['email'], removed['emails'][0])
            self.assertEqual(db.execute('SELECT deleted_at FROM opportunities WHERE id=?', (grouped['id'],)).fetchone()[0], moment)
            self.assertIsNone(db.execute('SELECT restored_at FROM opportunity_reset_entries WHERE record_key=?', (legacy['id'],)).fetchone()[0])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM builder_contact_links WHERE source_kind='opportunity' AND source_id IN (?,?)",
                                        (grouped['id'], legacy['id'])).fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
