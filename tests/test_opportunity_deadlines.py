"""Global deadline warnings, legacy display dates, and authenticated reads."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from conest_app import opportunities as op, tenders
from conest_app.database import connect
from conest_app.opportunity_deadlines import deadline_load
import test_opportunities as fixtures
import support_http as http_helpers


class OpportunityDeadlineTests(unittest.TestCase):
    setUp = fixtures.OpportunityTests.setUp
    make_user = staticmethod(fixtures.OpportunityTests.make_user)
    create = fixtures.OpportunityTests.create

    def tearDown(self):
        self.store.close()
        fixtures.OpportunityTests.tearDown(self)

    def lookup(self, due='2099-12-01', **params):
        return deadline_load(self.store, {'due': due, **params}, self.creator)

    def change_body(self, item, **changes):
        with self.store.connect() as db:
            body = json.loads(db.execute('SELECT body FROM opportunities WHERE id=?', (item['id'],)).fetchone()[0])
            body.update(changes)
            db.execute('UPDATE opportunities SET body=? WHERE id=?', (json.dumps(body), item['id']))

    def test_count_is_global_across_pages_statuses_teams_regions_and_multiple_builders(self):
        for number in range(27):
            item = self.create(project='Deadline project ' + str(number), due='2099-12-01',
                               region='NSW' if number % 2 else 'VIC')
            with self.store.connect() as db:
                body = json.loads(db.execute('SELECT body FROM opportunities WHERE id=?', (item['id'],)).fetchone()[0])
                body.update(status=op.STATUSES[number % len(op.STATUSES)],
                            assignedTeamIds=[self.team if number % 2 else self.other_team])
                db.execute('UPDATE opportunities SET body=?,status=? WHERE id=?',
                           (json.dumps(body), body['status'], item['id']))
        self.create(project='Previous day', due='2099-11-30')
        self.create(project='Following day', due='2099-12-02')
        self.create(project='No date', due='')
        result = self.lookup(page='2', pageSize='1', status='pending', region='NSW',
                             teamId=str(self.team), q='does not match')
        self.assertEqual(result, {'due': '2099-12-01', 'count': 27, 'teamGroups': [
            {'teamNames': ['Opportunity test team'], 'count': 13},
            {'teamNames': ['Other test team'], 'count': 14}]})
        self.assertEqual(self.lookup('2099-12-03'), {'due': '2099-12-03', 'count': 0, 'teamGroups': []})

    def test_team_combinations_count_each_project_once_and_do_not_infer_a_persons_team(self):
        self.create(project='First team only', due='2099-12-01', assignedTeamIds=[self.team])
        self.create(project='Second team only', due='2099-12-01', assignedTeamIds=[self.other_team])
        first_pair = self.create(project='Shared teams one', due='2099-12-01')
        second_pair = self.create(project='Shared teams two', due='2099-12-01')
        self.change_body(first_pair, assignedTeamIds=[self.other_team, self.team, self.team])
        self.change_body(second_pair, assignedTeamIds=[self.team, self.other_team])
        self.create(project='People only', due='2099-12-01', assignedUserIds=[self.member['id']])
        self.create(project='Nobody assigned', due='2099-12-01')
        result = self.lookup()
        self.assertEqual(result['teamGroups'], [
            {'teamNames': ['Opportunity test team'], 'count': 1},
            {'teamNames': ['Opportunity test team', 'Other test team'], 'count': 2},
            {'teamNames': ['Other test team'], 'count': 1},
            {'teamNames': [], 'count': 2}])
        self.assertEqual(result['count'], 6)
        self.assertEqual(sum(group['count'] for group in result['teamGroups']), result['count'])
        excluded = self.lookup(excludeId=first_pair['id'])
        self.assertEqual(excluded['count'], 5)
        self.assertEqual(excluded['teamGroups'][1]['count'], 1)
        self.assertEqual(sum(group['count'] for group in excluded['teamGroups']), excluded['count'])

    def test_team_names_are_live_and_missing_teams_are_grouped_without_writes(self):
        self.create(project='Live team name', due='2099-12-01', assignedTeamIds=[self.team])
        for number, assigned in enumerate(([999999], [999998, 999999, 999998])):
            item = self.create(project='Former teams ' + str(number), due='2099-12-01')
            self.change_body(item, assignedTeamIds=assigned)
        with connect() as db:
            db.execute('UPDATE teams SET name=? WHERE id=?', ('Renamed estimating team', self.team))
            account_before = list(db.iterdump())
        with self.store.connect() as db:
            tender_before = list(db.iterdump())
        result = self.lookup()
        self.assertEqual(result['teamGroups'], [
            {'teamNames': ['Former team'], 'count': 2},
            {'teamNames': ['Renamed estimating team'], 'count': 1}])
        self.assertEqual(result['count'], 3)
        with connect() as db:
            self.assertEqual(list(db.iterdump()), account_before)
        with self.store.connect() as db:
            self.assertEqual(list(db.iterdump()), tender_before)

    def test_edit_excludes_its_sql_id_even_when_legacy_json_id_is_absent(self):
        first = self.create(project='Edited project', due='2099-12-01')
        second = self.create(project='Other project', due='2099-12-01')
        with self.store.connect() as db:
            body = json.loads(db.execute('SELECT body FROM opportunities WHERE id=?', (first['id'],)).fetchone()[0])
            body.pop('id')
            db.execute('UPDATE opportunities SET body=? WHERE id=?', (json.dumps(body), first['id']))
        self.assertEqual(self.lookup(excludeId=first['id'])['count'], 1)
        self.assertEqual(self.lookup(excludeId=second['id'])['count'], 1)
        self.assertEqual(self.lookup(excludeId='not-an-existing-record')['count'], 2)

    def test_deleted_and_retired_records_are_excluded_but_restored_records_return(self):
        active, deleted, retired, restored = [
            self.create(project=name, due='2099-12-01')
            for name in ('Visible', 'Deleted', 'Retired', 'Restored')]
        op.delete(self.store, deleted, self.creator)
        with self.store.connect() as db:
            moment = tenders.timestamp()
            db.execute('INSERT INTO opportunity_reset_entries VALUES(?,?,?,NULL)',
                       ('opportunity', retired['id'], moment))
            db.execute('INSERT INTO opportunity_reset_entries VALUES(?,?,?,?)',
                       ('opportunity', restored['id'], moment, moment))
        self.assertEqual(self.lookup()['count'], 2)
        self.assertEqual(self.lookup(excludeId=active['id'])['count'], 1)

    def test_legacy_date_fallback_uses_only_an_absent_key_and_preserves_cleared_dates(self):
        target = '2099-12-01'
        cases = [
            ('Displayed date', target, '2099-12-02'),
            ('Different displayed date', '2099-12-02', target),
            ('Blank displayed date', '', target),
            ('Null displayed date', None, target),
            ('Absent displayed date', 'absent', target),
        ]
        for name, displayed, sql_due in cases:
            item = self.create(project=name, due=sql_due)
            with self.store.connect() as db:
                body = json.loads(db.execute('SELECT body FROM opportunities WHERE id=?', (item['id'],)).fetchone()[0])
                if displayed == 'absent':
                    body.pop('due')
                else:
                    body['due'] = displayed
                db.execute('UPDATE opportunities SET body=? WHERE id=?', (json.dumps(body), item['id']))
        self.assertEqual(self.lookup()['count'], 2)
        self.assertEqual(self.lookup('2099-12-02')['count'], 1)

    def test_exact_calendar_date_is_required_and_invalid_exclusion_is_rejected(self):
        self.create(project='Leap-day project', due='2080-02-29')
        self.assertEqual(self.lookup('2080-02-29'), {'due': '2080-02-29', 'count': 1,
                                                  'teamGroups': [{'teamNames': [], 'count': 1}]})
        for value in ('', None, '2099-02-29', '2099-13-01', '2099-2-01',
                      '20991201', '2099-W49-2', '2099-12-01T09:00', '01/12/2099', 123):
            with self.subTest(due=value), self.assertRaises(tenders.ValidationError) as error:
                self.lookup(value)
            self.assertEqual(error.exception.status, 400)
        for exclude in ('x' * 101, {'id': 'one'}):
            with self.subTest(exclude=exclude), self.assertRaises(tenders.ValidationError) as error:
                self.lookup(excludeId=exclude)
            self.assertEqual(error.exception.status, 400)

    def test_check_does_not_expire_records_or_change_history_assignments_or_generation(self):
        item = self.create(project='Past but deliberately awaiting decision', due='2000-01-01')
        with self.store.connect() as db:
            body = json.loads(db.execute('SELECT body FROM opportunities WHERE id=?', (item['id'],)).fetchone()[0])
            body['status'] = 'pending'
            db.execute('UPDATE opportunities SET body=?,status=? WHERE id=?',
                       (json.dumps(body), 'pending', item['id']))
            before = list(db.iterdump())
        self.assertEqual(self.lookup('2000-01-01')['count'], 1)
        self.assertEqual(self.lookup('2000-01-01', excludeId=item['id'])['count'], 0)
        with self.store.connect() as db:
            self.assertEqual(list(db.iterdump()), before)

    def test_all_active_users_can_read_but_inactive_and_unknown_accounts_cannot(self):
        self.create(project='Readable deadline', due='2099-12-01')
        for actor in (self.admin, self.creator, self.member, self.outsider, self.no_team):
            with self.subTest(actor=actor['id']):
                self.assertEqual(deadline_load(self.store, {'due': '2099-12-01'}, actor)['count'], 1)
        with connect() as db:
            db.execute('UPDATE users SET is_active=0 WHERE id=?', (self.member['id'],))
        for actor in (self.member, {'id': 999999999, 'role': 'admin'}):
            with self.subTest(actor=actor), self.assertRaises(tenders.ValidationError) as error:
                deadline_load(self.store, {'due': '2099-12-01'}, actor)
            self.assertEqual(error.exception.status, 403)


class OpportunityDeadlineHttpTests(unittest.TestCase):
    request = http_helpers.HttpPatchTests.request

    def setUp(self):
        tenders.close_store()
        http_helpers.HttpPatchTests.setUp(self)
        self.tender_environment = patch.dict('os.environ', {
            'CONEST_TENDERS_DB_PATH': str(Path(self.tmp.name) / 'deadline-http.db')})
        self.tender_environment.start()

    def tearDown(self):
        tenders.close_store()
        self.tender_environment.stop()
        http_helpers.HttpPatchTests.tearDown(self)

    def test_authenticated_route_contract_no_store_cache_and_invalid_date(self):
        status, created = self.request('POST', '/api/tenders/opportunities/save', {
            'project': 'HTTP deadline warning', 'region': 'NSW', 'due': '2099-12-01',
            'builders': ['Builder One', 'Builder Two']})
        self.assertEqual(status, 200, created)
        identifier = created['opportunity']['id']
        path = '/api/tenders/opportunities/deadline-load?due=2099-12-01'
        status, result = self.request('GET', path)
        self.assertEqual(status, 200, result)
        self.assertEqual(result, {'due': '2099-12-01', 'count': 1,
                                  'teamGroups': [{'teamNames': [], 'count': 1}]})
        self.assertEqual(self.last_headers.get('Cache-Control'), 'no-store')
        status, result = self.request('GET', path + '&excludeId=' + identifier)
        self.assertEqual((status, result['count']), (200, 0))
        self.assertEqual(self.request('GET', path.replace('2099-12-01', '2099-W49-2'))[0], 400)
        self.cookie = self.csrf = ''
        self.assertEqual(self.request('GET', path)[0], 401)


if __name__ == '__main__':
    unittest.main()
