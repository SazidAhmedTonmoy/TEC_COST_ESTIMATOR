"""v3.8: multiple people, phone numbers and emails per awarded submission."""
import unittest
from conest_app import tenders
import support_http as helpers


class MultipleAwardContactsTests(unittest.TestCase):
    request = helpers.HttpPatchTests.request

    def setUp(self):
        tenders._store = None
        helpers.HttpPatchTests.setUp(self)

    def tearDown(self):
        tenders._store = None
        helpers.HttpPatchTests.tearDown(self)

    def create(self, project='Multiple award contacts', builder='Awarded Builder'):
        status, data = self.request('POST', '/api/tenders/submissions', {
            'project': project, 'builder': builder, 'status': 'Open',
            'builderStatus': 'Awarded', 'value': 4200, 'contact': 'Original tender contact',
            'email': 'tender@example.com'})
        self.assertEqual(status, 200, data)
        return data['submission']

    def rows(self, sid):
        status, data = self.request('GET', '/api/tenders/data')
        self.assertEqual(status, 200)
        return next(row for row in data['submissions'] if row['id'] == sid)

    def test_two_people_multiple_numbers_and_emails_are_saved_and_preserved(self):
        s = self.create()
        people = [
            {'name': 'Josh Giles', 'phones': ['02 9616 2990', '0427 420 103'],
             'emails': ['josh@example.com', 'j.giles@example.com']},
            {'name': 'Project Manager', 'phones': ['+61 401 333 444'],
             'emails': ['manager@example.com', 'site@example.com']},
        ]
        payload = {'id': s['id'], 'revision': s['revision'], 'awardContacts': people,
                   'awardedDate': '2026-11-06', 'estStartDate': '2027-02-01'}
        status, result = self.request('POST', '/api/tenders/open-awarded/contact', payload)
        self.assertEqual(status, 200, result)
        saved = result['submission']
        self.assertEqual(saved['awardContacts'], people)
        self.assertEqual(saved['awardContactName'], 'Josh Giles')
        self.assertEqual(saved['awardContactPhone'], '02 9616 2990')
        self.assertEqual(saved['awardContactEmail'], 'josh@example.com')
        self.assertEqual(saved['contact'], 'Original tender contact')
        self.assertEqual(saved['email'], 'tender@example.com')
        self.assertEqual(self.rows(s['id'])['awardContacts'], people)
        # Generic tender editing cannot erase independent awarded contacts.
        self.assertEqual(self.request('POST', '/api/tenders/submissions', {
            **saved, 'remarks': 'Updated tender text'})[0], 200)
        self.assertEqual(self.rows(s['id'])['awardContacts'], people)
        # Changing an awarded date through the old endpoint must not erase them.
        next_rev = self.rows(s['id'])['revision']
        self.assertEqual(self.request('POST', '/api/tenders/open-awarded/contact', {
            'id': s['id'], 'revision': next_rev, 'awardedDate': '2026-11-10'})[0], 200)
        self.assertEqual(self.rows(s['id'])['awardContacts'], people)

    def test_legacy_single_contact_is_read_as_list_and_can_expand_without_loss(self):
        s = self.create('Legacy migration')
        status, result = self.request('POST', '/api/tenders/open-awarded/contact', {
            'id': s['id'], 'revision': s['revision'], 'awardContactName': 'Josh Giles',
            'awardContactPhone': '02 9616 2990  0427 420 103',
            'awardContactEmail': 'josh@example.com'})
        self.assertEqual(status, 200, result)
        current = self.rows(s['id'])
        self.assertEqual(current['awardContacts'][0]['phones'],
                         ['02 9616 2990', '0427 420 103'])
        expanded = current['awardContacts'] + [{'name': 'Another', 'phones': ['0422 111 333'],
                                                 'emails': ['another@example.com']}]
        status, result = self.request('POST', '/api/tenders/open-awarded/contact', {
            'id': s['id'], 'revision': current['revision'], 'awardContacts': expanded})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['submission']['awardContacts'], expanded)
        # Old clients that edit just the phone preserve the second contact.
        status, result = self.request('POST', '/api/tenders/open-awarded/contact', {
            'id': s['id'], 'revision': result['submission']['revision'],
            'awardContactPhone': '02 9000 0000'})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['submission']['awardContacts'][0]['phones'],
                         ['02 9000 0000', '0427 420 103'])
        self.assertEqual(result['submission']['awardContacts'][1], expanded[1])

    def test_removing_contact_and_last_contact_clears_legacy_fields(self):
        s = self.create('Removal')
        people = [{'name': 'First', 'phones': ['02 1234 5678'], 'emails': ['first@example.com']},
                  {'name': 'Second', 'phones': ['0423 222 333'], 'emails': ['second@example.com']}]
        status, result = self.request('POST', '/api/tenders/open-awarded/contact', {
            'id': s['id'], 'revision': s['revision'], 'awardContacts': people})
        self.assertEqual(status, 200, result)
        status, result = self.request('POST', '/api/tenders/open-awarded/contact', {
            'id': s['id'], 'revision': result['submission']['revision'], 'awardContacts': people[1:]})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['submission']['awardContactName'], 'Second')
        status, result = self.request('POST', '/api/tenders/open-awarded/contact', {
            'id': s['id'], 'revision': result['submission']['revision'], 'awardContacts': []})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['submission']['awardContacts'], [])
        self.assertEqual(result['submission']['awardContactPhone'], '')
        self.assertEqual(result['submission']['awardContactEmail'], '')
        self.assertEqual(self.rows(s['id'])['awardContacts'], [])

    def test_invalid_email_phone_bad_structure_duplicates_and_conflicts(self):
        s = self.create('Validation')
        base = {'id': s['id'], 'revision': s['revision']}
        bad_lists = [
            'incorrect', [{}] * 21, [{'name': 10, 'emails': [], 'phones': []}],
            [{'name': 'Bad', 'emails': 'x@example.com', 'phones': []}],
            [{'name': 'Bad', 'emails': ['not-email'], 'phones': []}],
            [{'name': 'Bad', 'emails': [], 'phones': ['javascript:alert(1)']}],
            [{'name': 'Bad', 'emails': ['x@example.com', 'X@example.com'], 'phones': []}],
            [{'name': 'Bad', 'emails': [], 'phones': ['0422 333 444', '0422333444']}],
            [{'name': 'Bad', 'emails': [], 'phones': ['04 21 33 44']*13}],
        ]
        for contacts in bad_lists:
            self.assertEqual(self.request('POST', '/api/tenders/open-awarded/contact', {
                **base, 'awardContacts': contacts})[0], 400, contacts)
        self.assertEqual(self.request('POST', '/api/tenders/open-awarded/contact', {
            **base, 'awardContacts': []}, csrf=False)[0], 403)
        valid = [{'name': 'Site contact', 'emails': ['site@example.com'], 'phones': ['04 22 33 44']}]
        status, result = self.request('POST', '/api/tenders/open-awarded/contact', {
            **base, 'awardContacts': valid})
        self.assertEqual(status, 200, result)
        self.assertEqual(self.request('POST', '/api/tenders/open-awarded/contact', {
            **base, 'awardContacts': []})[0], 409)
        self.assertEqual(self.rows(s['id'])['awardContacts'], valid)

    def test_contacts_are_isolated_per_builder(self):
        a = self.create('One project', 'Builder A')
        b = self.create('One project', 'Builder B')
        self.assertEqual(self.request('POST', '/api/tenders/open-awarded/contact', {
            'id': a['id'], 'revision': a['revision'],
            'awardContacts': [{'name': 'Builder A contact', 'phones': ['02 4444 5555'], 'emails': []}]})[0], 200)
        self.assertEqual(len(self.rows(a['id'])['awardContacts']), 1)
        self.assertEqual(self.rows(b['id'])['awardContacts'], [])


if __name__ == '__main__':
    unittest.main()
