"""Optional shared stars: save/clear, search visibility, validation and migration."""
import unittest
import test_http_v231 as helpers
from conest_app.database import connect,database_path
from conest_app import projects,auto_upgrade
from conest_app.catalog import create_manual_catalog_item,search_catalog,get_catalog_item
from conest_app.release_v31_rating import set_rating
from fixtures_v232 import seed

class CatalogRatingTests(unittest.TestCase):
 setUp=helpers.HttpPatchTests.setUp
 tearDown=helpers.HttpPatchTests.tearDown
 request=helpers.HttpPatchTests.request
 def test_saved_stars_visible_in_search_details_and_no_price_change(self):
  with connect() as c:
   f=seed(c);pid=f['project_id'];iid=f['catalog_id'];before=projects.calculate_project(c,pid)
  for value in [1,5,3,0]:
   status,result=self.request('POST',f'/api/catalog/{iid}/rating',{'importance_rating':value})
   self.assertEqual(status,200,result);self.assertEqual(result['importance_rating'],value)
   status,detail=self.request('GET',f'/api/catalog/{iid}')
   self.assertEqual(detail['item']['importance_rating'],value)
   status,found=self.request('GET','/api/catalog/search?q=Batten')
   self.assertEqual(next(x for x in found['results'] if x['id']==iid)['importance_rating'],value)
  with connect() as c:self.assertEqual(projects.calculate_project(c,pid),before)
  for value in [-1,6,True,2.5,'5',None]:
   status,_=self.request('POST',f'/api/catalog/{iid}/rating',{'importance_rating':value});self.assertEqual(status,400)
  status,_=self.request('POST',f'/api/catalog/{iid}/rating',{'importance_rating':5},csrf=False);self.assertEqual(status,403)
  with connect() as c:self.assertEqual(get_catalog_item(c,iid)['importance_rating'],0)
 def test_optional_default_and_rated_duplicate_not_hidden(self):
  with connect() as c:
   data={'name':'Test rating item','components':[{'description':'Allowance','quantity_per_unit':1,'unit_material':12}]}
   first=create_manual_catalog_item(c,{**data,'importance_rating':4})
   second=create_manual_catalog_item(c,data)
   self.assertEqual(second['importance_rating'],0)
   c.execute('UPDATE catalog_items SET content_key=? WHERE id=?',(first['content_key'],second['id']))
   results=search_catalog(c,'Test rating item')
   self.assertEqual(len(results),1);self.assertEqual(results[0]['importance_rating'],4)
   self.assertEqual(results[0]['id'],first['id'])
 def test_schema28_upgrade_preserves_estimates_and_defaults_unstarred(self):
  with connect() as c:
   f=seed(c);before=projects.calculate_project(c,f['project_id'])['totals']
   c.execute('ALTER TABLE catalog_items DROP COLUMN importance_rating')
   c.execute('UPDATE schema_version SET version=28')
   key=c.execute('PRAGMA table_info(app_migrations)').fetchone()[1]
   c.execute(f'DELETE FROM app_migrations WHERE "{key}"=?',('v3.1-catalog-rating',))
  auto_upgrade._ready.pop(str(database_path()),None)
  with connect() as c:
   self.assertEqual(c.execute('SELECT version FROM schema_version').fetchone()[0],31)
   self.assertEqual(get_catalog_item(c,f['catalog_id'])['importance_rating'],0)
   self.assertEqual(projects.calculate_project(c,f['project_id'])['totals'],before)
