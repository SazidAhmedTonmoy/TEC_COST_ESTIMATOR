"""TEC Flow v3.8: awarded-project start dates, links and permissions."""
import json
import unittest
from conest_app import tenders, opportunities
import support_http as helpers


class OpenAwardedDatesTests(unittest.TestCase):
    request = helpers.HttpPatchTests.request

    def setUp(self):
        tenders._store = None
        helpers.HttpPatchTests.setUp(self)

    def tearDown(self):
        tenders._store = None
        helpers.HttpPatchTests.tearDown(self)

    def create(self, project='New Builder Award', builder='Builder Award Test', region='NSW'):
        status, data = self.request('POST', '/api/tenders/submissions', {
            'project': project, 'builder': builder, 'region': region, 'status': 'Open',
            'builderStatus': 'Awarded', 'value': 1234, 'contact': 'Original tender contact',
            'email': 'original@example.com'})
        self.assertEqual(status, 200, data)
        return data['submission']

    def test_dates_and_project_link_persist_when_shared_contact_changes(self):
        record = self.create()
        status, data = self.request('POST', '/api/tenders/open-awarded/contact', {
            'id': record['id'], 'revision': record['revision'],
            'awardedDate': '2026-11-08', 'estStartDate': '2027-02-12',
            'awardProjectLink': 'https://builder.example.com/tenders/project?a=1',
            'awardContactName': 'Site manager', 'awardContactEmail': 'manager@example.com'})
        self.assertEqual(status, 200, data)
        record = data['submission']
        self.assertEqual(record['estStartDate'], '2027-02-12')
        self.assertEqual(record['awardProjectLink'], 'https://builder.example.com/tenders/project?a=1')
        self.assertEqual(record['awardedDate'], '2026-11-08')
        self.assertEqual(record['contact'], 'Site manager')
        self.assertEqual(record['email'], 'manager@example.com')
        self.assertEqual(record['contacts'], record['awardContacts'])
        self.assertTrue(record['contacts'][0]['id'])
        self.assertEqual(record['value'], 1234)
        # Older clients updating only the contact must NOT erase saved new fields.
        status, result = self.request('POST', '/api/tenders/open-awarded/contact', {
            'id': record['id'], 'revision': record['revision'], 'awardContactPhone': '+61 401 222 333'})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['submission']['estStartDate'], '2027-02-12')
        self.assertEqual(result['submission']['awardProjectLink'], record['awardProjectLink'])
        self.assertEqual(result['submission']['awardContactName'], 'Site manager')
        self.assertEqual(self.request('POST', '/api/tenders/open-awarded/contact', {
            'id': record['id'], 'revision': record['revision'], 'estStartDate': '2027-03-01'})[0], 409)
        reloaded = next(s for s in self.request('GET', '/api/tenders/data')[1]['submissions'] if s['id'] == record['id'])
        self.assertEqual(reloaded['estStartDate'], '2027-02-12')
        with tenders.get_store().connect() as db:
            self.assertIn('estStartDate', json.loads(db.execute('SELECT body FROM submissions WHERE id=?',(record['id'],)).fetchone()[0]))

    def test_invalid_dates_links_and_csrf_are_rejected(self):
        record = self.create('Award validation test')
        base = {'id': record['id'], 'revision': record['revision']}
        for bad in ({'estStartDate': '2026-02-30'}, {'estStartDate': 'next Friday'},
                    {'awardProjectLink': 'javascript:alert(1)'},
                    {'awardProjectLink': 'https://evil.test/\nlogin'},
                    {'awardProjectLink': 'https://name:password@example.com'}):
            self.assertEqual(self.request('POST', '/api/tenders/open-awarded/contact', {**base, **bad})[0], 400, bad)
        self.assertEqual(self.request('POST', '/api/tenders/open-awarded/contact', {**base,'estStartDate':'2026-11-18'}, csrf=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/tenders/open-awarded/contact', {**base,'awardProjectLink':'builder.example.com/project'})[0], 200)
        found = next(s for s in self.request('GET', '/api/tenders/data')[1]['submissions'] if s['id']==record['id'])
        self.assertEqual(found['awardProjectLink'], 'https://builder.example.com/project')

    def test_auto_link_uses_current_opportunity_url_and_allows_manual_override(self):
        submission = self.create('Exact Awarded Project', 'Unique Build Co')
        store = tenders.get_store()
        user = self._admin()
        opportunity = opportunities.save(store, {
            'project': submission['project'], 'builders': [submission['builder']], 'region': 'NSW',
            'link': 'https://first.example.com/project'}, user)['opportunity']
        # A unique exact project+builder+region match can suggest a URL without
        # pretending the records have been formally linked.
        row = self._tender(submission['id'])
        self.assertEqual(row['opportunityLink'], 'https://first.example.com/project')
        self.assertEqual(row['opportunityLinkSource'], 'exact-match')
        with store.connect(write=True) as db:
            existing = json.loads(db.execute('SELECT body FROM submissions WHERE id=?', (submission['id'],)).fetchone()['body'])
            existing['opportunityId'] = opportunity['id']
            db.execute('UPDATE submissions SET body=? WHERE id=?', (json.dumps(existing), submission['id']))
        row = self._tender(submission['id'])
        self.assertEqual(row['opportunityLinkSource'], 'linked')
        # Editing the opportunity URL should be visible at the next read.
        updated = opportunities.save(store, {'id': opportunity['id'], 'revision': opportunity['revision'],
                  'link': 'https://second.example.com/project'}, user)['opportunity']
        row = self._tender(submission['id'])
        self.assertEqual(row['opportunityLink'], 'https://second.example.com/project')
        self.assertEqual(row['revision'], submission['revision'])
        # A manual override belongs to the awarded-project contact record only.
        status, data = self.request('POST', '/api/tenders/open-awarded/contact', {
            'id': submission['id'], 'revision': row['revision'],
            'awardProjectLink': 'https://alternate.example.com/start'})
        self.assertEqual(status, 200, data)
        row = self._tender(submission['id'])
        self.assertEqual(row['awardProjectLink'], 'https://alternate.example.com/start')
        self.assertEqual(row['opportunityLink'], 'https://second.example.com/project')

    def test_ambiguous_or_unrelated_opportunities_do_not_add_links(self):
        a = self.create('Same project', 'A Builder')
        b = self.create('Same project', 'Other Builder')
        store = tenders.get_store()
        user = self._admin()
        for url in ('https://one.example.com', 'https://two.example.com'):
            payload = {'project': a['project'], 'builders': [a['builder']],
                       'region': 'NSW', 'link': url}
            result = opportunities.save(store, payload, user)
            if result.get('requiresDuplicateReview'):
                result = opportunities.save(store, {**payload, 'duplicateToken': result['duplicateToken']}, user)
            self.assertIn('opportunity', result)
        self.assertFalse(self._tender(a['id']).get('opportunityLink'))
        self.assertFalse(self._tender(b['id']).get('opportunityLink'))

    def _admin(self):
        from conest_app.database import connect
        with connect() as db:
            return dict(db.execute("SELECT id,name,role,team_id FROM users WHERE role='admin' LIMIT 1").fetchone())

    def _tender(self, identifier):
        result = self.request('GET', '/api/tenders/data')
        self.assertEqual(result[0], 200)
        return next(s for s in result[1]['submissions'] if s['id'] == identifier)


if __name__ == '__main__':
    unittest.main()
