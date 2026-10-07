"""Authorship, conflict protection, historical attribution and admin-only reporting."""
import json
import tempfile
import unittest
from pathlib import Path
from conest_app import tenders
from conest_app.tender_import import import_workbook
from conest_app.tender_export import export_workbook
import test_http_v231 as helpers

class V33Tests(unittest.TestCase):
    request=helpers.HttpPatchTests.request
    def setUp(self):
        tenders._store=None
        helpers.HttpPatchTests.setUp(self)
    def tearDown(self):
        tenders._store=None
        helpers.HttpPatchTests.tearDown(self)
    def test_edit_chase_authorship_conflict_and_metrics(self):
        store=tenders.get_store();chase=store.all_data()['chases'][0]
        self.assertEqual(chase['author'],'Yunus')
        body={**chase,'note':'Updated from the website','revision':0,'author':'Forged author','_actor_id':999}
        self.assertEqual(self.request('POST','/api/tenders/chases/edit',body,csrf=False)[0],403)
        status,data=self.request('POST','/api/tenders/chases/edit',body)
        self.assertEqual(status,200,data)
        changed=next(c for c in data['chases'] if c['id']==chase['id'])
        self.assertEqual(changed['author'],'Yunus');self.assertEqual(changed['updatedBy'],self.user_id)
        self.assertNotEqual(changed['updatedByName'],'Forged author');self.assertNotIn('edits',changed)
        self.assertEqual(self.request('POST','/api/tenders/chases/edit',body)[0],409)
        with store.connect() as db:
            saved=json.loads(db.execute('SELECT body FROM chases WHERE id=?',(chase['id'],)).fetchone()[0])
            self.assertEqual(saved['edits'][0]['note'],chase['note'])
        status,report=self.request('GET',f'/api/users/{self.user_id}/performance')
        self.assertEqual(status,200,report)
        self.assertEqual(report['tenders']['total'],1);self.assertEqual(report['tenders']['submissions'],1)
        self.assertEqual(report['recent'][0]['action'],'Edited chase-up')
        self.assertEqual(self.request('GET',f'/api/users/{self.user_id}/performance?since=bad')[0],400)
        with helpers.connect() as db:db.execute("UPDATE users SET role='user' WHERE id=?",(self.user_id,))
        self.assertEqual(self.request('GET',f'/api/users/{self.user_id}/performance')[0],403)
    def test_created_and_imported_are_separate_and_idempotent(self):
        status,result=self.request('POST','/api/tenders/submissions',{'project':'New web tender','builder':'Builder','status':'Open'})
        self.assertEqual(status,200,result);created=result['submission']
        self.assertEqual(created['createdBy'],self.user_id);self.assertTrue(created['createdByName']);self.assertTrue(created['createdAt'])
        store=tenders.get_store()
        old=store.all_data()['submissions'][0]
        self.assertEqual(old['importedByName'],'Tonmoy')
        new={**old,'id':'new-import','project':'New imported project'}
        blob=export_workbook({'submissions':[new],'chases':[],'reminders':[]},['new-import'])
        actor={'id':self.user_id,'name':'Future importer'}
        preview=import_workbook(store,'new.xlsx',blob,actor)
        import_workbook(store,'new.xlsx',blob,actor,preview['token'])
        new=store.delta('new-import')['submission'];self.assertEqual(new['importedByName'],'Future importer')
        again=import_workbook(store,'new.xlsx',blob,actor);self.assertEqual(again['counts']['unchanged'],1)
        import_workbook(store,'new.xlsx',blob,actor,again['token'])
        reloaded=tenders.Store(store.path);self.assertEqual(reloaded.delta('new-import')['submission']['importedByName'],'Future importer')
        status,report=self.request('GET',f'/api/users/{self.user_id}/performance')
        self.assertEqual(report['tenders']['rowsAdded'],1)
        self.assertEqual(report['tenders']['total'],2)
    def test_legacy_migration_preserves_web_entries(self):
        store=tenders.get_store();sid=store.all_data()['submissions'][0]['id']
        store.add_chase({'submissionId':sid,'note':'Existing website note','date':'2026-10-01','author':'Other user','_actor_id':12})
        with store.connect(write=True) as db:
            db.execute("DELETE FROM settings WHERE id='attribution-v33'")
            c=json.loads(db.execute('SELECT body FROM chases LIMIT 1').fetchone()[0]);c['author']='Workbook';c.pop('legacyChase',None)
            db.execute('UPDATE chases SET body=? WHERE id=?',(json.dumps(c),c['id']))
        migrated=tenders.Store(store.path)
        self.assertTrue(store.path.with_suffix('.pre-v33.db').exists())
        entries=migrated.all_data()['chases']
        self.assertEqual(next(x for x in entries if x['id']==c['id'])['author'],'Yunus')
        self.assertEqual(next(x for x in entries if x['note']=='Existing website note')['author'],'Other user')
