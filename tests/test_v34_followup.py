import json,unittest
import test_http_v231 as helpers
from conest_app import tenders

class FollowupTests(unittest.TestCase):
 request=helpers.HttpPatchTests.request
 def setUp(self):
  tenders._store=None;helpers.HttpPatchTests.setUp(self)
 def tearDown(self):
  tenders._store=None;helpers.HttpPatchTests.tearDown(self)
 def getdata(self):
  status,data=self.request('GET','/api/tenders/data');self.assertEqual(status,200,data);return data
 def test_team_rename_delete_and_no_fixed_options(self):
  status,t=self.request('POST','/api/teams',{'name':'Tender team','member_ids':[]});self.assertEqual(status,201,t);tid=t['team']['id']
  s=self.getdata()['submissions'][0]
  status,d=self.request('POST','/api/tenders/submissions',{**s,'submittedByTeam':'Tender team'});self.assertEqual(status,200,d)
  self.assertEqual(self.request('PATCH',f'/api/teams/{tid}',{'name':'Renamed'})[0],200)
  data=self.getdata();self.assertNotIn('Tender team',data['teams']);self.assertEqual(next(x for x in data['submissions'] if x['id']==s['id'])['submittedByTeam'],'Renamed')
  self.assertEqual(self.request('DELETE',f'/api/teams/{tid}',csrf=False)[0],403)
  self.assertEqual(self.request('DELETE',f'/api/teams/{tid}')[0],200)
  data=self.getdata();self.assertNotIn('Renamed',data['teams']);self.assertEqual(next(x for x in data['submissions'] if x['id']==s['id'])['submittedByTeam'],'')
 def test_shared_fields_and_stale_sibling(self):
  data=self.getdata();s=next(x for x in data['submissions'] if sum(y['project']==x['project'] for y in data['submissions'])>1)
  stale=next(x for x in data['submissions'] if x['project']==s['project'] and x['id']!=s['id'])
  status,d=self.request('POST','/api/tenders/submissions',{**s,'region':'vIc','due':'2027-02-12','month':'wrong','statusUpdated':'January 1900'});self.assertEqual(status,200,d)
  related=[d['submission'],*d['relatedSubmissions']]
  self.assertGreater(len(related),1)
  self.assertTrue(all(x['region']=='VIC' and x['due']=='2027-02-12' and x['month']=='Feb 2027' for x in related))
  self.assertEqual(self.request('POST','/api/tenders/submissions',stale)[0],409)
 def test_latest_chase_date_not_last_inserted_and_edit(self):
  s=self.getdata()['submissions'][0]
  for dt in ('2028-06-10','2027-02-01'):
   status,d=self.request('POST','/api/tenders/chases',{'submissionId':s['id'],'date':dt,'note':dt,'method':'Email'});self.assertEqual(status,200,d)
  self.assertEqual(d['submission']['statusUpdated'],'2028-06-10')
  c=next(c for c in d['chases'] if c['date']=='2028-06-10')
  status,d=self.request('POST','/api/tenders/chases/edit',{**c,'date':'2029-01-01'});self.assertEqual(status,200,d);self.assertEqual(d['submission']['statusUpdated'],'2029-01-01')
 def test_normalized_existing_data(self):
  data=self.getdata();groups={}
  for s in data['submissions']:
   self.assertEqual(s['region'],s['region'].upper());self.assertNotIn('1900',s['statusUpdated'])
   groups.setdefault(tenders.project_key(s['project']),set()).add((s['region'],s['due'],s['month']))
  self.assertTrue(all(len(v)==1 for v in groups.values()))

 def test_import_missing_values_and_project_updates(self):
  from io import BytesIO
  from openpyxl import Workbook
  from conest_app.tender_import import import_workbook,parse_workbook
  from conest_app.tender_export import export_workbook
  wb=Workbook();ws=wb.active;ws.title='Raw Data'
  ws.append(['Project','Builder','TEC status','Tender value','Region','Submission deadline','Pricing feedback','Status updated'])
  ws.append(['Shared import','One',None,None,'vIc','2027-04-02',None,'January 1900'])
  ws.append(['Shared import','Two',None,'Nil',None,None,None,'January 1900'])
  stream=BytesIO();wb.save(stream);blob=stream.getvalue()
  parsed=parse_workbook('test.xlsx',blob)
  self.assertEqual(parsed['records'][0]['pricing'],'Nil');self.assertIsNone(parsed['records'][0]['value'])
  self.assertNotIn('statusUpdated',parsed['records'][0])
  store=tenders.get_store();actor={'id':self.user_id,'name':'Test importer'}
  preview=import_workbook(store,'test.xlsx',blob,actor)
  import_workbook(store,'test.xlsx',blob,actor,preview['token'])
  rows=[s for s in store.all_data()['submissions'] if s['project']=='Shared import']
  self.assertEqual(len(rows),2);self.assertTrue(all(s['region']=='VIC' and s['due']=='2027-04-02' and s['month']=='Apr 2027' for s in rows))
  data={'submissions':[{**rows[0],'due':'2027-06-08'},rows[1]],'chases':[],'reminders':[]}
  blob=export_workbook(data,[s['id'] for s in rows]);preview=import_workbook(store,'test.xlsx',blob,actor)
  self.assertEqual(preview['counts']['updated'],2);self.assertEqual(preview['counts']['unchanged'],0)
  import_workbook(store,'test.xlsx',blob,actor,preview['token'])
  rows=[s for s in store.all_data()['submissions'] if s['project']=='Shared import']
  self.assertTrue(all(s['due']=='2027-06-08' and s['month']=='Jun 2027' for s in rows))

 def test_upgrade_existing_schema31_adds_team_directory(self):
  from conest_app import auto_upgrade
  from conest_app.database import database_path
  with helpers.connect() as db:
   before=[tuple(r) for r in db.execute('SELECT id,name FROM teams ORDER BY id')]
   db.execute('DROP TABLE tender_team_aliases')
   db.execute("DELETE FROM app_migrations WHERE name='v3.4-team-directory'")
  auto_upgrade._ready.pop(str(database_path().resolve()),None)
  with helpers.connect() as db:
   self.assertEqual([tuple(r) for r in db.execute('SELECT id,name FROM teams ORDER BY id')],before)
   self.assertIsNotNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='tender_team_aliases'").fetchone())
   self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())
