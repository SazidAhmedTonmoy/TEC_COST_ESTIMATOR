"""Shared builder contacts: real authenticated routes and non-destructive migration."""
from io import BytesIO
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from conest_app import tenders
import support_http as helpers


def details(people):
    """Compare user data independently of the directory's IDs and revisions."""
    return [{key: person.get(key, [] if key != 'name' else '')
             for key in ('name', 'phones', 'emails')} for person in people]


class BuilderContactsHttpTests(unittest.TestCase):
    request = helpers.HttpPatchTests.request

    def setUp(self):
        tenders.close_store()
        helpers.HttpPatchTests.setUp(self)

    def tearDown(self):
        tenders.close_store()
        helpers.HttpPatchTests.tearDown(self)

    def post(self, path, payload):
        status, data = self.request('POST', '/api/tenders/' + path, payload)
        self.assertEqual(status, 200, data)
        return data

    def directory(self, builder):
        status, data = self.request('GET', '/api/tenders/builder-contacts')
        self.assertEqual(status, 200, data)
        return next((row['contacts'] for row in data['builders']
                     if tenders.builder_key(row['builder']) == tenders.builder_key(builder)), [])

    def submission(self, identifier):
        status, data = self.request('GET', '/api/tenders/data')
        self.assertEqual(status, 200, data)
        return next(row for row in data['submissions'] if row['id'] == identifier)

    def create_tender(self, builder='Contact Builder A', project='Contact tender', **fields):
        return self.post('submissions', {
            'project': project, 'builder': builder, 'status': 'Open',
            'builderStatus': 'Awarded', 'region': 'NSW', 'value': 1000,
            **fields,
        })['submission']

    def create_opportunity(self, **fields):
        return self.post('opportunities/save', {
            'project': 'Shared contact opportunity', 'region': 'NSW',
            'builders': ['Contact Builder A', 'Contact Builder B'],
            'due': '2099-12-01', 'workingScope': 'Electrical works', **fields,
        })['opportunity']

    def opportunity(self, identifier):
        status, data = self.request('GET', '/api/tenders/opportunities/detail?id=' + identifier)
        self.assertEqual(status, 200, data)
        return data['opportunity']

    @staticmethod
    def selected(item, builder):
        return next((group['contacts'] for group in item.get('builderContacts', [])
                     if tenders.builder_key(group['builder']) == tenders.builder_key(builder)), [])

    def test_opportunity_contacts_optional_then_add_multiple_and_preserve_on_other_edits(self):
        item = self.create_opportunity()
        self.assertEqual(self.selected(item, 'Contact Builder A'), [])
        self.assertEqual(self.selected(item, 'Contact Builder B'), [])
        people = [
            {'name': 'Alex Lee', 'phones': ['02 1234 5678', '0412 333 444'],
             'emails': ['alex@example.test', 'alex.office@example.test']},
            {'name': 'Site team', 'phones': [], 'emails': []},
        ]
        item = self.post('opportunities/save', {
            'id': item['id'], 'revision': item['revision'],
            'builderContacts': [{'builder': 'Contact Builder A', 'contacts': people}],
        })['opportunity']
        saved = self.selected(item, 'Contact Builder A')
        self.assertEqual(details(saved), people)
        self.assertTrue(all(person.get('id') for person in saved))
        self.assertEqual(details(self.directory('Contact Builder A')), people)
        item = self.post('opportunities/save', {
            'id': item['id'], 'revision': item['revision'], 'workingScope': 'Revised scope',
        })['opportunity']
        self.assertEqual(details(self.selected(item, 'Contact Builder A')), people)
        self.assertEqual(self.selected(item, 'Contact Builder B'), [])

    def test_tender_and_awarded_share_people_and_directory_is_reusable_in_opportunities(self):
        first = {'name': 'Taylor Park', 'phones': ['0412 111 222'],
                 'emails': ['taylor@example.test']}
        s = self.create_tender(contacts=[first])
        self.assertEqual(details(s['contacts']), [first])
        self.assertEqual(details(s['awardContacts']), [first])
        extra = {'name': 'Jordan Smith', 'phones': ['02 9000 1111'],
                 'emails': ['jordan@example.test']}
        s = self.post('open-awarded/contact', {
            'id': s['id'], 'revision': s['revision'],
            'awardContacts': s['awardContacts'] + [extra],
        })['submission']
        self.assertEqual(details(s['contacts']), [first, extra])
        people = self.directory('Contact Builder A')
        self.assertEqual({p['name'] for p in people}, {'Taylor Park', 'Jordan Smith'})
        item = self.create_opportunity(builderContacts=[{
            'builder': 'Contact Builder A', 'contacts': people,
        }])
        self.assertEqual({p['id'] for p in self.selected(item, 'Contact Builder A')},
                         {p['id'] for p in people})
        self.assertEqual(len(self.directory('Contact Builder A')), 2)

    def test_directory_edit_updates_every_assignment_without_copying_people_between_builders(self):
        person = {'name': 'Sam Rivera', 'phones': ['0411 111 111'],
                  'emails': ['sam@example.test']}
        s = self.create_tender(contacts=[person])
        original = self.directory('Contact Builder A')[0]
        item = self.create_opportunity(builderContacts=[{
            'builder': 'Contact Builder A', 'contacts': [original],
        }])
        changed = {**original, 'name': 'Sam Rivers',
                   'phones': ['0411 111 111', '02 9111 2222'],
                   'emails': ['sam.rivers@example.test']}
        self.post('builder-contacts', {'builder': 'Contact Builder A', 'contacts': [changed]})
        expected = details([changed])
        s = self.submission(s['id'])
        self.assertEqual(details(s['contacts']), expected)
        self.assertEqual(details(s['awardContacts']), expected)
        self.assertEqual(s['contact'], changed['name'])
        self.assertEqual(s['email'], changed['emails'][0])
        item = self.opportunity(item['id'])
        self.assertEqual(details(self.selected(item, 'Contact Builder A')), expected)
        self.assertEqual(self.selected(item, 'Contact Builder B'), [])
        self.assertEqual(self.directory('Contact Builder B'), [])

    def test_builder_scoping_and_namesakes_do_not_merge_distinct_people(self):
        first = {'name': 'Alex Lee', 'phones': [], 'emails': ['alex.one@example.test']}
        second = {'name': 'Alex Lee', 'phones': [], 'emails': ['alex.two@example.test']}
        self.post('builder-contacts', {'builder': 'Contact Builder A', 'contacts': [first, second]})
        a = self.directory('Contact Builder A')
        self.assertEqual(len(a), 2)
        self.assertEqual(len({p['id'] for p in a}), 2)
        self.post('builder-contacts', {'builder': 'Contact Builder B', 'contacts': [first]})
        b = self.directory('Contact Builder B')
        self.assertEqual(len(b), 1)
        self.assertNotIn(b[0]['id'], {p['id'] for p in a})
        # Formatting differences in an existing builder name do not split its directory.
        self.post('builder-contacts', {'builder': 'contact builder a', 'contacts': [first]})
        self.assertEqual(len(self.directory('Contact Builder A')), 2)
        status, _ = self.request('POST', '/api/tenders/builder-contacts', {
            'builder': 'Contact Builder B', 'contacts': [a[0]],
        })
        self.assertEqual(status, 400)

    def test_stale_contact_edits_are_rejected_atomically_and_unchanged_people_can_be_reused(self):
        person = {'name': 'Original', 'phones': [], 'emails': ['original@example.test']}
        self.post('builder-contacts', {'builder': 'Contact Builder A', 'contacts': [person]})
        before = self.directory('Contact Builder A')[0]
        self.post('builder-contacts', {'builder': 'Contact Builder A',
                                     'contacts': [{**before, 'name': 'Updated'}]})
        status, _ = self.request('POST', '/api/tenders/builder-contacts', {
            'builder': 'Contact Builder A',
            'contacts': [{'name': 'Should roll back', 'phones': [], 'emails': []},
                         {**before, 'name': 'Stale change'}],
        })
        self.assertEqual(status, 409)
        current = self.directory('Contact Builder A')
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]['name'], 'Updated')
        no_revision = {k: v for k, v in current[0].items() if k != 'revision'}
        status, _ = self.request('POST', '/api/tenders/builder-contacts', {
            'builder': 'Contact Builder A', 'contacts': [{**no_revision, 'name': 'No revision'}],
        })
        self.assertEqual(status, 409)
        self.post('builder-contacts', {'builder': 'Contact Builder A', 'contacts': current})
        self.assertEqual(self.directory('Contact Builder A'), current)

    def test_removing_project_contact_does_not_delete_builder_directory(self):
        people = [{'name': 'Reusable person', 'phones': [], 'emails': ['reuse@example.test']}]
        s = self.create_tender(contacts=people)
        saved = s['contacts']
        item = self.create_opportunity(builderContacts=[{
            'builder': 'Contact Builder A', 'contacts': saved,
        }])
        s = self.post('submissions', {**s, 'contacts': []})['submission']
        self.assertEqual(s['contacts'], [])
        self.assertEqual(s['awardContacts'], [])
        self.assertEqual(s['contact'], '')
        self.assertEqual(s['email'], '')
        item = self.post('opportunities/save', {
            'id': item['id'], 'revision': item['revision'], 'builderContacts': [],
        })['opportunity']
        self.assertEqual(self.selected(item, 'Contact Builder A'), [])
        self.assertEqual(details(self.directory('Contact Builder A')), people)

    def test_batch_tenders_keep_each_builders_contacts_separate(self):
        a = {'name': 'Builder A person', 'phones': [], 'emails': ['a@example.test']}
        b = {'name': 'Builder B person', 'phones': [], 'emails': ['b@example.test']}
        self.post('submissions/batch', {
            'project': 'Multi-builder contact test', 'builders': ['Contact Builder A', 'Contact Builder B'],
            'status': 'Open', 'region': 'NSW', 'value': 1500,
            'builderContacts': [{'builder': 'Contact Builder A', 'contacts': [a]},
                                {'builder': 'Contact Builder B', 'contacts': [b]}],
        })
        status, data = self.request('GET', '/api/tenders/data')
        self.assertEqual(status, 200, data)
        rows = [s for s in data['submissions'] if s['project'] == 'Multi-builder contact test']
        self.assertEqual(len(rows), 2)
        for s in rows:
            self.assertEqual(details(s['contacts']), [a if s['builder'] == 'Contact Builder A' else b])

    def test_whole_opportunity_builder_removal_unassigns_contacts_without_resurrection(self):
        a = {'name': 'Removed builder person', 'phones': [], 'emails': ['removed@example.test']}
        b = {'name': 'Retained builder person', 'phones': [], 'emails': ['retained@example.test']}
        item = self.create_opportunity(builderContacts=[
            {'builder': 'Contact Builder A', 'contacts': [a]},
            {'builder': 'Contact Builder B', 'contacts': [b]},
        ])
        # A client submits the complete returned record, including the old
        # builderContacts groups, while replacing a builder in its name list.
        item = self.post('opportunities/save', {
            **item, 'builders': ['Contact Builder B', 'Replacement Builder'],
        })['opportunity']
        self.assertEqual(self.selected(item, 'Contact Builder A'), [])
        self.assertEqual(details(self.selected(item, 'Contact Builder B')), [b])
        self.assertEqual(self.selected(item, 'Replacement Builder'), [])
        self.assertEqual(details(self.directory('Contact Builder A')), [a])
        # Re-adding its name offers the directory person but does not silently
        # select a person the user removed from this opportunity.
        item = self.post('opportunities/save', {
            **item, 'builders': ['Contact Builder A', *item['builders']],
        })['opportunity']
        self.assertEqual(self.selected(self.opportunity(item['id']), 'Contact Builder A'), [])
        self.assertEqual(details(self.selected(item, 'Contact Builder B')), [b])
        status, _ = self.request('POST', '/api/tenders/opportunities/save', {
            **item, 'builderContacts': item['builderContacts'] + [
                {'builder': 'Never selected builder', 'contacts': []}],
        })
        self.assertEqual(status, 400)

    def test_opportunity_quote_handoff_and_later_awarded_contact_selection_are_shared(self):
        a = {'name': 'Opportunity person A', 'phones': ['0422 100 100'], 'emails': ['op.a@example.test']}
        b = {'name': 'Opportunity person B', 'phones': [], 'emails': ['op.b@example.test']}
        item = self.create_opportunity(builderContacts=[
            {'builder': 'Contact Builder A', 'contacts': [a]},
            {'builder': 'Contact Builder B', 'contacts': [b]},
        ])
        item = self.post('opportunities/decision', {
            'id': item['id'], 'revision': item['revision'], 'decision': 'approved',
        })['opportunity']
        result = self.post('opportunities/quote', {
            'id': item['id'], 'revision': item['revision'], 'value': 5000,
            'submittedDate': '2026-11-20', 'builders': ['Contact Builder A', 'Contact Builder B'],
        })
        self.assertEqual(len(result['submissionIds']), 2)
        rows = [self.submission(sid) for sid in result['submissionIds']]
        for s in rows:
            self.assertEqual(details(s['contacts']), [a if s['builder'] == 'Contact Builder A' else b])
        s = next(row for row in rows if row['builder'] == 'Contact Builder A')
        s = self.post('submissions', {**s, 'builderStatus': 'Awarded'})['submission']
        additional = {'name': 'Construction manager', 'phones': [], 'emails': ['manager@example.test']}
        self.post('open-awarded/contact', {
            'id': s['id'], 'revision': s['revision'], 'awardContacts': s['contacts'] + [additional],
        })
        item = self.opportunity(item['id'])
        self.assertEqual(details(self.selected(item, 'Contact Builder A')), [a, additional])
        self.assertEqual(details(self.selected(item, 'Contact Builder B')), [b])

    def test_invalid_contacts_and_unknown_builder_groups_do_not_partially_save(self):
        invalid = [
            'not-a-list', [{'name': 42, 'phones': [], 'emails': []}],
            [{'name': 'Invalid email', 'phones': [], 'emails': ['not-an-email']}],
            [{'name': 'Invalid phone', 'phones': ['javascript:alert(1)'], 'emails': []}],
            [{'name': 'Bad array', 'phones': [], 'emails': 'one@example.test'}],
        ]
        for people in invalid:
            with self.subTest(people=people):
                status, _ = self.request('POST', '/api/tenders/builder-contacts', {
                    'builder': 'Contact Builder A', 'contacts': people,
                })
                self.assertEqual(status, 400)
        self.assertEqual(self.directory('Contact Builder A'), [])
        item = self.create_opportunity()
        status, _ = self.request('POST', '/api/tenders/opportunities/save', {
            'id': item['id'], 'revision': item['revision'],
            'builderContacts': [{'builder': 'Not on this opportunity',
                                 'contacts': [{'name': 'Wrong builder person', 'phones': [], 'emails': []}]}],
        })
        self.assertEqual(status, 400)
        self.assertEqual(self.opportunity(item['id'])['revision'], item['revision'])
        self.assertEqual(self.directory('Not on this opportunity'), [])

    def test_workbook_import_registers_shared_contacts_and_keeps_additional_people(self):
        def import_row(value):
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = 'Tenders'
            sheet.append(['Submission ID', 'Project', 'Builder', 'TEC status',
                          'Tender value', 'Contact person', 'Email'])
            sheet.append(['imported-contact-1', 'Imported contact project', 'Contact Builder A',
                          'Open', value, 'Imported person', 'imported@example.test'])
            output = BytesIO()
            workbook.save(output)
            workbook.close()
            payload = {'filename': 'contacts.xlsx',
                       'content': base64.b64encode(output.getvalue()).decode()}
            preview = self.post('import', {**payload, 'mode': 'preview'})
            return self.post('import', {**payload, 'mode': 'apply', 'token': preview['token']})

        self.assertEqual(import_row(1200)['counts']['added'], 1)
        s = self.submission('imported-contact-1')
        primary = {'name': 'Imported person', 'phones': [], 'emails': ['imported@example.test']}
        self.assertEqual(details(s['contacts']), [primary])
        self.assertEqual(details(self.directory('Contact Builder A')), [primary])
        additional = {'name': 'Later contact', 'phones': ['0412 000 111'], 'emails': []}
        self.post('submissions', {**s, 'contacts': s['contacts'] + [additional]})
        # A subsequent one-contact workbook updates its provided fields only.
        self.assertEqual(import_row(1300)['counts']['updated'], 1)
        s = self.submission('imported-contact-1')
        self.assertEqual(s['value'], 1300)
        self.assertEqual(details(s['contacts']), [primary, additional])
        self.assertEqual(s['contacts'], s['awardContacts'])
        self.assertEqual(len(self.directory('Contact Builder A')), 2)

    def test_explicit_link_merges_existing_selections_and_later_opportunity_edits_reach_tender(self):
        tender_person = {'name': 'Tender team person', 'phones': [], 'emails': ['tender.team@example.test']}
        opportunity_person = {'name': 'Opportunity team person', 'phones': [], 'emails': ['op.team@example.test']}
        s = self.create_tender(project='Existing tender to link', contacts=[tender_person])
        item = self.create_opportunity(builderContacts=[{
            'builder': 'Contact Builder A', 'contacts': [opportunity_person],
        }])
        item = self.post('opportunities/decision', {
            'id': item['id'], 'revision': item['revision'], 'decision': 'approved',
        })['opportunity']
        item = self.post('opportunities/link-project', {
            'id': item['id'], 'revision': item['revision'], 'submissionId': s['id'],
        })['opportunity']
        selected = self.selected(item, 'Contact Builder A')
        self.assertEqual({p['name'] for p in selected},
                         {tender_person['name'], opportunity_person['name']})
        s = self.submission(s['id'])
        self.assertEqual({p['id'] for p in s['contacts']}, {p['id'] for p in selected})
        later_person = {'name': 'Added after linking', 'phones': [], 'emails': ['later@example.test']}
        item = self.post('opportunities/save', {
            'id': item['id'], 'revision': item['revision'],
            'builderContacts': [{'builder': 'Contact Builder A', 'contacts': selected + [later_person]}],
        })['opportunity']
        s = self.submission(s['id'])
        self.assertEqual(details(s['contacts']), details(self.selected(item, 'Contact Builder A')))
        self.assertIn(later_person, details(s['contacts']))
        self.assertEqual(s['contacts'], s['awardContacts'])

    def test_directory_and_download_require_login_and_mutation_requires_csrf(self):
        payload = {'builder': 'Contact Builder A',
                   'contacts': [{'name': 'Access check', 'phones': [], 'emails': []}]}
        self.assertEqual(self.request('POST', '/api/tenders/builder-contacts', payload, csrf=False)[0], 403)
        cookie, csrf = self.cookie, self.csrf
        self.cookie = self.csrf = ''
        for path in ('/api/tenders/builder-contacts', '/api/tenders/builder-contacts/export.xlsx'):
            self.assertEqual(self.request('GET', path)[0], 401)
        self.assertEqual(self.request('POST', '/api/tenders/builder-contacts', payload)[0], 401)
        self.cookie, self.csrf = cookie, csrf
        self.assertEqual(self.directory('Contact Builder A'), [])
        # Shared builder people are available to ordinary authenticated staff.
        from conest_app import accounts
        from conest_app.database import connect
        with connect() as db:
            row = db.execute("SELECT id,username FROM users WHERE role!='admin' LIMIT 1").fetchone()
            self.assertIsNotNone(row)
            db.execute('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?',
                       (accounts.password_hash('contact-directory-test-password'), row['id']))
        self.cookie = self.csrf = ''
        status, data = self.request('POST', '/api/auth/login', {
            'username': row['username'], 'password': 'contact-directory-test-password',
        })
        self.assertEqual(status, 200, data)
        self.post('builder-contacts', payload)
        self.assertEqual(self.directory('Contact Builder A')[0]['name'], 'Access check')

    def test_contacts_download_covers_multiple_people_and_treats_formula_text_as_text(self):
        people = [
            {'name': '=HYPERLINK("https://example.test","person")',
             'phones': ['+61 412 345 678'], 'emails': ['first@example.test', 'second@example.test']},
            {'name': 'Another person', 'phones': ['02 9999 8888', '0433 555 777'], 'emails': []},
        ]
        self.post('builder-contacts', {'builder': 'Contact Builder A', 'contacts': people})
        self.post('builder-contacts', {'builder': 'Contact Builder B',
                                     'contacts': [{'name': 'Builder B person', 'phones': [], 'emails': []}]})
        status, content = self.request('GET', '/api/tenders/builder-contacts/export.xlsx')
        self.assertEqual(status, 200, content if not isinstance(content, bytes) else '')
        self.assertIn('spreadsheetml', self.last_headers.get('Content-Type', ''))
        self.assertIn('attachment', self.last_headers.get('Content-Disposition', ''))
        workbook = load_workbook(BytesIO(content), data_only=False)
        cells = [cell for sheet in workbook for row in sheet for cell in row]
        text = '\n'.join(str(cell.value or '') for cell in cells)
        for value in ('Contact Builder A', 'Contact Builder B', 'Another person', 'Builder B person',
                      '+61 412 345 678', '0433 555 777', 'first@example.test', 'second@example.test'):
            self.assertIn(value, text)
        dangerous = [cell for cell in cells if 'HYPERLINK' in str(cell.value)]
        self.assertTrue(dangerous)
        self.assertTrue(all(cell.data_type != 'f' for cell in dangerous))
        workbook.close()


