"""v3.7.17 read-only linked-project journey and explicit Estimator linking."""
import json
import unittest
from datetime import datetime, timedelta, timezone

from conest_app import opportunities as op, tenders
from conest_app.database import connect
from conest_app.opportunity_journey import estimator_choices, link_estimator
from tests import test_opportunities as fixture


class JourneyTests(unittest.TestCase):
    setUp = fixture.OpportunityTests.setUp
    tearDown = fixture.OpportunityTests.tearDown
    make_user = staticmethod(fixture.OpportunityTests.make_user)
    create = fixture.OpportunityTests.create

    def approve(self, item):
        return op.decide(self.store, {'id':item['id'],'revision':item['revision'],
                        'decision':'approved'}, self.admin)['opportunity']

    def test_unlinked_journey_does_not_invent_estimate_quote_or_chase(self):
        pending=self.create(project='Not yet quoted')
        journey=op.detail(self.store,pending['id'],self.admin)['journey']
        self.assertIsNone(journey['estimatorProject'])
        self.assertEqual(journey['quotation']['status'],'pending')
        self.assertEqual(journey['chaseUp']['updates'],0)
        self.assertEqual(journey['outcome']['label'],'Not recorded')
        self.assertEqual(journey['nextAction']['title'],'Make approval decision')

    def test_explicit_estimator_link_is_audited_revision_checked_and_can_unlink(self):
        pending=self.create(project='Estimate linkage')
        with connect() as db:
            stamp=tenders.timestamp()
            pid=db.execute('INSERT INTO projects(name,client,created_at,updated_at) VALUES(?,?,?,?)',
                           ('Different Estimator Title','',stamp,stamp)).lastrowid
        choices=estimator_choices(self.store,{'id':pending['id'],'q':'Different Estimator'},self.creator)
        self.assertEqual(choices['items'],[{'id':pid,'name':'Different Estimator Title'}])
        linked=link_estimator(self.store,{'id':pending['id'],'revision':pending['revision'],
                                          'estimatorProjectId':pid},self.creator)
        self.assertEqual(linked['journey']['estimatorProject']['name'],'Different Estimator Title')
        self.assertTrue(linked['journey']['estimatorProject']['available'])
        self.assertEqual(linked['opportunity']['estimatorProjectId'],pid)
        self.assertEqual(linked['activity'][0]['action'],'Linked Estimator project')
        with self.assertRaises(tenders.ValidationError):
            link_estimator(self.store,{'id':pending['id'],'revision':pending['revision'],
                                            'estimatorProjectId':None},self.creator)
        with self.assertRaises(tenders.ValidationError):
            link_estimator(self.store,{'id':pending['id'],'revision':linked['opportunity']['revision'],
                                            'estimatorProjectId':9999999},self.creator)
        with self.assertRaises(tenders.ValidationError):
            link_estimator(self.store,{'id':pending['id'],'revision':linked['opportunity']['revision'],
                                            'estimatorProjectId':True},self.creator)
        with self.assertRaises(tenders.ValidationError):
            link_estimator(self.store,{'id':pending['id'],'revision':linked['opportunity']['revision'],
                                            'estimatorProjectId':None},self.no_team)
        unlinked=link_estimator(self.store,{'id':pending['id'],'revision':linked['opportunity']['revision'],
                                             'estimatorProjectId':None},self.creator)
        self.assertIsNone(unlinked['journey']['estimatorProject'])
        self.assertEqual(unlinked['activity'][0]['action'],'Unlinked Estimator project')

    def test_builder_chases_reminders_and_final_tec_status_use_linked_submissions(self):
        original=self.approve(self.create(project='End to end'))
        data=op.quote(self.store,{'id':original['id'],'revision':original['revision'],
                                  'value':12345,'builders':['Builder One','Builder Two'],
                                  'note':'Quote notes'},self.admin)
        item=data['opportunity']
        self.assertEqual(data['journey']['quotation']['value'],12345)
        self.assertEqual(data['journey']['quotation']['submissionCount'],2)
        self.assertEqual(data['journey']['nextAction']['title'],'Schedule a follow-up')
        sid=item['submissionIds'][0]
        with self.store.connect(write=True) as db:
            when=(datetime.now(timezone.utc)+timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
            chase={'id':'chase-fixture','submissionId':sid,'date':'2026-10-30',
                   'note':'Builder requested pricing clarification','method':'Email','author':'Estimator'}
            reminder={'id':'rem-fixture','submissionId':sid,'due':when,
                      'note':'Call back','done':False}
            db.execute('INSERT INTO chases VALUES(?,?,?)',(chase['id'],sid,json.dumps(chase)))
            db.execute('INSERT INTO reminders VALUES(?,?,?)',(reminder['id'],sid,json.dumps(reminder)))
        journey=op.detail(self.store,item['id'],self.admin)['journey']
        self.assertEqual(journey['chaseUp']['updates'],1)
        self.assertEqual(journey['chaseUp']['latest']['note'],chase['note'])
        self.assertEqual(journey['nextAction']['title'],'Follow-up scheduled')
        with self.store.connect(write=True) as db:
            for record_id in item['submissionIds']:
                row=db.execute('SELECT body FROM submissions WHERE id=?',(record_id,)).fetchone()
                submission=json.loads(row[0]);submission['status']='Won'
                submission['builderStatus']='Unsuccessful'
                db.execute('UPDATE submissions SET body=? WHERE id=?',(json.dumps(submission),record_id))
        outcome=op.detail(self.store,item['id'],self.admin)['journey']['outcome']
        self.assertEqual(outcome['label'],'Won')
        self.assertTrue(outcome['completed'])
        with self.store.connect(write=True) as db:
            row=db.execute('SELECT body FROM submissions WHERE id=?',(sid,)).fetchone()
            submission=json.loads(row[0]);submission['status']='Open'
            db.execute('UPDATE submissions SET body=? WHERE id=?',(json.dumps(submission),sid))
        self.assertEqual(op.detail(self.store,item['id'],self.admin)['journey']['outcome']['label'],'Awaiting outcome')

    def test_moved_tender_link_is_not_read_from_previous_owner(self):
        a=self.create(project='Old opportunity')
        with self.store.connect(write=True) as db:
            item=op._find(db,a['id']);item.update(submissionIds=['sid-1'],status='approved',quoteStatus='quoted');op._write(db,item)
            db.execute('INSERT INTO submissions(id,body,revision) VALUES(?,?,0)',
                       ('sid-1',json.dumps({'id':'sid-1','project':'Transferred','opportunityId':'another','status':'Won'})))
        journey=op.detail(self.store,a['id'],self.admin)['journey']
        self.assertEqual(journey['quotation']['submissionCount'],0)
        self.assertTrue(journey['quotation']['missingSubmissions'])
        self.assertEqual(journey['outcome']['label'],'Not recorded')

if __name__=='__main__':unittest.main()
