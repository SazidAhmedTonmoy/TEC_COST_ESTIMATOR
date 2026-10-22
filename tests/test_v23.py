"""v2.3 regression coverage: upgrades, project refs/outcomes, prices, media and deletion."""
import base64
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from openpyxl import load_workbook
from conest_app.auto_upgrade import CURRENT_SCHEMA
from conest_app.database import initialize, connect
from conest_app.accounts import AccessError, start_session, session_user
from conest_app import light_prices
from conest_app.catalog import create_manual_catalog_item, get_catalog_item
from conest_app.projects import create_project, add_catalog_line, update_project_line, calculate_project, save_manual_estimate_item
from conest_app.workspace import register_project, update_workflow, get_project, project_activity, project_contributors
from conest_app.estimate_tools import copy_line, copy_project
from conest_app.productivity import save_revision, revision_snapshot, compare_snapshots
from conest_app.project_notes import add_note, list_notes, mark_notes_read
from conest_app.release_v23 import delete_account
from conest_app.exporter import export_project


class Version23Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.environment = patch.dict(os.environ, {'CONEST_DB_PATH': str(self.root/'main.db'), 'CONEST_LIGHT_PRICES_DB': str(self.root/'unused.db')})
        self.environment.start(); initialize()
        with connect() as conn:
            self.admin = dict(conn.execute("SELECT * FROM users WHERE role='admin' LIMIT 1").fetchone())
            self.user = dict(conn.execute("SELECT * FROM users WHERE role='user' LIMIT 1").fetchone())

    def tearDown(self):
        self.environment.stop(); self.folder.cleanup()

    def project(self, conn, owner=None):
        pid = create_project(conn, {'name':'v2.3 test project'})['project']['id']
        register_project(conn, pid, owner or self.admin)
        return pid

    def light(self):
        rows = [
            {'Type':'D1', 'Supplier':'Supplier A','Qty':10,'Cat No':'L-1','Description':'Light body','Unit Ex GST':20,'Total Ex GST':190},
            {'Type':'','Supplier':'Supplier A','Qty':5,'Cat No':'DRV','Description':'Driver','Unit Ex GST':10,'Total Ex GST':50},
            {'Type':'','Supplier':'Supplier B','Qty':1,'Cat No':'FR','Description':'Freight','Unit Ex GST':30,'Total Ex GST':30},
        ]
        quote = {'reference':'TEST-V23','quote_date':'2026-09-17','project':'Lighting test','source':'test.xlsx','total_ex':270,
                 'lines':[light_prices.normal_line(row, i) for i,row in enumerate(rows,1)]}
        light_prices.save_quotes([quote])
        return light_prices.search()['results'][0]['id']

    def edit_payload(self, ident):
        item = light_prices.detail(ident)
        return {**{key:item[key] for key in ('description','nickname','notes','base_qty','primary_unit','project','reference','quote_date')},
                'expected_revision':item['revision'], 'components':[{key:row[key] for key in
                ('id','description','supplier','cat_no','quantity','unit_ex','total_ex','status','included','total_mode')}
                for row in item['components']]}

    def update_light(self, ident, payload):
        with connect() as conn:
            return light_prices.update(conn,ident,payload,self.admin)

    def test_schema_idempotent_preserves_notes_and_reads(self):
        with connect() as conn:
            pid=self.project(conn,self.user); notes=add_note(conn,pid,self.user,{'body':'Retain this note'})
            mark_notes_read(conn,pid,self.admin,{'note_ids':[notes[0]['id']]})
        initialize();initialize()
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM project_notes').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM project_note_reads').fetchone()[0],1)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
            self.assertEqual(conn.execute('SELECT version FROM schema_version').fetchone()[0],CURRENT_SCHEMA)

    def test_legacy_notes_migration_keeps_deleted_id_sequence(self):
        import sqlite3
        from conest_app.release_v23 import initialize_v23
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        conn.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE users(id INTEGER PRIMARY KEY);
            CREATE TABLE projects(id INTEGER PRIMARY KEY);
            CREATE TABLE project_lines(id INTEGER PRIMARY KEY);
            CREATE TABLE project_activity(id INTEGER PRIMARY KEY);
            CREATE TABLE tender_revisions(id INTEGER PRIMARY KEY);
            CREATE TABLE catalog_price_history(id INTEGER PRIMARY KEY);
            CREATE TABLE app_migrations(name TEXT PRIMARY KEY,created_at TEXT);
            CREATE TABLE schema_version(version INTEGER); INSERT INTO schema_version VALUES(21);
            INSERT INTO users VALUES(1); INSERT INTO projects VALUES(1);
            CREATE TABLE project_notes(id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id),
                author_id INTEGER NOT NULL REFERENCES users(id),body TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE project_note_reads(note_id INTEGER REFERENCES project_notes(id),
                user_id INTEGER REFERENCES users(id),read_at TEXT,PRIMARY KEY(note_id,user_id));
            INSERT INTO project_notes VALUES(1,1,1,'Keep note','2026-09-17');
            INSERT INTO project_note_reads VALUES(1,1,'2026-09-17');
            INSERT INTO project_notes VALUES(99,1,1,'Deleted note','2026-09-17');
            DELETE FROM project_notes WHERE id=99;
        """)
        initialize_v23(conn);initialize_v23(conn)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM project_note_reads').fetchone()[0],1)
        conn.execute("INSERT INTO project_notes(project_id,author_id,body,created_at) VALUES(1,1,'New','2026-09-17')")
        self.assertEqual(conn.execute('SELECT MAX(id) FROM project_notes').fetchone()[0],100)
        self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall());conn.close()

    def test_reference_survives_full_estimate_editor_without_catalog_write(self):
        with connect() as conn:
            item=create_manual_catalog_item(conn,{'name':'Exit light','category_override':'Emergency & Exit Lighting',
                'components':[{'description':'Exit','quantity_per_unit':1,'unit_material':0,'is_parent':1}]})
            pid=self.project(conn);line=add_catalog_line(conn,pid,item['id'],2)['lines'][0]
            update_project_line(conn,pid,line['id'],{'reference_name':'EX1'})
            item_count=conn.execute('SELECT COUNT(*) FROM catalog_items').fetchone()[0]
            latest=calculate_project(conn,pid)['lines'][0]
            result=save_manual_estimate_item(conn,pid,{'expected_revision':latest['revision'],
                'save_mode':'estimate','quantity':3,'item':{'name':'Edited exit light',
                'category_override':'Emergency & Exit Lighting','base_uom':'EA',
                'components':[{'description':'Exit','quantity_per_unit':1,'unit_material':90,'is_parent':1}]}},line['id'])
            self.assertEqual(result['lines'][0]['reference_name'],'EX1')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM catalog_items').fetchone()[0],item_count)
            self.assertEqual(get_catalog_item(conn,item['id'])['name'],'Exit light')

    def test_project_outcome_independent_optional_and_revision_checked(self):
        with connect() as conn:
            pid=self.project(conn)
            for award in ('won','lost',''):
                previous=get_project(conn,pid)
                result=update_workflow(conn,pid,{'award_status':award,'expected_revision':previous['revision']},self.admin)
                self.assertEqual(result['award_status'],award)
                self.assertEqual(result['status'],'draft')
            with self.assertRaises(ValueError):update_workflow(conn,pid,{'award_status':'maybe'},self.admin)
            with self.assertRaises(AccessError):update_workflow(conn,pid,{'award_status':'won','expected_revision':-1},self.admin)
            self.assertEqual(sum(a['action']=='Changed project result' for a in project_activity(conn,pid,self.admin)),3)

    def test_reference_project_only_and_copies_snapshots_excel(self):
        with connect() as conn:
            item=create_manual_catalog_item(conn,{'name':'Test batten','category_override':'Lighting','components':[
                {'description':'Batten','quantity_per_unit':1,'unit_material':0,'is_parent':1},
                {'description':'Install','quantity_per_unit':1,'unit_hours':.2}]})
            pid=self.project(conn)
            line=add_catalog_line(conn,pid,item['id'],7)['lines'][0]
            before=calculate_project(conn,pid)
            update_project_line(conn,pid,line['id'],{'reference_name':'D1 / Office','expected_revision':line['revision']})
            after=calculate_project(conn,pid)
            self.assertEqual(after['lines'][0]['reference_name'],'D1 / Office')
            self.assertNotIn('reference_name',get_catalog_item(conn,item['id']))
            self.assertIn('reference_name',compare_snapshots(before,after)['changes'][0]['fields'])
            self.assertEqual(after['totals'],before['totals'])
            copy_line(conn,pid,line['id'],{})
            self.assertEqual(calculate_project(conn,pid)['lines'][1]['reference_name'],'D1 / Office')
            rid=save_revision(conn,pid,self.admin,{'label':'Original'})
            self.assertEqual(revision_snapshot(conn,pid,rid,self.admin)['lines'][0]['reference_name'],'D1 / Office')
            copied=copy_project(conn,pid,self.admin,{})
            self.assertEqual(calculate_project(conn,copied)['lines'][0]['reference_name'],'D1 / Office')
            output=export_project(conn,pid,self.root/'reference.xlsx')
            book=load_workbook(output);sheet=book['CONNECTED COST DETAIL']
            cells=[cell for row in sheet for cell in row if cell.value=='Test batten\nRef: D1 / Office']
            self.assertEqual(len(cells),2)
            for cell in cells:
                self.assertTrue(cell.alignment.wrap_text)
                self.assertEqual(cell.column,2)
                self.assertGreaterEqual(sheet.row_dimensions[cell.row].height,40)
            book.close()

    def test_reference_invalid_values(self):
        with connect() as conn:
            item=create_manual_catalog_item(conn,{'name':'Outlet','category_override':'Power','components':[{'description':'Outlet','quantity_per_unit':1}]})
            pid=self.project(conn);lid=add_catalog_line(conn,pid,item['id'],1)['lines'][0]['id']
            for value in ('D1', 'a'*121, 1):
                with self.assertRaises(ValueError):update_project_line(conn,pid,lid,{'reference_name':value})

    def test_package_arithmetic_same_in_card_and_detail(self):
        ident=self.light();item=light_prices.detail(ident);card=light_prices.search()['results'][0]
        for key in ('connected_unit_ex','connected_total_ex','missing_prices','included_count','difference_count'):
            self.assertEqual(item[key],card[key])
        self.assertEqual(item['connected_total_ex'],270)
        self.assertEqual(item['connected_unit_ex'],27)
        self.assertEqual(item['main_row_unit_ex'],20)
        self.assertEqual(item['difference_count'],1)
        self.assertEqual(item['components'][0]['difference_ex'],-10)
        self.assertEqual(item['components'][1]['quantity_per_primary'],.5)
        self.assertEqual(item['components'][1]['contribution_unit_ex'],5)
        self.assertEqual(item['implicit_links'],2)

    def test_edit_nickname_search_price_mode_exclusion_and_immutable_source(self):
        ident=self.light();payload=self.edit_payload(ident)
        payload.update(description='Renamed light',nickname='Office favourite',notes='Test specification',primary_unit='fitting')
        payload['components'][0]['total_mode']='calculated'
        payload['components'][2]['included']=False
        result=self.update_light(ident,payload)
        self.assertEqual(result['connected_total_ex'],250)
        self.assertEqual(result['connected_unit_ex'],25)
        self.assertEqual(result['difference_count'],0)
        self.assertEqual(result['components'][0]['original']['Total Ex GST'],190)
        self.assertEqual(result['components'][0]['total_ex'],190)
        self.assertEqual(light_prices.search('office favourite')['results'][0]['id'],ident)
        self.assertEqual(light_prices.search('Renamed light')['total'],1)
        self.assertEqual(result['edit_count'],1)
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM lighting_edit_history').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT reference FROM quotes').fetchone()[0],'TEST-V23')

    def test_missing_and_zero_are_distinct_and_divisor_guarded(self):
        ident=self.light();payload=self.edit_payload(ident)
        payload['components'][1]['total_ex']=None
        result=self.update_light(ident,payload)
        self.assertEqual(result['missing_prices'],1);self.assertIsNone(result['connected_unit_ex'])
        self.assertEqual(result['connected_total_ex'],220)
        payload=self.edit_payload(ident);payload['components'][1]['total_ex']=0
        result=self.update_light(ident,payload)
        self.assertEqual(result['missing_prices'],0);self.assertEqual(result['connected_unit_ex'],22)
        payload=self.edit_payload(ident);payload['base_qty']=0
        self.assertIsNone(self.update_light(ident,payload)['connected_unit_ex'])
        payload=self.edit_payload(ident)
        for row in payload['components']:row['included']=False
        self.assertIsNone(self.update_light(ident,payload)['connected_unit_ex'])

    def test_price_edit_conflicts_and_cross_group_rows_rejected(self):
        ident=self.light();payload=self.edit_payload(ident)
        self.update_light(ident,payload)
        with self.assertRaises(AccessError):self.update_light(ident,payload)
        payload=self.edit_payload(ident);payload['components'][0]['id']=999999
        with self.assertRaises(ValueError):self.update_light(ident,payload)
        payload=self.edit_payload(ident);payload['components'].pop()
        with self.assertRaises(ValueError):self.update_light(ident,payload)
        payload=self.edit_payload(ident);payload['components'][0]['unit_ex']=-1
        with self.assertRaises(ValueError):self.update_light(ident,payload)
        payload=self.edit_payload(ident);payload['components'][0]['unit_ex']=float('nan')
        with self.assertRaises(ValueError):self.update_light(ident,payload)

    def test_manual_component_and_rounding(self):
        ident=self.light();payload=self.edit_payload(ident)
        payload['components'].append({'id':None,'description':'Connector','supplier':'New supplier','cat_no':'CN',
            'quantity':1,'unit_ex':1.005,'total_ex':None,'status':'Manual','included':True,'total_mode':'calculated'})
        result=self.update_light(ident,payload)
        self.assertEqual(result['components'][-1]['calculated_total_ex'],1.01)
        self.assertEqual(result['connected_total_ex'],271.01)
        self.assertEqual(light_prices.search('New supplier')['total'],1)

    def test_photo_is_normalized_in_database_and_removable(self):
        ident=self.light();payload=self.edit_payload(ident)
        output=io.BytesIO();Image.new('RGB',(1800,900),(120,100,50)).save(output,'PNG')
        payload['photo_data_url']='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()
        result=self.update_light(ident,payload);self.assertTrue(result['has_photo'])
        with connect() as conn:
            photo=conn.execute('SELECT mime,image FROM lighting_photos WHERE group_id=?',(ident,)).fetchone()
            self.assertEqual(photo['mime'],'image/jpeg')
            self.assertEqual(Image.open(io.BytesIO(photo['image'])).size,(1600,800))
        payload=self.edit_payload(ident);payload['remove_photo']=True
        self.assertFalse(self.update_light(ident,payload)['has_photo'])
        payload=self.edit_payload(ident);payload['photo_data_url']='data:image/svg+xml;base64,PHN2Zz4='
        with self.assertRaises(ValueError):self.update_light(ident,payload)
        payload=self.edit_payload(ident);payload['photo_data_url']='data:image/png;base64,bm90IGFuIGltYWdl'
        with self.assertRaises(ValueError):self.update_light(ident,payload)

    def test_delete_account_keeps_history_notes_revisions_and_work(self):
        with connect() as conn:
            pid=self.project(conn,self.user)
            notes=add_note(conn,pid,self.user,{'body':'Author should be preserved'})
            mark_notes_read(conn,pid,self.admin,{'note_ids':[notes[0]['id']]})
            save_revision(conn,pid,self.user,{'label':'Original'})
            token=start_session(conn,self.user['id'])
            self.assertIsNotNone(session_user(conn,token))
            result=delete_account(conn,self.user['id'],self.admin,{'confirm_username':self.user['username']})
            self.assertEqual(result['transferred_projects'],1)
            self.assertIsNone(conn.execute('SELECT * FROM users WHERE id=?',(self.user['id'],)).fetchone())
            self.assertIsNone(session_user(conn,token))
            self.assertEqual(get_project(conn,pid)['owner_id'],self.admin['id'])
            self.assertEqual(list_notes(conn,pid,self.admin)[0]['author_name'],self.user['name'])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM project_note_reads').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM tender_revisions').fetchone()[0],1)
            self.assertIn(self.user['name'],[a['name'] for a in project_activity(conn,pid,self.admin)])
            self.assertIn(self.user['name'],[a['name'] for a in project_contributors(conn,pid)])
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        initialize()
        with connect() as conn:
            self.assertFalse(conn.execute('SELECT 1 FROM users WHERE id=?',(self.user['id'],)).fetchone())

    def test_delete_authorization_and_confirmation(self):
        with connect() as conn:
            with self.assertRaises(AccessError):delete_account(conn,self.admin['id'],self.user,{'confirm_username':self.admin['username']})
            with self.assertRaises(ValueError):delete_account(conn,self.admin['id'],self.admin,{'confirm_username':self.admin['username']})
            with self.assertRaises(ValueError):delete_account(conn,self.user['id'],self.admin,{'confirm_username':'wrong'})
            self.assertIsNotNone(conn.execute('SELECT id FROM users WHERE id=?',(self.user['id'],)).fetchone())


if __name__=='__main__':
    unittest.main()
