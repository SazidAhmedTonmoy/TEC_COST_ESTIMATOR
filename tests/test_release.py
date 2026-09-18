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
 def test_latest_backup_metadata_and_restore(self):
  first=backups.create_backup();second=backups.create_backup();third=backups.create_backup()
  self.assertEqual({r['name'] for r in backups.list_backups()},{third['name']})
  self.assertFalse((backups.folder()/first['name']).exists());self.assertFalse((backups.folder()/first['name']).with_suffix('.json').exists())
  backups.restore_backup(third['name']) # It may be pruned while the restoration is in progress.
  self.assertEqual(len(backups.list_backups()),1)
  with connect() as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
 def test_predeploy_names_sort_by_time_and_invalid_paths(self):
  for i,name in enumerate(['predeploy_20260915_000000.db','20260915T000000Z-daily-12345678.db','predeploy_20260915_000001.db']):
   p=backups.folder()/name;p.write_bytes(b'test');os.utime(p,(100+i,100+i))
  result=backups.list_backups();self.assertEqual(len(result),1);self.assertEqual(result[0]['name'],'predeploy_20260915_000001.db')
  self.assertTrue(backups.backup_path(result[0]['name']).exists())
  with self.assertRaises(ValueError):backups.backup_path('../main.db')

 def test_fixed_quantities_survive_save_copy_and_export(self):
  from conest_app.catalog import create_manual_catalog_item,get_catalog_item
  from conest_app.projects import add_catalog_line,save_manual_estimate_item,update_project_line,calculate_project
  from conest_app.estimate_tools import copy_line
  from conest_app.exporter import export_project
  from openpyxl import load_workbook
  with connect() as c:
   item=create_manual_catalog_item(c,{'name':'Cable kit','category_override':'Power','components':[
    {'description':'Cable','quantity_per_unit':1,'unit_material':2,'unit_hours':.1},
    {'description':'Lugs','quantity_per_unit':.04,'source_quantity':4,'unit_material':3,'unit_hours':.2}]})
   pid=create_project(c,{'name':'Fixed quantity test'})['project']['id']
   data=add_catalog_line(c,pid,item['id'],100);line=data['lines'][0]
   self.assertEqual(line['components'][1]['source_quantity'],4)
   item['components'][1].update(quantity_per_unit=4,fixed_quantity=1)
   data=save_manual_estimate_item(c,pid,{'save_mode':'new','quantity':100,'item':dict(item,category_override='Power')},line['id'])
   line=data['lines'][0];self.assertEqual(line['components'][1]['scaled_quantity'],4)
   saved=get_catalog_item(c,line['catalog_item_id']);self.assertEqual(saved['components'][1]['fixed_quantity'],1)
   update_project_line(c,pid,line['id'],{'quantity':200})
   line=calculate_project(c,pid)['lines'][0]
   self.assertEqual(line['components'][0]['scaled_quantity'],200)
   self.assertEqual(line['components'][1]['scaled_quantity'],4)
   self.assertAlmostEqual(line['components'][1]['total_hours'],.8)
   copy_line(c,pid,line['id'],{})
   self.assertEqual(calculate_project(c,pid)['lines'][1]['components'][1]['scaled_quantity'],4)
   book=load_workbook(export_project(c,pid,self.root/'fixed.xlsx'));sheet=book['CONNECTED COST DETAIL']
   rows=[row[1].row for row in sheet if row[1].value=='Lugs']
   self.assertEqual(len(rows),2)
   for row in rows:self.assertEqual(sheet.cell(row,5).value,f'=D{row}')
   # A fixed quantity still applies when the parent is zero.
   update_project_line(c,pid,line['id'],{'quantity':0})
   self.assertEqual(calculate_project(c,pid)['lines'][0]['components'][1]['scaled_quantity'],4)

 def test_help_company_projects_are_readable_but_others_are_not_editable(self):
  from conest_app.help_chat import prepare_context,answer_context
  from conest_app.accounts import AccessError
  with connect() as c:
   user=dict(c.execute("SELECT * FROM users WHERE role='user' LIMIT 1").fetchone())
   visible=create_project(c,{'name':'Orchid office'})['project']['id']
   hidden=create_project(c,{'name':'Orchid private'})['project']['id']
   c.execute('UPDATE projects SET owner_id=? WHERE id=?',(user['id'],visible))
   prepared=prepare_context(c,user,{'question':'What is the total for Orchid project?'})
   names=[p['name'] for p in prepared[1]['matching_projects']]
   self.assertIn('Orchid office',names);self.assertIn('Orchid private',names)
   with patch('conest_app.help_chat.assistant._api_key',return_value=''):
    reply=answer_context(prepared)['answer'];self.assertIn('Orchid office',reply);self.assertIn('Orchid private',reply)
   from conest_app.workspace import require_project
   prepare_context(c,user,{'question':'Total?','project_id':hidden})
   with self.assertRaises(AccessError):require_project(c,hidden,user,'edit')

 def test_failed_backup_keeps_previous_snapshot(self):
  previous=backups.create_backup()
  with patch('conest_app.backups.os.replace',side_effect=OSError('Simulated full disk')):
   with self.assertRaises(OSError):backups.create_backup()
  self.assertEqual([r['name'] for r in backups.list_backups()],[previous['name']])

 def test_fixed_quantity_distinguishes_catalog_and_revision(self):
  from copy import deepcopy
  from conest_app.taxonomy import catalog_content_key
  from conest_app.productivity import compare_snapshots
  item={'name':'Accessory','base_uom':'EA','work_type':'assembly'}
  component={'description':'Bend','quantity_per_unit':4,'fixed_quantity':0}
  original=catalog_content_key(item,[component]);component['fixed_quantity']=1
  self.assertNotEqual(original,catalog_content_key(item,[component]))
  before={'project':{'currency':'AUD'},'totals':{},'lines':[{'id':1,'name_snapshot':'Accessory','components':[dict(component,fixed_quantity=0)]}]}
  after=deepcopy(before);after['lines'][0]['components'][0]['fixed_quantity']=1
  self.assertIn('components',compare_snapshots(before,after)['changes'][0]['fields'])
