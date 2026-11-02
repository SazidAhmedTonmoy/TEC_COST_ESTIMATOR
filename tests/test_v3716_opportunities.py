"""v3.7.16 opportunity date, document, region, and review regressions.

All database fixtures use temporary copies, never production data.
"""
import unittest
from unittest.mock import patch
from datetime import date

from conest_app import opportunities as op, tenders
from tests import test_opportunities as fixture


class V3716OpportunityTests(unittest.TestCase):
    setUp = fixture.OpportunityTests.setUp
    tearDown = fixture.OpportunityTests.tearDown
    make_user = staticmethod(fixture.OpportunityTests.make_user)
    create = fixture.OpportunityTests.create

    def test_create_cannot_save_deadline_before_added_date(self):
        with self.assertRaises(tenders.ValidationError) as captured:
            self.create(project='Invalid dates', addedDate='2026-11-20', due='2026-11-19')
        self.assertIn('Closing deadline', str(captured.exception))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunities').fetchone()[0], 0)
        same = self.create(project='Same day', addedDate='2099-01-08', due='2099-01-08')
        later = self.create(project='Later deadline', addedDate='2099-01-08', due='2099-02-09')
        self.assertEqual(same['due'], '2099-01-08')
        self.assertEqual(later['addedDate'], '2099-01-08')

    def test_edited_deadline_and_added_date_are_reconciled_on_server(self):
        item = self.create(project='Edit date', addedDate='2099-01-01', due='2099-03-04')
        with self.assertRaises(tenders.ValidationError):
            op.save(self.store, {'id':item['id'], 'revision':item['revision'], 'addedDate':'2099-04-01'},self.creator)
        self.assertEqual(op.detail(self.store,item['id'],self.creator)['opportunity']['due'],'2099-03-04')
        updated = op.save(self.store, {'id':item['id'], 'revision':item['revision'], 'addedDate':'2099-04-01', 'due':'2099-04-02'},self.creator)['opportunity']
        self.assertEqual((updated['addedDate'], updated['due']),('2099-04-01','2099-04-02'))

    def test_historical_invalid_date_pair_does_not_block_unrelated_edits(self):
        # Some historical workbook dates pre-date this validation; do not
        # change them or trap a user when editing unrelated descriptions.
        original = self.create(project='Legacy date')
        with self.store.connect(write=True) as db:
            current = op._find(db,original['id'])
            current['addedDate']='2099-05-01';current['due']='2099-03-04'
            op._write(db,current)
        unchanged_date = op.save(self.store, {'id':original['id'], 'revision':original['revision'], 'workingScope':'Corrected scope'},self.creator)['opportunity']
        self.assertEqual(unchanged_date['due'],'2099-03-04')
        with self.assertRaises(tenders.ValidationError):
            op.save(self.store, {'id':original['id'], 'revision':unchanged_date['revision'], 'due':'2099-04-01'},self.creator)

    def test_new_documents_flag_is_persistent_audited_and_defaults_no(self):
        yes = self.create(project='Docs yes', documentsAvailable=True)
        no = self.create(project='Docs no')
        self.assertTrue(yes['documentsAvailable'])
        self.assertFalse(no['documentsAvailable'])
        detail = op.detail(self.store,yes['id'],self.creator)
        self.assertTrue(detail['opportunity']['documentsAvailable'])
        created = next(a for a in detail['activity'] if a['action']=='Created opportunity')
        self.assertIs(created['details']['after']['documentsAvailable'],True)
        with self.store.connect() as db:
            self.assertTrue(db.execute('SELECT COUNT(*) FROM tender_notifications WHERE target_id=?',(yes['id'],)).fetchone()[0]>0)
        for bad in ('yes','true',1,None,{},[]):
            with self.subTest(bad=repr(bad)),self.assertRaises(tenders.ValidationError):
                self.create(project='Invalid documents', documentsAvailable=bad)
        # The generic edit endpoint cannot overwrite document availability.
        edited=op.save(self.store,{'id':yes['id'],'revision':yes['revision'], 'documentsAvailable':False,'remarks':'Notes only'},self.member)['opportunity']
        self.assertTrue(edited['documentsAvailable'])
        self.assertEqual(edited['remarks'],'Notes only')

    def test_approved_unlinked_can_move_to_review_and_is_audited(self):
        pending = self.create(project='Approved to review',due='2099-03-04')
        approved=op.decide(self.store, {'id':pending['id'],'revision':pending['revision'], 'decision':'approved'},self.admin)['opportunity']
        review=op.decide(self.store, {'id':approved['id'],'revision':approved['revision'], 'decision':'review','reason':'More details needed'},self.member)['opportunity']
        self.assertEqual(review['status'],'review')
        self.assertEqual(review['decisionReason'],'More details needed')
        detail=op.detail(self.store,review['id'],self.admin)
        self.assertEqual(detail['activity'][0]['action'],'Moved opportunity to In Review')
        self.assertEqual(detail['activity'][0]['details']['before'],'approved')
        self.assertTrue(any(n['opportunityId']==review['id'] for n in op.notifications(self.store,{'pageSize':100},self.admin)['items']))
        reapproved=op.decide(self.store,{'id':review['id'],'revision':review['revision'],'decision':'approved'},self.member)['opportunity']
        self.assertEqual(reapproved['status'],'approved')

    def test_quoted_and_overdue_approved_records_remain_protected(self):
        pending = self.create(project='Quoted cannot review')
        approved=op.decide(self.store,{'id':pending['id'],'revision':pending['revision'],'decision':'approved'},self.admin)['opportunity']
        quoted={**approved,'quoteStatus':'quoted'}
        with self.store.connect(write=True) as db:op._write(db,quoted)
        with self.assertRaises(tenders.ValidationError) as err:
            op.decide(self.store,{'id':approved['id'],'revision':approved['revision'],'decision':'review'},self.admin)
        self.assertEqual(err.exception.status,409)

        past = self.create(project='Past approved',due='2000-01-01')
        past = op.decide(self.store,{'id':past['id'],'revision':past['revision'],'decision':'approved'},self.admin)['opportunity']
        with self.assertRaises(tenders.ValidationError) as err:
            op.decide(self.store,{'id':past['id'],'revision':past['revision'],'decision':'review'},self.admin)
        self.assertEqual(err.exception.status,409)
        self.assertEqual(op.detail(self.store,past['id'],self.admin)['opportunity']['status'],'approved')


if __name__=='__main__':
    unittest.main()
