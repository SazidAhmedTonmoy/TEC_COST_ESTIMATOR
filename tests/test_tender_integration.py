"""Shared login, CSRF, deletion, migration and compact tender writes."""
import tempfile
import unittest
import sqlite3
from pathlib import Path
from conest_app import tenders
import test_http_v231 as http_helpers

class TenderIntegrationTests(unittest.TestCase):
    request=http_helpers.HttpPatchTests.request
    def setUp(self):
        tenders._store=None
        http_helpers.HttpPatchTests.setUp(self)
    def tearDown(self):
        tenders._store=None
        http_helpers.HttpPatchTests.tearDown(self)
    def test_tender_shared_session_and_compact_changes(self):
        status,data=self.request('GET','/api/tenders/data')
        self.assertEqual(status,200,data)
        self.assertEqual(len(data['submissions']),291)
        self.assertEqual(len(data['chases']),332)
        before=len(data['submissions'])
        body={'project':'Integration check','builder':'Test Builder','value':100,'status':'Open','builderStatus':'Awarded','pricing':'Competitive'}
        status,result=self.request('POST','/api/tenders/submissions',body,csrf=False)
        self.assertEqual(status,403)
        status,result=self.request('POST','/api/tenders/submissions',body)
        self.assertEqual(status,200,result)
        self.assertNotIn('submissions',result)
        item=result['submission'];sid=item['id']
        self.assertEqual(item['createdBy'],self.user_id)
        status,chase=self.request('POST','/api/tenders/chases',{'submissionId':sid,'note':'Check price','date':'2026-09-24','author':'Forged author','nextDue':'2026-09-26T09:00'})
        self.assertEqual(status,200,chase)
        self.assertNotEqual(chase['chases'][0]['author'],'Forged author')
        self.assertEqual(len(chase['reminders']),1)
        status,res=self.request('DELETE','/api/tenders/submissions',{'id':sid,'revision':item['revision']})
        self.assertEqual(status,409)
        status,res=self.request('DELETE','/api/tenders/submissions',{'id':sid,'revision':chase['submission']['revision']})
        self.assertEqual(status,200,res);self.assertIsNone(res['submission']);self.assertEqual(res['chases'],[])
        status,data=self.request('GET','/api/tenders/data');self.assertEqual(len(data['submissions']),before)
        cookie=self.cookie;self.cookie=''
        status,data=self.request('GET','/api/tenders/data');self.assertEqual(status,401)
        self.cookie=cookie
    def test_tender_delete_permissions_and_sqlite_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            old=Path(tmp)/'tec_tenders.sqlite3';new=old.with_suffix('.db')
            store=tenders.Store(old)
            s=store.all_data()['submissions'][0]
            with self.assertRaises(tenders.ValidationError) as caught:store.delete_submission({'id':s['id'],'revision':s['revision']},{'id':9999,'role':'user'})
            self.assertEqual(caught.exception.status,403)
            converted=tenders.Store(new)
            self.assertTrue(old.exists());self.assertTrue(new.exists())
            self.assertEqual(store.all_data()['submissions'],converted.all_data()['submissions'])
            with sqlite3.connect(new) as db:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
