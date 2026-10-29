"""v3.7.5: approved/unlinked after-deadline quote outcomes and date sorting."""
import unittest

from tests import test_opportunities as fixtures
from conest_app import opportunities as op, tenders


class Opportunity375Tests(unittest.TestCase):
    setUp = fixtures.OpportunityTests.setUp
    tearDown = fixtures.OpportunityTests.tearDown
    make_user = staticmethod(fixtures.OpportunityTests.make_user)
    create = fixtures.OpportunityTests.create
    assert_denied = fixtures.OpportunityTests.assert_denied

    def approve(self, item):
        return op.decide(self.store, {'id': item['id'], 'revision': item['revision'],
                                      'decision': 'approved'}, self.admin)['opportunity']

    def quote_fields(self, item):
        return {'id': item['id'], 'revision': item['revision'], 'value': 159000,
                'submittedDate': '2026-10-29', 'builders': item['builders'],
                'submittedByTeamId': self.team, 'note': 'Submitted after the deadline'}

    def test_expired_approved_unlinked_creates_real_submissions_and_cannot_quote_twice(self):
        item = self.approve(self.create(project='Approved long after due', due='2000-01-01'))
        quote = op.quote(self.store, self.quote_fields(item), self.member)
        self.assertTrue(quote['quoted'])
        self.assertEqual(quote['opportunity']['status'], 'approved')
        self.assertEqual(quote['opportunity']['quoteStatus'], 'quoted')
        self.assertEqual(len(quote['submissionIds']), 2)
        self.assertTrue(all(row['opportunityId'] == item['id']
                            for row in self.store.all_data()['submissions']
                            if row['id'] in quote['submissionIds']))
        self.assertEqual(op.quote(self.store, self.quote_fields(item), self.member)['submissionIds'], quote['submissionIds'])
        self.assert_denied(lambda: op.decide(self.store, {'id': item['id'],
                            'revision': quote['opportunity']['revision'],
                            'decision': 'rejected'}, self.admin), 409)

    def test_expired_approved_unlinked_not_quoted_is_a_recorded_rejection(self):
        item = self.approve(self.create(project='Not quoting late', due='2000-01-01'))
        result = op.decide(self.store, {'id': item['id'], 'revision': item['revision'],
                                        'decision': 'rejected', 'reason': ''}, self.member)
        result_item = result['opportunity']
        self.assertEqual(result_item['status'], 'rejected')
        self.assertEqual(result_item['quoteStatus'], 'not_quoted')
        self.assertEqual(result_item['notQuotedBy'], self.member['id'])
        self.assertEqual(result['activity'][0]['details']['quoteStatus'], 'not_quoted')

    def test_approved_with_link_timestamp_but_no_ids_is_protected(self):
        item = self.approve(self.create(project='Legacy linked', due='2000-01-01'))
        item['linkedAt'] = tenders.timestamp()
        item['linkedProjectName'] = 'Historical Chase-up project'
        with self.store.connect() as db:
            op._write(db, item)
        self.assert_denied(lambda: op.quote(self.store, self.quote_fields(item), self.admin), 409)
        self.assert_denied(lambda: op.decide(self.store, {'id': item['id'],
                            'revision': item['revision'], 'decision': 'rejected'}, self.admin), 409)

    def test_deadline_low_high_high_low_and_empty_last_with_pagination(self):
        dates = [('Old expired', '2000-01-01'), ('Mid date', '2099-02-01'),
                 ('Latest date', '2099-12-31'), ('Earliest future', '2099-01-01'),
                 ('No date', '')]
        for name, due in dates:
            self.create(project=name, due=due)
        def names(sort, **opts):
            return [item['project'] for item in op.list_opportunities(self.store,
                      {'sort': sort, 'pageSize': 10, **opts}, self.admin)['items']]
        ascending = ['Old expired','Earliest future','Mid date','Latest date','No date']
        descending = ['Latest date','Mid date','Earliest future','Old expired','No date']
        self.assertEqual(names('due_asc'), ascending)
        self.assertEqual(names('due'), ascending)   # Existing API parameter still works.
        self.assertEqual(names('due_desc'), descending)
        self.assertEqual(names('due_asc', pageSize=2, page=2), ascending[2:4])
        self.assertEqual(names('due_desc', pageSize=2, page=3), descending[4:])
        self.assertEqual(names('due_desc', region='VIC'), [])
        self.assertEqual(len(names('due DESC; DROP TABLE opportunities')), 5)  # Allowlist SQL.

    def test_deadline_sort_also_applies_to_approved_after_expiry(self):
        for label, due in [('Approved old','2000-01-01'),('Approved soon','2099-02-02'),
                           ('Approved no deadline','')]:
            self.approve(self.create(project=label, due=due))
        names = lambda sort: [item['project'] for item in op.list_opportunities(self.store,
                {'status': 'approved', 'sort': sort}, self.admin)['items']]
        self.assertEqual(names('due_asc'), ['Approved old','Approved soon','Approved no deadline'])
        self.assertEqual(names('due_desc'), ['Approved soon','Approved old','Approved no deadline'])


if __name__ == '__main__':
    unittest.main()
