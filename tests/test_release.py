import os,sqlite3,tempfile,time,unittest
from pathlib import Path
from datetime import date,timedelta
from unittest.mock import patch
from conest_app.database import initialize,connect
from conest_app.projects import create_project
from conest_app import backups

class ReleaseTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.env=patch.dict(os.environ,{'CONEST_DB_PATH':str(self.root/'main.db'),'CONEST_LIGHT_PRICES_DB':str(self.root/'unused.db')});self.env.start();initialize()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def test_new_project_date(self):
  with connect() as c:
   with self.assertRaises(ValueError):create_project(c,{'name':'Past','submission_deadline':str(date.today()-timedelta(days=1))})
   self.assertEqual(c.execute("SELECT COUNT(*) FROM projects WHERE name='Past'").fetchone()[0],0)
   for day in (date.today(),date.today()+timedelta(days=1)):
    self.assertIsNotNone(create_project(c,{'name':'Allowed','submission_deadline':str(day)})['project']['id'])
 def test_latest_two_backups_metadata_and_restore(self):
  first=backups.create_backup();second=backups.create_backup();third=backups.create_backup()
  self.assertEqual({r['name'] for r in backups.list_backups()},{second['name'],third['name']})
  self.assertFalse((backups.folder()/first['name']).exists());self.assertFalse((backups.folder()/first['name']).with_suffix('.json').exists())
  backups.restore_backup(second['name']) # It may be pruned while the restoration is in progress.
  self.assertEqual(len(backups.list_backups()),2)
  with connect() as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
 def test_predeploy_names_sort_by_time_and_invalid_paths(self):
  for i,name in enumerate(['predeploy_20260915_000000.db','20260915T000000Z-daily-12345678.db','predeploy_20260915_000001.db']):
   p=backups.folder()/name;p.write_bytes(b'test');os.utime(p,(100+i,100+i))
  result=backups.list_backups();self.assertEqual(len(result),2);self.assertEqual(result[0]['name'],'predeploy_20260915_000001.db')
  self.assertTrue(backups.backup_path(result[0]['name']).exists())
  with self.assertRaises(ValueError):backups.backup_path('../main.db')