class BuilderContactMigrationTests(unittest.TestCase):
    def test_legacy_backfill_preserves_sources_unions_contacts_and_is_idempotent(self):
        from conest_app import builder_contacts

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            'CONEST_DB_PATH': str(Path(folder) / 'accounts.db'),
            'CONEST_TENDERS_DB_PATH': str(Path(folder) / 'tenders.db'),
        }):
            # Prepare an otherwise current DB without running the new contact migration.
            with patch.object(builder_contacts, 'initialize'):
                store = tenders.Store(Path(folder) / 'tenders.db')
            legacy = {
                'id': 'legacy-contact-fixture', 'project': 'Legacy contact project',
                'builder': 'Legacy Contact Builder', 'status': 'Open', 'builderStatus': 'Awarded',
                'region': 'NSW', 'due': '', 'value': 1000, 'revision': 7,
                'contact': 'Taylor Park', 'email': 'taylor@example.test',
                'awardContactName': 'Taylor Park', 'awardContactEmail': 'taylor@example.test',
                'awardContactPhone': '02 9111 2222  0412 333 444',
            }
            invalid = {**legacy, 'id': 'legacy-invalid-email', 'project': 'Legacy invalid email',
                       'contact': 'Legacy partial person', 'email': 'old address needs correction',
                       'awardContactName': '', 'awardContactEmail': '', 'awardContactPhone': ''}
            raw = {row['id']: json.dumps(row, indent=2) for row in (legacy, invalid)}
            with store.connect() as db:
                db.executemany('INSERT INTO submissions(id,body,revision) VALUES(?,?,7)', raw.items())
            builder_contacts.initialize(store)
            first = builder_contacts.directory(store)
            people = next(row['contacts'] for row in first['builders'] if row['builder'] == legacy['builder'])
            taylor = next(p for p in people if p['name'] == 'Taylor Park')
            self.assertEqual(taylor['emails'], ['taylor@example.test'])
            self.assertEqual(taylor['phones'], ['02 9111 2222', '0412 333 444'])
            self.assertEqual(sum(p['name'] == 'Taylor Park' for p in people), 1)
            old_person = next(p for p in people if p['name'] == 'Legacy partial person')
            self.assertIn('old address needs correction', old_person['emails'])
            builder_contacts.initialize(store)
            self.assertEqual(builder_contacts.directory(store), first)
            with store.connect() as db:
                for identifier, original in raw.items():
                    saved = db.execute('SELECT body,revision FROM submissions WHERE id=?', (identifier,)).fetchone()
                    self.assertEqual(saved['body'], original)
                    self.assertEqual(saved['revision'], 7)
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            # Loading a record displays canonical details without rewriting legacy JSON.
            data = store.all_data()
            migrated = next(s for s in data['submissions'] if s['id'] == legacy['id'])
            self.assertEqual(migrated['contacts'][0]['id'], taylor['id'])
            self.assertEqual(migrated['contacts'], migrated['awardContacts'])
            store.close()


if __name__ == '__main__':
    unittest.main()
