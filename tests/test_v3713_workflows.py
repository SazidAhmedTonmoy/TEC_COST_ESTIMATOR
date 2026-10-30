"""v3.7.13 review state, grouped KPI counts, quotation filters and deadlines."""
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from conest_app import opportunities as op, tenders
from tests import test_opportunities as fixture


class Workflow3713Tests(unittest.TestCase):
    setUp = fixture.OpportunityTests.setUp
    tearDown = fixture.OpportunityTests.tearDown
    make_user = staticmethod(fixture.OpportunityTests.make_user)
    create = fixture.OpportunityTests.create

    def decide(self, item, decision, who=None):
        return op.decide(self.store, {'id':item['id'], 'revision':item['revision'],
                                       'decision':decision, 'reason':''}, who or self.admin)['opportunity']

    def test_in_review_can_be_approved_rejected_or_expired(self):
        pending = self.create(project='Review project', due='2099-03-04')
        review = self.decide(pending, 'review')
        self.assertEqual(review['status'], 'review')
        self.assertEqual(self.decide(review, 'approved')['status'], 'approved')
        rejected = self.decide(self.decide(self.create(project='Rejected review'), 'review'), 'rejected')
        self.assertEqual(rejected['status'], 'rejected')
        expiring = self.decide(self.create(project='Expires in review',due='2099-03-04'), 'review')
        # Existing status is review; a future simulated day triggers expiry.
        op.process_due(self.store, force=True, now=datetime(2099,3,6,12,tzinfo=timezone.utc))
        self.assertEqual(op.detail(self.store,expiring['id'],self.admin)['opportunity']['status'],'expired')

    def test_closed_combined_counts_and_approved_quote_counts(self):
        approval = self.decide(self.create(project='Needs quote'),'approved')
        quoted = self.decide(self.create(project='Already quoted'),'approved')
        quoted['quoteStatus']='quoted'
        with self.store.connect() as db:op._write(db,quoted)
        self.decide(self.create(project='Rejected project'), 'rejected')
        self.create(project='Expired project',due='2000-01-01')
        result=op.list_opportunities(self.store,{'sort':'due_desc'},self.admin)
        self.assertEqual(result['quoteCounts'],{'quoted':1,'needsQuote':1})
        self.assertEqual(result['counts']['closed'],2)
        self.assertEqual(len(op.list_opportunities(self.store,{'status':'closed'},self.admin)['items']),2)
        self.assertEqual([item['project'] for item in op.list_opportunities(
            self.store,{'status':'approved','quoteFilter':'quoted'},self.admin)['items']],['Already quoted'])
        self.assertEqual([item['project'] for item in op.list_opportunities(
            self.store,{'status':'approved','quoteFilter':'needs_quote'},self.admin)['items']],['Needs quote'])

    def test_approved_month_calendar_uses_due_month_and_excludes_other_statuses(self):
        a=self.decide(self.create(project='Due October',due='2026-10-29'),'approved')
        self.decide(self.create(project='Still review',due='2026-10-30'),'review')
        self.decide(self.create(project='Due November',due='2026-11-02'),'approved')
        calendar=op.approved_calendar(self.store,{'month':'2026-10'},self.admin)
        self.assertEqual([item['project'] for item in calendar['items']], ['Due October'])
        self.assertEqual(calendar['quoted'],0)
        with self.assertRaises(tenders.ValidationError):
            op.approved_calendar(self.store,{'month':'2026-13'},self.admin)

if __name__=='__main__':unittest.main()
