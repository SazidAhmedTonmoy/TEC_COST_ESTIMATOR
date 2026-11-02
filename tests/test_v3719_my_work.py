"""v3.7.19 dashboard inbox: read-only, assigned-user/team scoping and live reminders."""
import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from conest_app import opportunities as op, tenders
from conest_app.my_work import summary
from tests import test_opportunities as fixture

NOW = datetime(2026, 11, 2, 11, 30, tzinfo=ZoneInfo('Australia/Sydney'))


class MyWorkTests(unittest.TestCase):
    setUp = fixture.OpportunityTests.setUp
    tearDown = fixture.OpportunityTests.tearDown
    create = fixture.OpportunityTests.create
    make_user = staticmethod(fixture.OpportunityTests.make_user)

    def assign(self, item, *team_ids, users=(), status=None, due=None):
        with self.store.connect(write=True) as db:
            obj = op._find(db, item['id'])
            obj['assignedTeamIds'] = list(team_ids)
            obj['assignedUserIds'] = list(users)
            if status is not None:
                obj['status'] = status
            if due is not None:
                obj['due'] = due
            op._write(db, obj)
        return obj

    def test_personal_and_team_views_do_not_show_other_teams_or_unowned_work(self):
        self.assign(self.create(project='My team approval'), self.team, status='pending', due='2026-11-04')
        self.assign(self.create(project='Other team'), self.other_team, status='approved', due='2026-11-04')
        self.assign(self.create(project='Assigned direct'), users=[self.member['id']], status='approved', due='2026-11-20')
        mine = summary(self.store, self.member, now=NOW)
        team = summary(self.store, self.member, 'team', now=NOW)
        self.assertEqual(mine['counts']['needsApproval'], 1)
        self.assertEqual(mine['counts']['needsQuote'], 1)
        self.assertEqual(mine['counts']['dueSoon'], 1)
        self.assertEqual(team['counts']['needsQuote'], 1)
        projects = {a['project'] for a in mine['actions']}
        self.assertEqual(projects, {'My team approval', 'Assigned direct'})
        self.assertNotIn('Other team', {a['project'] for a in team['actions']})
        with self.assertRaises(tenders.ValidationError):
            summary(self.store, self.no_team, 'team', now=NOW)
        with self.assertRaises(tenders.ValidationError):
            summary(self.store, self.member, 'all', now=NOW)

    def test_quote_and_link_are_excluded_from_urgent_deadline_and_needs_quote(self):
        item = self.assign(self.create(project='Already quoted'), self.team,
                           status='approved', due='2026-11-02')
        with self.store.connect(write=True) as db:
            record = op._find(db, item['id']); record['quoteStatus'] = 'quoted'; op._write(db, record)
        active = self.assign(self.create(project='Ready for quote'), self.team,
                             status='approved', due='2026-11-05')
        response = summary(self.store, self.member, now=NOW)
        self.assertEqual(response['counts']['needsQuote'], 1)
        self.assertEqual(response['counts']['dueSoon'], 1)
        self.assertEqual({a['project'] for a in response['actions']}, {'Ready for quote'})
        self.assertEqual(response['actions'][0]['title'], 'Deadline approaching')

    def test_due_reminders_are_scoped_to_submission_and_exclude_completed(self):
        first = self.assign(self.create(project='Linked quote'), self.team, status='approved')
        second = self.assign(self.create(project='Not our project'), self.other_team, status='approved')
        with self.store.connect(write=True) as db:
            for id_, opportunity in [('mine-submission', first), ('other-submission', second)]:
                submission = {'id': id_, 'project': opportunity['project'], 'builder': 'Builder',
                              'opportunityId': opportunity['id'], 'status': 'Open'}
                db.execute('INSERT INTO submissions (id,body,revision) VALUES (?,?,0)',
                           (id_, json.dumps(submission)))
                reminder = {'id': id_+'-reminder', 'submissionId': id_,
                            'due': '2026-11-02T09:00', 'note': 'Call builder', 'done': False}
                db.execute('INSERT INTO reminders (id,submission_id,body) VALUES (?,?,?)',
                           (reminder['id'], id_, json.dumps(reminder)))
            later = {'id': 'future', 'submissionId': 'mine-submission',
                     'due': '2026-11-03T12:00', 'done': False}
            db.execute('INSERT INTO reminders (id,submission_id,body) VALUES (?,?,?)',
                       (later['id'], 'mine-submission', json.dumps(later)))
        result = summary(self.store, self.member, now=NOW)
        self.assertEqual(result['counts']['followUpsDue'], 1)
        self.assertEqual(result['actions'][0]['kind'], 'chase')
        self.assertEqual(result['actions'][0]['id'], 'mine-submission')

    def test_authenticated_route_uses_same_backend_summary_without_writes(self):
        from types import SimpleNamespace
        from conest_app.opportunity_http import route
        item = self.assign(self.create(project='Dashboard API'), self.team,
                           status='pending', due='2026-11-03')
        before = op.generation(self.store)
        result = {}
        handler = SimpleNamespace(command='GET', user=self.member,
                                  path='/api/tenders/opportunities/my-work?scope=mine')
        self.assertTrue(route(handler, '/api/tenders/opportunities/my-work', self.store,
                              lambda _handler, value: result.update(value)))
        self.assertEqual(result['counts']['needsApproval'], 1)
        self.assertEqual(result['actions'][0]['id'], item['id'])
        self.assertEqual(op.generation(self.store), before)

    def test_admin_can_explicitly_see_all_teams_but_personal_is_bounded(self):
        self.assign(self.create(project='Other assigned team'), self.other_team,
                    status='approved', due='2026-11-10')
        mine = summary(self.store, self.admin, now=NOW)
        teams = summary(self.store, self.admin, 'team', now=NOW)
        self.assertEqual(mine['counts']['needsQuote'], 0)
        self.assertEqual(teams['counts']['needsQuote'], 1)
        self.assertEqual(teams['scopeLabel'], 'All teams')


if __name__ == '__main__':
    unittest.main()
