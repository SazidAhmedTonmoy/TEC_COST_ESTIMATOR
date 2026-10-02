import unittest
import test_http_v231 as helpers
from fixtures_v232 import seed
from conest_app.database import connect
from conest_app import projects,workspace,catalog

class QualityOfLifeTests(unittest.TestCase):
 setUp=helpers.HttpPatchTests.setUp
 tearDown=helpers.HttpPatchTests.tearDown
 request=helpers.HttpPatchTests.request
 def test_rename_remarks_and_estimate_only_component_removal(self):
  with connect() as c:
   f=seed(c);pid=f['project_id'];iid=f['catalog_id'];lid=f['line_id']
   original=catalog.get_catalog_item(c,iid);before=projects.calculate_project(c,pid);line=before['lines'][0];component=line['components'][0]
  status,result=self.request('PATCH',f'/api/projects/{pid}/workflow',{'name':'Updated project title','expected_revision':before['project']['revision']})
  self.assertEqual(status,200,result)
  status,result=self.request('PATCH',f'/api/projects/{pid}/lines/{lid}',{'notes':'Confirm DALI driver with supplier','expected_revision':line['revision']})
  self.assertEqual(status,200,result);line=next(x for x in result['lines'] if x['id']==lid)
  self.assertEqual(line['notes'],'Confirm DALI driver with supplier')
  url=f'/api/projects/{pid}/lines/{lid}/components/{component["id"]}/remove'
  status,result=self.request('POST',url,{'expected_revision':line['revision']},csrf=False);self.assertEqual(status,403)
  status,result=self.request('POST',url,{'expected_revision':line['revision']});self.assertEqual(status,201,result)
  changed=next(x for x in result['lines'] if x['id']==lid)
  self.assertEqual(len(changed['components']),len(line['components'])-1)
  self.assertAlmostEqual(changed['total_material'],line['total_material']-component['total_material'])
  self.assertEqual(changed['notes'],line['notes'])
  status,_=self.request('POST',url,{'expected_revision':line['revision']});self.assertEqual(status,409)
  with connect() as c:
   self.assertEqual(catalog.get_catalog_item(c,iid),original)
   self.assertEqual(workspace.get_project(c,pid)['name'],'Updated project title')
   self.assertEqual(projects.calculate_project(c,pid)['lines'][1],before['lines'][1])
   with self.assertRaises(Exception):workspace.update_workflow(c,pid,{'name':'Not permitted'},f['editor'])
 def test_search_order_before_pagination_and_usage_without_query(self):
  with connect() as c:
   f=seed(c);pid=f['project_id'];items=[]
   for i in range(4):
    item=catalog.create_manual_catalog_item(c,{'name':f'Isolator option {i}','importance_rating':5-i,'components':[{'description':f'Part {i}','unit_material':i+1}]});items.append(item['id'])
   projects.add_catalog_line(c,pid,items[2],1)
   self.assertEqual(catalog.get_catalog_item(c,items[2])['usage_count'],1)
   projects.add_catalog_line(c,pid,items[3],1)
   c.execute("UPDATE project_lines SET created_at='2026-09-30T00:00:00' WHERE catalog_item_id=?",(items[2],))
   c.execute("UPDATE project_lines SET created_at='2026-10-01T00:00:00' WHERE catalog_item_id=?",(items[3],))
   c.execute('UPDATE catalog_items SET usage_count=10 WHERE id=?',(items[0],))
   self.assertEqual([x['id'] for x in catalog.search_catalog(c,'isolator',limit=2)],[items[0],items[3]])
   self.assertEqual([x['id'] for x in catalog.search_catalog(c,'ISOLATOR',limit=2,offset=2)],[items[2],items[1]])
