"""Assignment approval, permanent decisions and atomic quotation handoff."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import json
import sqlite3
import threading
import unittest
from unittest.mock import patch

import test_opportunities as shared
from conest_app import opportunities as op, tenders
from conest_app import opportunity_workflow_upgrade as upgrade
from conest_app.opportunity_reset import RESET_KEY


class OpportunityWorkflowTests(unittest.TestCase):
    setUp = shared.OpportunityTests.setUp
    tearDown = shared.OpportunityTests.tearDown
    make_user = staticmethod(shared.OpportunityTests.make_user)
    create = shared.OpportunityTests.create
    assert_denied = shared.OpportunityTests.assert_denied

    def approved(self, **changes):
        item = self.create(**changes)
        return op.decide(self.store, {**item, 'decision': 'approved'}, self.admin)['opportunity']

    def quote_payload(self, item, **changes):
        return {'id': item['id'], 'revision': item['revision'], 'value': 125000,
                'note': 'Electrical services including lighting and power', 'quoteNo': 'TEC-357',
                'submittedDate': '2026-10-22', 'submittedByTeamId': self.team,
                'builders': item['builders'], **changes}

    def snapshot(self):
        with self.store.connect() as db:
            return {table: [tuple(row) for row in db.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                    for table in ('opportunities', 'opportunity_people', 'opportunity_activity',
                                  'submissions', 'tender_activity', 'tender_notifications',
                                  'opportunity_generation', 'tender_generation')}

    def test_rejection_reason_is_optional_and_still_audited(self):
        for index, reason in enumerate((None, '', '   ')):
            item = self.create(project='Blank rejection ' + str(index))
            result = op.decide(self.store, {**item, 'decision': 'rejected', 'reason': reason}, self.admin)
            self.assertEqual(result['opportunity']['status'], 'rejected')
            self.assertEqual(result['opportunity']['decisionReason'], '')
            event = result['activity'][0]
            self.assertEqual(event['action'], 'Rejected opportunity')
            self.assertEqual(event['actorId'], self.admin['id'])
            self.assertEqual(event['details']['reason'], '')

    def test_team_assignment_approves_expired_for_authorised_creator(self):
        item = self.create(due='2000-01-01')
        self.assertEqual(item['status'], 'expired')
        assigned = op.update_authority(self.store, {**item, 'assignedTeamIds': [self.team]},
                                       self.creator, 'assign')['opportunity']
        self.assertEqual(assigned['status'], 'approved')
        self.assertEqual(assigned['decisionBy'], self.creator['id'])
        self.assertEqual(assigned['revision'], item['revision'] + 1)
        notices = op.notifications(self.store, {'pageSize': 100}, self.member)['items']
        kinds = [row['kind'] for row in notices if row.get('opportunityId') == item['id']]
        self.assertIn('assignment', kinds)
        self.assertIn('approved', kinds)
        with self.store.connect() as db:
            row = db.execute("SELECT details FROM opportunity_activity WHERE opportunity_id=? AND action='Approved opportunity'",
                             (item['id'],)).fetchone()
        self.assertTrue(json.loads(row[0])['automatic'])
        counts = op.list_opportunities(self.store, {}, self.admin)['counts']
        self.assertEqual((counts['approved'], counts['expired']), (1, 0))

    def test_assigned_creation_and_save_approve_but_person_only_does_not(self):
        item = self.create(project='Assigned on create', due='2000-01-01', assignedTeamIds=[self.team])
        self.assertEqual(item['status'], 'approved')
        expired = self.create(project='Assign while saving', due='2000-01-01')
        assigned = op.save(self.store, {**expired, 'assignedTeamIds': [self.team]}, self.creator)['opportunity']
        self.assertEqual(assigned['status'], 'approved')
        individual = self.create(project='Person only', due='2000-01-01', assignedUserIds=[self.member['id']])
        self.assertEqual(individual['status'], 'expired')

    def test_existing_team_selection_can_approve_without_assignment_diff(self):
        item = self.create(assignedTeamIds=[self.team])
        with self.store.connect() as db:
            legacy = {**item, 'status': 'expired'}
            op._write(db, legacy)
        result = op.update_authority(self.store, {**legacy, 'assignedTeamIds': [self.team]},
                                     self.creator, 'assign')['opportunity']
        self.assertEqual(result['status'], 'approved')
        self.assertEqual(result['revision'], legacy['revision'] + 1)

    def test_approved_survives_past_date_edit_sweep_and_unassignment(self):
        item = self.create(assignedTeamIds=[self.team])
        changed = op.save(self.store, {**item, 'due': '2000-01-01'}, self.creator)['opportunity']
        self.assertEqual(changed['status'], 'approved')
        decision = (changed['decisionBy'], changed['decisionAt'])
        unassigned = op.update_authority(self.store, {**changed, 'assignedTeamIds': []}, self.creator, 'assign')['opportunity']
        op.process_due(self.store, force=True, now=datetime(2099, 1, 1, tzinfo=timezone.utc))
        kept = op.detail(self.store, item['id'], self.admin)['opportunity']
        self.assertEqual(kept['status'], 'approved')
        self.assertEqual(kept['revision'], unassigned['revision'])
        self.assertEqual((kept['decisionBy'], kept['decisionAt']), decision)
        with self.store.connect() as db:
            self.assertFalse(db.execute("SELECT 1 FROM opportunity_activity WHERE opportunity_id=? AND action='Expired opportunity'",
                                        (item['id'],)).fetchone())

    def test_manual_approval_accepts_expired_and_rejects_without_note(self):
        item = self.approved(due='2000-01-01')
        self.assertEqual(item['status'], 'approved')
        repeated = op.decide(self.store, {**item, 'decision': 'approved'}, self.member)['opportunity']
        self.assertEqual(repeated['revision'], item['revision'])
        result = op.decide(self.store, {**item, 'decision': 'rejected'}, self.member)['opportunity']
        self.assertEqual((result['status'], result.get('quoteStatus', ''), result['decisionReason']), ('rejected', '', ''))
        self.assertNotIn('notQuotedBy', result)
        again = op.update_authority(self.store, {**result, 'assignedTeamIds': [self.team]}, self.creator, 'assign')['opportunity']
        self.assertEqual(again['status'], 'approved')
        self.assertEqual(again.get('quoteStatus', ''), '')

    def test_seed_approved_deadline_does_not_override_recorded_status(self):
        imported = op.import_records(self.store, [{
            'project': 'Historically approved seed', 'region': 'VIC', 'due': '2000-01-01',
            'builders': [], 'sourceStatus': 'approved',
        }], self.admin, 'fixture.xlsx', seed_key='test-v357-seed')
        item = op.detail(self.store, imported['items'][0], self.admin)['opportunity']
        self.assertEqual(item['status'], 'approved')

    def test_quote_creates_real_linked_builder_submissions_and_refreshes_caches(self):
        item = self.approved(link='https://example.test/plans', remarks='Original opportunity notes')
        first_cache = self.store.all_data()
        other_store = tenders.Store(self.store.path)
        other_cache = other_store.all_data()
        result = op.quote(self.store, self.quote_payload(item), self.member)
        quoted = result['opportunity']
        self.assertEqual((quoted['status'], quoted['quoteStatus']), ('approved', 'quoted'))
        self.assertEqual(quoted['submissionIds'], result['submissionIds'])
        self.assertEqual(len(result['submissionIds']), 2)
        self.assertEqual((quoted['decisionBy'], quoted['decisionAt']), (item['decisionBy'], item['decisionAt']))
        new_cache = self.store.all_data()
        self.assertIsNot(first_cache, new_cache)
        self.assertIsNot(other_cache, other_store.all_data())
        rows = [row for row in new_cache['submissions'] if row['id'] in result['submissionIds']]
        self.assertEqual({row['builder'] for row in rows}, set(item['builders']))
        for row in rows:
            self.assertEqual(row['value'], 125000)
            self.assertEqual(row['status'], 'Open')
            self.assertEqual(row['opportunityId'], item['id'])
            self.assertEqual(row['opportunityLink'], item['link'])
            self.assertEqual(row['workingScope'], item['workingScope'])
            self.assertEqual(row['opportunityRemarks'], item['remarks'])
            self.assertEqual(row['remarks'], self.quote_payload(item)['note'])
            self.assertEqual(row['submittedDate'], '2026-10-22')
            self.assertEqual(row['due'], item['due'])
            self.assertEqual(row['submittedByTeamId'], self.team)
            self.assertEqual(row['contact'], '')
            self.assertEqual(row['email'], '')
        with self.store.connect() as db:
            contribution = db.execute("SELECT actor_id,details FROM tender_activity WHERE action='Quoted opportunity'").fetchone()
            self.assertEqual(contribution['actor_id'], self.member['id'])
            self.assertEqual(json.loads(contribution['details'])['submissionIds'], result['submissionIds'])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        notices = op.notifications(self.store, {'pageSize': 100}, self.creator)['items']
        self.assertTrue(any(row['kind'] == 'quoted' and row.get('opportunityId') == item['id'] for row in notices))

    def test_quote_allows_zero_blank_notes_unassigned_and_one_selected_builder(self):
        item = self.create(assignedTeamIds=[self.team])
        with patch.object(op, '_today', return_value=date(2026, 10, 22)):
            result = op.quote(self.store, self.quote_payload(item, value=0, note='', quoteNo='',
                submittedDate='', submittedByTeamId=None, builders=[item['builders'][1]]), self.admin)
        self.assertEqual(len(result['submissionIds']), 1)
        quoted = result['opportunity']
        self.assertEqual((quoted['quotedValue'], quoted['quoteNote'], quoted['quoteNo']), (0, '', ''))
        self.assertEqual(quoted['submittedDate'], '2026-10-22')
        self.assertIsNone(quoted['submittedByTeamId'])

    def test_quote_validation_and_live_authorisation_leave_no_partial_writes(self):
        item = self.approved()
        before = self.snapshot()
        for change in ({'value': None}, {'value': ''}, {'value': True}, {'value': -1},
                       {'value': float('nan')}, {'value': float('inf')}, {'value': '12000'},
                       {'builders': []}, {'builders': ['Unrelated builder']}, {'builders': 'Builder One'},
                       {'submittedByTeamId': True}, {'submittedByTeamId': 999999},
                       {'submittedDate': '2026-02-30'}, {'note': []}):
            with self.subTest(change=change):
                self.assert_denied(lambda: op.quote(self.store, self.quote_payload(item, **change), self.admin), 400)
                self.assertEqual(self.snapshot(), before)
        self.assert_denied(lambda: op.quote(self.store, self.quote_payload(item), self.creator))
        self.assert_denied(lambda: op.quote(self.store, self.quote_payload(item), {**self.no_team, 'role': 'admin'}))
        self.assertEqual(self.snapshot(), before)

    def test_quote_requires_approval_and_current_revision(self):
        item = self.create()
        self.assert_denied(lambda: op.quote(self.store, self.quote_payload(item), self.admin), 409)
        approved = op.decide(self.store, {**item, 'decision': 'approved'}, self.admin)['opportunity']
        before = self.snapshot()
        self.assert_denied(lambda: op.quote(self.store, self.quote_payload(item), self.admin), 409)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(op.quote(self.store, self.quote_payload(approved), self.admin)['quoted'])

    def test_quote_exact_retry_is_idempotent_but_changed_retry_is_rejected(self):
        item = self.approved()
        payload = self.quote_payload(item)
        first = op.quote(self.store, payload, self.member)
        snapshot = self.snapshot()
        second = op.quote(self.store, payload, self.member)
        self.assertTrue(second['alreadyQuoted'])
        self.assertEqual(second['submissionIds'], first['submissionIds'])
        self.assertEqual(self.snapshot(), snapshot)
        self.assert_denied(lambda: op.quote(self.store, {**payload, 'value': 999}, self.member), 409)
        self.assertEqual(self.snapshot(), snapshot)

    def test_concurrent_quote_requests_create_one_group(self):
        item = self.approved()
        payload = self.quote_payload(item)
        barrier = threading.Barrier(2)

        def submit():
            barrier.wait(timeout=5)
            return op.quote(self.store, payload, self.admin)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(submit), pool.submit(submit)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(results[0]['submissionIds'], results[1]['submissionIds'])
        self.assertEqual(sum(bool(row.get('alreadyQuoted')) for row in results), 1)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM opportunity_activity WHERE action='Quoted opportunity'").fetchone()[0], 1)

    def test_existing_project_group_is_never_overwritten_by_conversion(self):
        item = self.approved()
        self.store.save_submission({'project': item['project'].upper(), 'builder': 'Different existing builder',
                                    'value': 123, 'status': 'Won', '_actor_id': self.admin['id'], 'author': self.admin['name']})
        snapshot = self.snapshot()
        with self.assertRaises(tenders.ValidationError) as caught:
            op.quote(self.store, self.quote_payload(item), self.admin)
        self.assertEqual(caught.exception.status, 409)
        self.assertIn('Project Chase-up', str(caught.exception))
        self.assertEqual(self.snapshot(), snapshot)

    def test_failure_after_one_builder_or_final_notice_rolls_back_every_write(self):
        item = self.approved()
        snapshot = self.snapshot()
        original = self.store.save_submission
        calls = []

        def fail_second(body, _db=None):
            calls.append(body)
            if len(calls) == 2:
                raise RuntimeError('injected second builder failure')
            return original(body, _db=_db)

        with patch.object(self.store, 'save_submission', side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, 'second builder'):
                op.quote(self.store, self.quote_payload(item), self.admin)
        self.assertEqual(self.snapshot(), snapshot)
        with patch.object(op, '_notify', side_effect=RuntimeError('injected notification failure')):
            with self.assertRaisesRegex(RuntimeError, 'notification'):
                op.quote(self.store, self.quote_payload(item), self.admin)
        self.assertEqual(self.snapshot(), snapshot)

    def test_quoted_outcome_stays_approved_and_is_managed_in_chase_up(self):
        item = self.approved()
        quoted = op.quote(self.store, self.quote_payload(item), self.admin)['opportunity']
        quoted = op.save(self.store, {**quoted, 'due': '2000-01-01'}, self.creator)['opportunity']
        for decision in ('pending', 'rejected'):
            self.assert_denied(lambda: op.decide(self.store, {**quoted, 'decision': decision}, self.admin), 409)
        op.process_due(self.store, force=True)
        saved = op.save(self.store, {**quoted, 'remarks': 'Retain history after quoting'}, self.creator)['opportunity']
        self.assertEqual(saved['status'], 'approved')
        self.assertEqual(saved['submissionIds'], quoted['submissionIds'])

    def test_quoted_project_receives_no_obsolete_opportunity_deadline_reminders(self):
        with patch.object(op, '_today', return_value=date(2026, 10, 22)):
            item = self.approved(due='2026-10-25')
            quoted = op.quote(self.store, self.quote_payload(item), self.admin)['opportunity']
        with self.store.connect() as db:
            before = db.execute('SELECT COUNT(*) FROM opportunity_events').fetchone()[0]
        op.process_due(self.store, force=True, now=datetime(2026, 10, 24, tzinfo=timezone.utc))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunity_events').fetchone()[0], before)
            self.assertEqual(op._find(db, quoted['id'])['status'], 'approved')

    def legacy_expire(self, item, actor=None):
        with self.store.connect() as db:
            expired = {**item, 'status': 'expired', 'revision': item['revision'] + 1,
                       'updatedAt': tenders.timestamp(), 'expiredAt': tenders.timestamp()}
            op._write(db, expired)
            op._activity(self.store, db, actor or op.SYSTEM, 'Expired opportunity', expired, {'due': item['due']})
        return expired

    def clear_upgrade_marker(self):
        with self.store.connect() as db:
            db.execute('DELETE FROM settings WHERE id=?', (upgrade.MIGRATION_KEY,))

    def test_restore_only_clear_approval_then_system_expiry_preserves_history(self):
        good = self.legacy_expire(self.approved(project='Restore prior approval', due='2000-01-01'))
        rejected = self.approved(project='Latest decision is rejection', due='2000-01-01')
        rejected = op.decide(self.store, {**rejected, 'decision': 'rejected'}, self.admin)['opportunity']
        rejected = self.legacy_expire(rejected)
        user_expiry = self.legacy_expire(self.approved(project='Not a system expiry'), self.admin)
        unknown = self.create(project='No approval evidence', due='2000-01-01')
        deleted = self.legacy_expire(self.approved(project='Deleted prior approval'))
        op.delete(self.store, deleted, self.admin)
        retired = self.legacy_expire(self.approved(project='Retired prior approval'))
        with self.store.connect() as db:
            db.execute("INSERT INTO opportunity_reset_entries(kind,record_key,retired_at) VALUES('opportunity',?,?)",
                       (retired['id'], tenders.timestamp()))
            old_activity = [tuple(row) for row in db.execute('SELECT * FROM opportunity_activity ORDER BY id')]
        self.clear_upgrade_marker()
        result = upgrade.restore_approved_once(self.store)
        self.assertEqual(result, {'applied': True, 'restored': 1})
        with self.store.connect() as db:
            restored = op._find(db, good['id'])
            self.assertEqual(restored['status'], 'approved')
            self.assertEqual(restored['revision'], good['revision'] + 1)
            for key in ('decisionBy', 'decisionByName', 'decisionAt', 'decisionReason', 'createdBy'):
                self.assertEqual(restored[key], good[key])
            for untouched in (rejected, user_expiry, unknown, retired):
                row = db.execute('SELECT status FROM opportunities WHERE id=?', (untouched['id'],)).fetchone()
                self.assertEqual(row['status'], 'expired')
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM opportunity_activity ORDER BY id')][:len(old_activity)], old_activity)
            marker = json.loads(db.execute('SELECT body FROM settings WHERE id=?', (upgrade.MIGRATION_KEY,)).fetchone()[0])
            self.assertEqual(marker['restored'], 1)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        backup = self.store.path.parent / 'upgrade_backups' / marker['backupFile']
        with sqlite3.connect(backup) as db:
            self.assertEqual(db.execute('SELECT status FROM opportunities WHERE id=?', (good['id'],)).fetchone()[0], 'expired')
        snapshot = self.snapshot()
        self.assertEqual(upgrade.restore_approved_once(self.store), {'applied': False, 'restored': 0})
        self.assertEqual(self.snapshot(), snapshot)
        restarted = tenders.Store(self.store.path)
        self.assertEqual(op.detail(restarted, good['id'], self.admin)['opportunity']['status'], 'approved')

    def test_restore_backup_or_late_failure_keeps_original_rows_and_marker_absent(self):
        self.legacy_expire(self.approved(due='2000-01-01'))
        self.clear_upgrade_marker()
        snapshot = self.snapshot()
        with patch.object(upgrade, '_backup', side_effect=RuntimeError('backup failed')):
            with self.assertRaisesRegex(RuntimeError, 'backup failed'):
                upgrade.restore_approved_once(self.store)
        self.assertEqual(self.snapshot(), snapshot)
        with patch.object(op, '_notify', side_effect=RuntimeError('notice failed')):
            with self.assertRaisesRegex(RuntimeError, 'notice failed'):
                upgrade.restore_approved_once(self.store)
        self.assertEqual(self.snapshot(), snapshot)
        with self.store.connect() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM settings WHERE id=?', (upgrade.MIGRATION_KEY,)).fetchone())

    def test_restore_skips_a_pending_reset_cohort_and_preserves_reset_key(self):
        item = self.legacy_expire(self.approved())
        self.clear_upgrade_marker()
        with self.store.connect() as db:
            db.execute('DELETE FROM settings WHERE id=?', (RESET_KEY,))
        with patch.object(upgrade, '_backup', side_effect=AssertionError('No backup needed for skipped cohort')):
            result = upgrade.restore_approved_once(self.store)
        self.assertEqual(result['restored'], 0)
        with self.store.connect() as db:
            self.assertEqual(op._find(db, item['id'])['status'], 'expired')
            self.assertIsNone(db.execute('SELECT 1 FROM settings WHERE id=?', (RESET_KEY,)).fetchone())

    def test_store_startup_restores_approved_history_after_schema_and_reset(self):
        item = self.legacy_expire(self.approved(project='Restore during store startup', due='2000-01-01'))
        self.clear_upgrade_marker()
        restarted = tenders.Store(self.store.path)
        restored = op.detail(restarted, item['id'], self.admin)['opportunity']
        self.assertEqual(restored['status'], 'approved')
        self.assertEqual(restored['revision'], item['revision'] + 1)
        self.assertEqual(restored['decisionAt'], item['decisionAt'])
        with restarted.connect() as db:
            marker = json.loads(db.execute('SELECT body FROM settings WHERE id=?',
                                           (upgrade.MIGRATION_KEY,)).fetchone()[0])
            self.assertEqual(marker['restored'], 1)
            self.assertFalse(marker['pendingResetCohortSkipped'])

    def test_store_startup_retires_pending_reset_cohort_before_approval_correction(self):
        item = self.legacy_expire(self.approved(project='Retire before correction', due='2000-01-01'))
        self.clear_upgrade_marker()
        with self.store.connect() as db:
            db.execute('DELETE FROM settings WHERE id=?', (RESET_KEY,))
        with patch.object(upgrade, '_backup', side_effect=AssertionError('No approval correction needed')):
            restarted = tenders.Store(self.store.path)
        with restarted.connect() as db:
            self.assertIsNotNone(db.execute('SELECT 1 FROM settings WHERE id=?', (RESET_KEY,)).fetchone())
            self.assertIsNotNone(db.execute("SELECT 1 FROM opportunity_reset_entries WHERE kind='opportunity' AND record_key=?",
                                           (item['id'],)).fetchone())
            self.assertEqual(db.execute('SELECT status FROM opportunities WHERE id=?', (item['id'],)).fetchone()[0], 'expired')
            self.assertIsNone(db.execute("SELECT 1 FROM opportunity_activity WHERE opportunity_id=? AND action='Restored approved opportunity'",
                                        (item['id'],)).fetchone())
            marker = json.loads(db.execute('SELECT body FROM settings WHERE id=?',
                                           (upgrade.MIGRATION_KEY,)).fetchone()[0])
            self.assertEqual(marker['restored'], 0)


if __name__ == '__main__':
    unittest.main()
