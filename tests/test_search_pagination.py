import unittest
import test_hours_markup as helpers
from conest_app.database import connect
from conest_app.catalog import create_manual_catalog_item, search_catalog
class SearchPaginationTests(unittest.TestCase):
 setUp=helpers.HoursMarkupTests.setUp
 tearDown=helpers.HoursMarkupTests.tearDown
 def test_all_title_matches_are_reachable(self):
  with connect() as c:
   for i in range(43):
    name=f'Isolator assembly {i}' if i<40 else f'IP66 250 V Surface Isolator (1PH-{i} A)'
    create_manual_catalog_item(c,{'name':name,'category_override':'Power','components':[{'description':name,'quantity_per_unit':1,'unit_material':i+1}]})
   seen=[]
   for offset in [0,30]:
    info={};rows=search_catalog(c,'ISOLATOR',30,offset=offset,page_info=info,recent_first=True)
    self.assertEqual(info['total'],43);self.assertEqual(info['has_more'],offset==0);seen+=rows
   self.assertEqual(len({r['id'] for r in seen}),43)
   self.assertEqual(sum('Surface' in r['name'] for r in seen),3)
   info={};self.assertEqual(search_catalog(c,'isolator',30,offset=60,page_info=info),[])
   self.assertFalse(info['has_more'])
 def test_distinct_titles_with_identical_allowances_remain_visible(self):
  with connect() as c:
   ids=[]
   for name in ['ISOLATOR 2 POLE','IP66 250 V Surface Isolator (1PH-15 A)']:
    item=create_manual_catalog_item(c,{'name':name,'category_override':'Power','components':[{'description':'Same allowance','quantity_per_unit':1,'unit_material':5.76,'unit_hours':.08}]})
    ids.append(item['id'])
   key=c.execute('SELECT content_key FROM catalog_items WHERE id=?',(ids[0],)).fetchone()[0]
   c.execute('UPDATE catalog_items SET content_key=? WHERE id=?',(key,ids[1]))
   broad=search_catalog(c,'isolator',100)
   narrow=search_catalog(c,'isolator 1',100)
   self.assertTrue(set(ids)<={r['id'] for r in broad})
   self.assertTrue({r['id'] for r in narrow}<={r['id'] for r in broad})
