import unittest,json
from pathlib import Path
import test_http_v231 as helpers
from fixtures_v232 import seed
from conest_app.database import connect
from conest_app import projects

class ProjectJSONTests(unittest.TestCase):
 setUp=helpers.HttpPatchTests.setUp
 tearDown=helpers.HttpPatchTests.tearDown
 request=helpers.HttpPatchTests.request
 def test_round_trip_preserves_estimate_and_ignores_foreign_ids(self):
  with connect() as c:
   f=seed(c)
   c.execute('UPDATE project_lines SET exclude_hours_markup=1,notes=? WHERE id=?',('Driver confirmation',f['line_id']))
   c.execute('UPDATE project_line_components SET fixed_quantity=1 WHERE project_line_id=?',(f['second_line_id'],))
   before=projects.calculate_project(c,f['project_id'])
  status,data=self.request('GET',f'/api/projects/{f["project_id"]}/json');self.assertEqual(status,200,data)
  data['project']['owner_id']=f['viewer']['id'];data['project']['id']=f['project_id'];data['lines'][0]['catalog_item_id']=f['catalog_id']
  status,result=self.request('POST','/api/project-json/import',data);self.assertEqual(status,200,result)
  with connect() as c:
   after=projects.calculate_project(c,result['id']);self.assertNotEqual(after['project']['id'],f['project_id'])
   self.assertEqual(after['totals'],before['totals']);self.assertEqual(after['lines'][0]['notes'],'Driver confirmation')
   self.assertIsNone(after['lines'][0]['catalog_item_id']);self.assertNotEqual(after['project']['owner_id'],f['viewer']['id'])
   self.assertEqual(projects.calculate_project(c,f['project_id']),before)
 def test_example_bad_files_and_csrf(self):
  example=json.loads((Path(__file__).resolve().parents[1]/'assets/example_project.json').read_text())
  status,result=self.request('POST','/api/project-json/import',example,csrf=False);self.assertEqual(status,403)
  status,result=self.request('POST','/api/project-json/import',example);self.assertEqual(status,200,result)
  with connect() as c:count=c.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
  for bad in [{},dict(example,version=2),dict(example,lines=[{'name_snapshot':'Bad','quantity':-5}]),dict(example,lines=[{'name_snapshot':'Bad','components':[{'description':'bad','unit_material':float('nan')}]}])]:
   status,result=self.request('POST','/api/project-json/import',bad);self.assertEqual(status,400,result)
  with connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM projects').fetchone()[0],count)
