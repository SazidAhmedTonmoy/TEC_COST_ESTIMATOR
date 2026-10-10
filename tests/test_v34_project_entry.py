import unittest,json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import test_http_v231 as helpers
from conest_app import tenders,backups

class ProjectEntryTests(unittest.TestCase):
 request=helpers.HttpPatchTests.request
 def setUp(self):
  tenders._store=None;helpers.HttpPatchTests.setUp(self)
 def tearDown(self):
  tenders._store=None;helpers.HttpPatchTests.tearDown(self)
 def draft(self):
  return dict(project='Multi-builder entry',quoteNo='Q-007/A',builders=['New Builder A','New Builder B'],value=123456,status='Open',builderStatus='In Progress',pricing='Nil',due='2027-06-01',region='vic',contact='Jane',email='jane@example.com',submittedByTeam='')
 def test_batch_shared_values_and_separate_chases(self):
  status,d=self.request('POST','/api/tenders/submissions/batch',self.draft());self.assertEqual(status,200,d)
  a=d['submission'];b=d['relatedSubmissions'][0]
  self.assertEqual(a['quoteNo'],b['quoteNo']);self.assertEqual(a['contact'],b['contact'])
  status,d=self.request('POST','/api/tenders/chases',{'submissionId':a['id'],'date':'2027-01-01','note':'Called A','nextDue':'2027-01-08T09:00'})
  self.assertEqual(status,200,d);self.assertEqual(len(d['chases']),1);self.assertEqual(d['reminders'],[])
  status,t=self.request('POST','/api/teams',{'name':'Shared team','member_ids':[]});self.assertEqual(status,201,t)
  status,d=self.request('POST','/api/tenders/submissions',{**d['submission'],'value':9876,'quoteNo':'Q-008','submittedByTeam':'Shared team','contact':'Only A'})
  self.assertEqual(status,200,d);b=d['relatedSubmissions'][0]
  self.assertEqual((b['value'],b['quoteNo'],b['submittedByTeam']),(9876,'Q-008','Shared team'));self.assertEqual(b['contact'],'Jane')
  self.assertEqual(tenders.get_store().delta(b['id'])['chases'],[])
 def test_batch_duplicate_is_atomic_and_builder_canonicalized(self):
  draft=self.draft();draft['builders']=['Acme Pty Ltd','ACME PTY. LTD']
  self.assertEqual(self.request('POST','/api/tenders/submissions/batch',draft)[0],400)
  self.assertFalse(any(s['project']==draft['project'] for s in tenders.get_store().all_data()['submissions']))
  draft['builders']=['Acme Pty Ltd'];self.assertEqual(self.request('POST','/api/tenders/submissions/batch',draft)[0],200)
  draft['builders']=['Fresh Builder','ACME PTY. LTD']
  self.assertEqual(self.request('POST','/api/tenders/submissions/batch',draft)[0],409)
  self.assertFalse(any(s['builder']=='Fresh Builder' for s in tenders.get_store().all_data()['submissions']))
  draft.update(project='Other project',builders=['ACME PTY. LTD'])
  status,d=self.request('POST','/api/tenders/submissions/batch',draft);self.assertEqual(status,200,d);self.assertEqual(d['submission']['builder'],'Acme Pty Ltd')
 def test_both_backups_schedule_and_download(self):
  tenders.get_store()
  self.assertEqual(backups.daily_backup(datetime(2026,10,10,0,9)),[])
  result=backups.daily_backup(datetime(2026,10,10,0,10));self.assertEqual({b['database'] for b in result},{'catalog','tenders'})
  self.assertEqual(backups.daily_backup(datetime(2026,10,10,12,0)),[])
  backups.create_backup_set();self.assertEqual(backups.daily_backup(datetime(2026,10,10,13,0)),[])
  self.assertEqual(len(backups.daily_backup(datetime(2026,10,11,0,10))),2)
  status,d=self.request('GET','/api/backups');self.assertEqual(status,200,d);self.assertEqual({b['database'] for b in d['backups']},{'catalog','tenders'})
  for b in d['backups']:
   status,body=self.request('GET',f"/api/backups/{b['name']}/download");self.assertEqual(status,200);self.assertTrue(body.startswith(b'SQLite format 3'))
 def test_failed_second_backup_does_not_mark_day_complete(self):
  tenders.get_store()
  with patch('conest_app.backups.create_tender_backup',side_effect=OSError('disk full')):
   with self.assertRaises(OSError):backups.daily_backup(datetime(2026,10,10,0,10))
  self.assertFalse((backups.folder()/'.daily-complete.json').exists())
  self.assertEqual(len(backups.daily_backup(datetime(2026,10,10,0,11))),2)
 def test_cron_preserves_other_jobs_and_is_idempotent(self):
  from tools.install_backup_cron import cron_line,updated_crontab
  line,tag=cron_line(Path('/tmp/app with spaces'),'/usr/bin/python3')
  self.assertTrue(line.startswith('10 0 * * * '));self.assertIn('--runtime-config',line)
  original='5 5 * * * echo keep\n'
  saved=updated_crontab(original,line,tag)
  self.assertEqual(updated_crontab(saved,line,tag),saved);self.assertTrue(saved.startswith(original))

 def test_legacy_tender_snapshot_remains_visible(self):
  tenders.get_store();record=backups.create_tender_backup()
  original=backups.backup_path(record['name']);legacy=original.with_name('20261009.db');original.rename(legacy)
  records=backups.list_all_backups();entry=next(b for b in records if b['database']=='tenders')
  self.assertEqual(backups.backup_path(entry['name']),legacy)
