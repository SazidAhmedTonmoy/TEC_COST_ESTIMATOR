import json,unittest
import test_http_v231 as helpers
from conest_app import tenders

class V34Tests(unittest.TestCase):
 request=helpers.HttpPatchTests.request
 def setUp(self):
  tenders._store=None;helpers.HttpPatchTests.setUp(self)
  with helpers.connect() as db:
   for name in ('TEC AU TEAM','TEC BD TEAM'):db.execute("INSERT OR IGNORE INTO teams(name,created_at,updated_at) VALUES(?,'2026-10-09','2026-10-09')",(name,))
 def tearDown(self):tenders._store=None;helpers.HttpPatchTests.tearDown(self)
 def test_cutoff_and_editable_team(self):
  self.assertEqual(tenders.default_submission_team('2026-07-19'),'TEC AU TEAM')
  self.assertEqual(tenders.default_submission_team('2026-07-20'),'TEC BD TEAM')
  self.assertEqual(tenders.default_submission_team(''),'')
  store=tenders.get_store();original=store.all_data()['submissions'][0]
  status,d=self.request('POST','/api/tenders/submissions',{**original,'due':'2026-07-20','submittedByTeam':'TEC AU TEAM'})
  self.assertEqual(status,200,d);self.assertEqual(d['submission']['submittedByTeam'],'TEC AU TEAM')
  updated=d['submission'];store.initialize()
  self.assertEqual(store.delta(updated['id'])['submission']['submittedByTeam'],'TEC AU TEAM')
  status,d=self.request('POST','/api/tenders/submissions',{**updated,'submittedByTeam':'not an existing team'})
  self.assertEqual(status,400)
 def test_legacy_backfill_is_once_and_revisions_guarded(self):
  store=tenders.get_store();s=store.all_data()['submissions'][0]
  with store.connect(write=True) as db:
   del s['submittedByTeam'];s['due']='2026-07-20'
   db.execute('UPDATE submissions SET body=? WHERE id=?',(json.dumps(s),s['id']))
   db.execute("DELETE FROM settings WHERE id='submission-teams-v34'")
  store.initialize();updated=store.delta(s['id'])['submission']
  self.assertEqual(updated['submittedByTeam'],'TEC BD TEAM');self.assertEqual(updated['revision'],s['revision']+1)
  status,d=self.request('POST','/api/tenders/submissions',s);self.assertEqual(status,409)
  store.initialize();self.assertEqual(store.delta(s['id'])['submission']['revision'],updated['revision'])
 def test_bootstrap_has_actual_team_options(self):
  with helpers.connect() as db:db.execute("INSERT INTO teams(name,created_at,updated_at) VALUES('Custom team','2026-10-09','2026-10-09')")
  status,data=self.request('GET','/api/tenders/bootstrap');self.assertEqual(status,200,data)
  self.assertIn('Custom team',data['data']['teams'])
  self.assertTrue(all('submittedByTeam' in s for s in data['data']['submissions']))
