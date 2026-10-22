"""Expired decisions and quotation boundaries without changing existing projects."""
from datetime import date
import unittest
from unittest.mock import patch

import test_opportunity_workflow_v357 as shared
from conest_app import opportunities as op


class OpportunityExpiredActionsTests(unittest.TestCase):
    setUp = shared.OpportunityWorkflowTests.setUp
    tearDown = shared.OpportunityWorkflowTests.tearDown
    make_user = staticmethod(shared.OpportunityWorkflowTests.make_user)
    create = shared.OpportunityWorkflowTests.create
    approved = shared.OpportunityWorkflowTests.approved
    assert_denied = shared.OpportunityWorkflowTests.assert_denied
    quote_payload = shared.OpportunityWorkflowTests.quote_payload
    snapshot = shared.OpportunityWorkflowTests.snapshot

    def test_expired_rejection_is_authorised_audited_and_not_a_quote_outcome(self):
        item = self.create(due='2000-01-01')
        before = self.snapshot()
        self.assert_denied(lambda: op.decide(self.store, {**item, 'decision': 'rejected'}, self.no_team))
        self.assertEqual(self.snapshot(), before)
        result = op.decide(self.store, {**item, 'decision': 'rejected'}, self.member)
        rejected = result['opportunity']
        self.assertEqual((rejected['status'], rejected['decisionReason']), ('rejected', ''))
        self.assertEqual(rejected['decisionBy'], self.member['id'])
        self.assertNotIn('notQuotedAt', rejected)
        self.assertNotIn('quoteStatus', result['activity'][0]['details'])
        notices = op.notifications(self.store, {'pageSize': 100}, self.creator)['items']
        self.assertTrue(any(row['kind'] == 'rejected' and row.get('opportunityId') == item['id'] for row in notices))
        with self.store.connect() as db:
            self.assertTrue(db.execute("SELECT 1 FROM tender_activity WHERE action='Rejected opportunity' AND actor_id=?",
                                       (self.member['id'],)).fetchone())

    def test_assigning_expired_approves_without_creating_quote_and_can_be_rejected(self):
        expired = self.create(due='2000-01-01')
        approved = op.update_authority(self.store, {**expired, 'assignedTeamIds': [self.team]},
                                       self.creator, 'assign')['opportunity']
        self.assertEqual(approved['status'], 'approved')
        before = self.snapshot()
        self.assert_denied(lambda: op.quote(self.store, self.quote_payload(approved), self.admin), 409)
        self.assertEqual(self.snapshot(), before)
        result = op.decide(self.store, {**approved, 'decision': 'rejected'}, self.admin)
        self.assertEqual(result['opportunity']['status'], 'rejected')
        self.assertFalse(result['opportunity'].get('quoteStatus'))
        self.assertNotIn('notQuotedBy', result['opportunity'])
        self.assertEqual(result['activity'][0]['details']['before'], 'approved')
        self.assertNotIn('quoteStatus', result['activity'][0]['details'])

    def test_quote_accepts_due_today_or_blank_but_rejects_yesterday(self):
        with patch.object(op, '_today', return_value=date(2026, 10, 22)):
            for due in ('2026-10-22', ''):
                item = self.approved(project='Current or blank ' + due, due=due)
                self.assertTrue(op.quote(self.store, self.quote_payload(item), self.admin)['quoted'])
            past = self.approved(project='Yesterday', due='2026-10-21', region='VIC')
            before = self.snapshot()
            self.assert_denied(lambda: op.quote(self.store, self.quote_payload(past), self.admin), 409)
            self.assertEqual(self.snapshot(), before)

    def test_saved_quote_retry_remains_idempotent_after_deadline(self):
        with patch.object(op, '_today', return_value=date(2026, 10, 22)):
            item = self.approved(due='2026-10-22')
            payload = self.quote_payload(item)
            first = op.quote(self.store, payload, self.admin)
        before = self.snapshot()
        with patch.object(op, '_today', return_value=date(2026, 10, 23)):
            replay = op.quote(self.store, payload, self.admin)
        self.assertTrue(replay['alreadyQuoted'])
        self.assertEqual(first['submissionIds'], replay['submissionIds'])
        self.assertEqual(self.snapshot(), before)

    def test_linked_legacy_submissions_cannot_be_rejected_or_quoted_again(self):
        item = self.approved()
        linked = op.quote(self.store, self.quote_payload(item), self.admin)['opportunity']
        # A legacy record may retain its links while lacking the newer flag.
        with self.store.connect() as db:
            linked.pop('quoteStatus')
            op._write(db, linked)
        before = self.snapshot()
        self.assert_denied(lambda: op.decide(self.store, {**linked, 'decision': 'rejected'}, self.admin), 409)
        self.assert_denied(lambda: op.quote(self.store, self.quote_payload(linked), self.admin), 409)
        self.assertEqual(self.snapshot(), before)

    def test_active_approved_not_quoted_still_records_quote_outcome(self):
        item = self.approved()
        rejected = op.decide(self.store, {**item, 'decision': 'rejected'}, self.member)
        self.assertEqual(rejected['opportunity']['quoteStatus'], 'not_quoted')
        self.assertEqual(rejected['opportunity']['notQuotedBy'], self.member['id'])
        self.assertEqual(rejected['activity'][0]['details']['quoteStatus'], 'not_quoted')


if __name__ == '__main__':
    unittest.main()
