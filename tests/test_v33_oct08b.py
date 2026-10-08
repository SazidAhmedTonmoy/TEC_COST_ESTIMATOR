import unittest
from datetime import date
import test_http_v231 as helpers
from fixtures_v232 import seed
from conest_app import tenders,workspace,projects,productivity
from conest_app.performance import contribution_report

class FollowupTests(unittest.TestCase):
 request=helpers.HttpPatchTests.request
 def setUp(self):tenders._store=None;helpers.HttpPatchTests.setUp(self)
 def tearDown(self):tenders._store=None;helpers.HttpPatchTests.tearDown(self)
 def test_import_credit_is_two_documents_not_submission_work(self):
  store=tenders.get_store()
  with helpers.connect() as db:
   uid=db.execute("SELECT id FROM users WHERE username='Tonmoy'").fetchone()[0]
   r=contribution_report(db,uid)
   self.assertEqual(r['tenders']['submissions'],0)
   self.assertEqual(next(x['count'] for x in r['uploads']['byType'] if x['kind']=='tender Excel'),2)
   self.assertEqual(r['historical']['importedFiles'],2)
   filtered=contribution_report(db,uid,'2026-01-01','2026-12-31')
   self.assertFalse(any(x['kind']=='tender Excel' for x in filtered['uploads']['byType']))
  with store.connect(write=True) as db:store.activity(db,uid,'Tonmoy','Imported Excel',details={'added':1})
  with helpers.connect() as db:
   r=contribution_report(db,uid);self.assertEqual(r['tenders']['submissions'],0)
   self.assertEqual(next(x['count'] for x in r['uploads']['byType'] if x['kind']=='tender Excel'),3)
 def test_closed_preserves_estimate_and_removes_reminders(self):
  with helpers.connect() as db:
   f=seed(db);pid=f['project_id'];before=projects.calculate_project(db,pid)['totals']
   workspace.update_workflow(db,pid,{'status':'in_review','review_deadline':date.today().isoformat()},f['owner'])
   p=workspace.update_workflow(db,pid,{'status':'closed'},f['owner'])
   self.assertEqual(p['status'],'closed');self.assertIsNone(p['review_deadline'])
   self.assertEqual(productivity.reminders(db,f['owner']),[])
   self.assertEqual(projects.calculate_project(db,pid)['totals'],before)
 def test_clear_chat_preserves_memory_and_latest_tenders(self):
  self.request('POST','/api/assistant/memory',{'note':'Keep this'})
  status,r=self.request('POST','/api/assistant/chat',{'question':'tell me about last 5 tenders','scope':'auto'})
  self.assertEqual(status,200,r);self.assertIn('Showing up to 5.',r['answer']);self.assertNotIn('0 matching',r['answer'])
  status,r=self.request('POST','/api/assistant/memory',{'clearConversation':True})
  self.assertEqual(r['note'],'Keep this');self.assertEqual(r['messages'],[])
