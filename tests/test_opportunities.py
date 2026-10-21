"""Workflow/security regression tests against private temporary databases."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from conest_app import opportunities as op, tenders
from conest_app.database import connect
from conest_app.opportunity_import import initialize_seed


class OpportunityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {
            'CONEST_DB_PATH': str(Path(self.temp.name) / 'accounts.db'),
            'CONEST_TENDERS_DB_PATH': str(Path(self.temp.name) / 'tenders.db'),
        })
        self.environment.start()
        with connect() as db:
            self.admin = dict(db.execute("SELECT id,name,role,team_id FROM users WHERE role='admin' LIMIT 1").fetchone())
            stamp = tenders.timestamp()
            self.team = db.execute('INSERT INTO teams(name,created_at,updated_at) VALUES(?,?,?)',
                                   ('Opportunity test team', stamp, stamp)).lastrowid
            self.other_team = db.execute('INSERT INTO teams(name,created_at,updated_at) VALUES(?,?,?)',
                                         ('Other test team', stamp, stamp)).lastrowid
            self.creator = self.make_user(db, 'Creator', None)
            self.member = self.make_user(db, 'Member', self.team)
            self.outsider = self.make_user(db, 'Other', self.other_team)
            self.no_team = self.make_user(db, 'NoTeam', None)
        self.store = tenders.Store(Path(self.temp.name) / 'tenders.db')

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    @staticmethod
    def make_user(db, name, team):
        stamp = tenders.timestamp()
        identifier = db.execute('''INSERT INTO users
            (username,name,password_hash,role,team_id,is_active,must_change_password,created_at,updated_at)
            VALUES(?,?,?,'user',?,1,0,?,?)''', ('optest' + name, name, 'not-a-login-hash', team, stamp, stamp)).lastrowid
        return {'id': identifier, 'name': name, 'role': 'user', 'team_id': team}

    def create(self, **changes):
        return op.save(self.store, {'project': 'Test opportunity', 'region': 'NSW',
                       'builders': ['Builder One', 'Builder Two'], 'due': '2099-03-04',
                       'workingScope': 'Power, lighting and communications', **changes}, self.creator)['opportunity']

    def assert_denied(self, operation, status=403):
        with self.assertRaises(tenders.ValidationError) as caught:
            operation()
        self.assertEqual(caught.exception.status, status, str(caught.exception))

    def test_creator_admin_and_delegated_edit_authority(self):
        item = self.create()
        self.assertEqual(item['status'], 'pending')
        self.assertFalse(op.permissions(item, self.creator)['approve'])
        self.assert_denied(lambda: op.save(self.store, {**item, 'remarks': 'Unauthorised'}, self.member))
        access = op.update_authority(self.store, {**item, 'editorTeamIds': [self.team]}, self.creator, 'access')['opportunity']
        edited = op.save(self.store, {**access, 'workingScope': 'New authorised scope'}, self.member)['opportunity']
        self.assertEqual(edited['workingScope'], 'New authorised scope')
        for actor in (self.member, self.outsider):
            self.assert_denied(lambda actor=actor: op.delete(self.store, edited, actor))
            self.assert_denied(lambda actor=actor: op.update_authority(self.store, {**edited, 'assignedUserIds': [actor['id']]}, actor, 'assign'))
        self.assert_denied(lambda: op.save(self.store, {**edited, 'editorUserIds': [self.outsider['id']]}, self.member))
        self.assert_denied(lambda: op.save(self.store, {**edited, 'createdBy': self.member['id'], 'assignedTeamIds': [self.other_team]}, self.member))
        admin_edit = op.save(self.store, {**edited, 'remarks': 'Admin review'}, self.admin)['opportunity']
        self.assertEqual(admin_edit['remarks'], 'Admin review')

    def test_approval_team_members_admin_and_live_role_checks(self):
        item = self.create()
        self.assert_denied(lambda: op.decide(self.store, {**item, 'decision': 'approved'}, self.creator))
        approved = op.decide(self.store, {**item, 'decision': 'approved'}, self.member)['opportunity']
        self.assertEqual(approved['decisionBy'], self.member['id'])
        self.assertEqual(approved['status'], 'approved')
        reopened = op.decide(self.store, {**approved, 'decision': 'pending'}, self.creator)['opportunity']
        rejected = op.decide(self.store, {**reopened, 'decision': 'rejected', 'reason': 'Outside our scope'}, self.admin)['opportunity']
        self.assertEqual(rejected['decisionBy'], self.admin['id'])
        self.assertEqual(rejected['status'], 'rejected')
        reopened = op.decide(self.store, {**rejected, 'decision': 'pending'}, self.creator)['opportunity']
        # Forging an admin role or holding a stale team_id cannot bypass live membership.
        self.assert_denied(lambda: op.decide(self.store, {**reopened, 'decision': 'approved'}, {**self.no_team, 'role': 'admin'}))
        with connect() as db:
            db.execute('UPDATE users SET team_id=NULL WHERE id=?', (self.member['id'],))
        self.assert_denied(lambda: op.decide(self.store, {**reopened, 'decision': 'approved'}, self.member))

    def test_revision_conflict_cannot_overwrite_or_delete(self):
        item = self.create()
        latest = op.save(self.store, {**item, 'remarks': 'Other window'}, self.creator)['opportunity']
        self.assert_denied(lambda: op.save(self.store, {**item, 'remarks': 'Stale'}, self.creator), 409)
        self.assert_denied(lambda: op.delete(self.store, item, self.creator), 409)
        self.assertEqual(op.detail(self.store, item['id'], self.creator)['opportunity']['revision'], latest['revision'])

    def test_assignments_notify_all_team_members_and_per_user_read(self):
        item = self.create()
        assigned = op.update_authority(self.store, {**item, 'assignedTeamIds': [self.team],
                    'assignedUserIds': [self.no_team['id']]}, self.creator, 'assign')['opportunity']
        def relevant(person):
            return [n for n in op.notifications(self.store, {'pageSize': 100}, person)['items']
                    if n.get('opportunityId') == item['id'] and n['kind'] == 'assignment']
        member_notice = relevant(self.member)
        person_notice = relevant(self.no_team)
        self.assertEqual(len(member_notice), 1)
        self.assertEqual(len(person_notice), 1)
        self.assertFalse(member_notice[0]['read'])
        op.mark_read(self.store, {'ids': [member_notice[0]['id']]}, self.no_team)
        self.assertFalse(relevant(self.member)[0]['read'])
        generation = op.generation(self.store)
        op.mark_read(self.store, {'ids': [member_notice[0]['id']]}, self.member)
        self.assertTrue(relevant(self.member)[0]['read'])
        self.assertFalse(relevant(self.no_team)[0]['read'])
        self.assertEqual(op.generation(self.store), generation)
        filtered = op.list_opportunities(self.store, {'teamId': str(self.team)}, self.admin)
        self.assertEqual([r['id'] for r in filtered['items']], [assigned['id']])

    def test_expiry_uses_australian_midnight_and_preserves_rejection(self):
        with patch.object(op, '_today', return_value=date(2026, 10, 21)):
            item = self.create(due='2026-10-21')
            rejected = self.create(project='Rejected before deadline', due='2026-10-21')
            rejected = op.decide(self.store, {**rejected, 'decision': 'rejected', 'reason': 'No capacity'}, self.admin)['opportunity']
        # Sydney/Melbourne daylight saving: UTC 12:59 is still 21 October.
        op.process_due(self.store, force=True, now=datetime(2026, 10, 21, 12, 59, tzinfo=timezone.utc))
        with self.store.connect() as db:
            self.assertEqual(op._find(db, item['id'])['status'], 'pending')
        op.process_due(self.store, force=True, now=datetime(2026, 10, 21, 13, 0, tzinfo=timezone.utc))
        op.process_due(self.store, force=True, now=datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc))
        with self.store.connect() as db:
            self.assertEqual(op._find(db, item['id'])['status'], 'expired')
            self.assertEqual(op._find(db, rejected['id'])['status'], 'rejected')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM opportunity_activity WHERE opportunity_id=? AND action='Expired opportunity'", (item['id'],)).fetchone()[0], 1)
        expired = op.detail(self.store, item['id'], self.creator)['opportunity']
        extended = op.save(self.store, {**expired, 'due': '2099-04-05'}, self.creator)['opportunity']
        self.assertEqual(extended['status'], 'pending')
        self.assertIsNone(extended['decisionBy'])

    def test_delete_retains_audit_and_seed_is_not_replayed(self):
        seed = op.list_opportunities(self.store, {'pageSize': 100}, self.admin)
        self.assertEqual(seed['total'], 54)
        target = seed['items'][0]
        op.delete(self.store, target, self.admin)
        self.assertEqual(initialize_seed(self.store)['added'], 0)
        items = op.list_opportunities(self.store, {'pageSize': 100}, self.admin)
        self.assertEqual(items['total'], 53)
        self.assertNotIn(target['id'], {row['id'] for row in items['items']})
        audit = op.detail(self.store, target['id'], self.admin)
        self.assertEqual(audit['activity'][0]['action'], 'Deleted opportunity')
        self.assert_denied(lambda: op.detail(self.store, target['id'], self.no_team))
        self.assert_denied(lambda: op.list_opportunities(self.store, {'status': 'deleted'}, self.admin), 400)

    def test_region_defaults_and_manual_new_region(self):
        nsw = self.create()
        vic = self.create(project='Victoria', region='VIC')
        self.assertEqual(nsw['distanceOrigin'], '63-79 Parramatta Rd Silverwater, NSW 2128')
        self.assertEqual(vic['distanceOrigin'], 'CBD, Melbourne')
        self.assert_denied(lambda: self.create(project='New region', region='QLD'), 400)
        qld = self.create(project='New region', region='QLD', distanceOrigin='Brisbane office')
        regions = op.regions(self.store, self.creator)['regions']
        self.assertEqual([r['code'] for r in regions], ['NSW', 'QLD', 'VIC'])
        self.assertEqual(qld['distanceOrigin'], 'Brisbane office')
        self.assert_denied(lambda: op.regions(self.store, self.creator, {'code': 'QLD', 'origin': 'Changed'}))

    def test_reminder_notifications_do_not_complete_reminders(self):
        submission = self.store.all_data()['submissions'][0]
        with self.store.connect(write=True) as db:
            self.store.insert_reminder(db, submission['id'], '2026-10-21T10:00', 'Call the builder')
        moment = datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc)
        op.process_due(self.store, force=True, now=moment)
        first = op.notifications(self.store, {'pageSize': 100}, self.member)
        reminders = [r for r in first['items'] if r['kind'] == 'reminder']
        self.assertTrue(reminders)
        op.mark_read(self.store, {'ids': [r['id'] for r in reminders]}, self.member)
        op.process_due(self.store, force=True, now=moment)
        with self.store.connect() as db:
            self.assertFalse(json.loads(db.execute('SELECT body FROM reminders ORDER BY id DESC LIMIT 1').fetchone()[0])['done'])
            counts = db.execute('''SELECT user_id,event_key,COUNT(*) n FROM tender_notifications
                WHERE kind='reminder' GROUP BY user_id,event_key HAVING COUNT(*)>1''').fetchall()
            self.assertEqual(counts, [])

    def test_import_generation_is_atomic_and_seed_approvers_unknown(self):
        generation = op.generation(self.store)
        self.create()
        self.assert_denied(lambda: op.import_records(self.store, [{'project': 'Import', 'region': 'NSW'}],
            self.creator, 'import.xlsx', expected_generation=generation), 409)
        result = op.import_records(self.store, [{'project': 'Import', 'region': 'NSW', 'sourceStatus': 'approved'}],
            self.creator, 'import.xlsx', expected_generation=op.generation(self.store))
        item = op.detail(self.store, result['items'][0], self.creator)['opportunity']
        self.assertEqual(item['status'], 'pending')
        self.assertEqual(item['sourceStatus'], 'approved')
        self.assertIsNone(item['decisionBy'])
        with self.store.connect() as db:
            events = db.execute("SELECT details FROM tender_activity WHERE actor_id=? AND action='Imported opportunities Excel'", (self.creator['id'],)).fetchall()
            self.assertEqual(len(events), 1)
            self.assertEqual(json.loads(events[0][0])['added'], 1)

    def test_activity_cursor_can_retrieve_all_history_without_overlap(self):
        item = self.create()
        with op._transaction(self.store) as db:
            for number in range(205):
                op._activity(self.store, db, self.creator, 'Updated opportunity', item, {'sequence': number})
        first = op.detail(self.store, item['id'], self.creator)
        self.assertEqual(first['activityTotal'], 206)
        self.assertEqual(len(first['activity']), 200)
        self.assertTrue(first['hasMoreActivity'])
        second = op.activity_history(self.store, {'id': item['id'], 'before': first['nextActivityCursor']}, self.creator)
        self.assertEqual(len(second['activity']), 6)
        self.assertFalse(second['hasMoreActivity'])
        self.assertFalse({r['id'] for r in first['activity']} & {r['id'] for r in second['activity']})


if __name__ == '__main__':
    unittest.main()
