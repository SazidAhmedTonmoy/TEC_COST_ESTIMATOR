"""v3.7.14: team identities for calendar; recently added sort is stable."""
from unittest import TestCase
from unittest.mock import patch
from conest_app import opportunities as op
from tests.test_opportunities import OpportunityTests


class CalendarAndSort3714Tests(TestCase):
    setUp = OpportunityTests.setUp
    tearDown = OpportunityTests.tearDown
    make_user = staticmethod(OpportunityTests.make_user)
    create = OpportunityTests.create

    def approve(self, item):
        return op.decide(self.store, {
            'id': item['id'], 'revision': item['revision'],
            'decision': 'approved', 'reason': '',
        }, self.admin)['opportunity']

    def test_approved_calendar_includes_safe_teams_and_assignments(self):
        first = self.approve(self.create(project='TEC AU needs quote', due='2099-11-02'))
        first = op.update_authority(self.store, {
            'id': first['id'], 'revision': first['revision'],
            'assignedTeamIds': [self.team], 'assignedUserIds': [],
        }, self.admin, 'assign')['opportunity']
        second = self.approve(self.create(project='Two teams', due='2099-11-03'))
        second = op.update_authority(self.store, {
            'id': second['id'], 'revision': second['revision'],
            'assignedTeamIds': [self.other_team, self.team], 'assignedUserIds': [],
        }, self.admin, 'assign')['opportunity']
        third = self.approve(self.create(project='Already quoted', due='2099-11-04'))
        third['quoteStatus'] = 'quoted'
        with self.store.connect() as db:
            op._write(db, third)
        rows = op.approved_calendar(self.store, {'month': '2099-11'}, self.admin)
        by_name = {item['project']: item for item in rows['items']}
        self.assertEqual(by_name['TEC AU needs quote']['assignedTeamIds'], [self.team])
        self.assertEqual(by_name['Two teams']['assignedTeamIds'], sorted([self.team, self.other_team]))
        self.assertFalse(by_name['TEC AU needs quote']['quoted'])
        self.assertTrue(by_name['Already quoted']['quoted'])
        self.assertEqual(rows['quoted'], 1)
        self.assertEqual({r['id']: r['name'] for r in rows['teams']}[self.team], 'Opportunity test team')
        self.assertNotIn('workingScope', by_name['Two teams'])
        self.assertNotIn('createdBy', by_name['Two teams'])

    def test_recently_added_prefers_added_date_and_falls_back_to_creation_date(self):
        with patch.object(op.tenders, 'timestamp', return_value='2026-10-27T12:00:00Z'):
            first = self.create(project='Imported later', addedDate='2026-11-02')
        with patch.object(op.tenders, 'timestamp', return_value='2026-10-29T12:00:00Z'):
            second = self.create(project='Manual recent', addedDate='')
        with patch.object(op.tenders, 'timestamp', return_value='2026-10-30T12:00:00Z'):
            third = self.create(project='Imported earlier', addedDate='2026-10-28')
        names = lambda **filters: [item['project'] for item in op.list_opportunities(self.store, {'sort': 'added', **filters}, self.admin)['items']]
        self.assertEqual(names(), ['Imported later', 'Manual recent', 'Imported earlier'])
        with patch.object(op.tenders, 'timestamp', return_value='2026-12-30T12:00:00Z'):
            op.save(self.store, {'id': third['id'], 'revision': third['revision'], 'remarks': 'Updated in December'}, self.admin)
        self.assertEqual(names(), ['Imported later', 'Manual recent', 'Imported earlier'])
        self.assertEqual(names(pageSize=2, page=1), ['Imported later', 'Manual recent'])
        self.assertEqual(names(pageSize=2, page=2), ['Imported earlier'])
        self.assertEqual(len({i['id'] for page in (1, 2) for i in op.list_opportunities(self.store, {'sort': 'added', 'pageSize': 2, 'page': page}, self.admin)['items']}), 3)

    def test_added_date_tie_breaker_is_deterministic_and_region_filter_works(self):
        a = self.create(project='Same date one', addedDate='2099-01-03', region='VIC')
        b = self.create(project='Same date two', addedDate='2099-01-03', region='NSW')
        rows = op.list_opportunities(self.store, {'sort': 'added'}, self.admin)['items']
        self.assertEqual({row['id'] for row in rows}, {a['id'], b['id']})
        self.assertEqual([i['project'] for i in op.list_opportunities(self.store, {'sort': 'added', 'region': 'VIC'}, self.admin)['items']], ['Same date one'])
