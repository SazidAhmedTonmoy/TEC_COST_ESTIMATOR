"""Owner-managed access and read-only upload history, using private test data."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from conest_app import accounts, auto_upgrade, workspace, productivity
from conest_app.database import connect
from conest_app.import_history import list_uploads
from conest_app.projects import create_project, calculate_project, delete_project
from conest_app.release_v23 import delete_account
from conest_app.utils import utc_now
from fixtures_v232 import seed


class Patch233Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.path=self.root/'main.db'
        self.env=patch.dict(os.environ,{'CONEST_DB_PATH':str(self.path),'CONEST_LLM_ENABLED':'0'});self.env.start()
        with connect() as c:self.d=seed(c)
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()
    def grant(self,c,**payload):
        return workspace.update_workflow(c,self.d['project_id'],payload,self.d['owner'])
    def permission(self,c,who):
        return workspace.permissions(c,workspace.get_project(c,self.d['project_id']),self.d[who])
    def source(self,c,name='catalog.xlsx',sha='hash',sheet='Sheet 1',who=None,when=None):
        return c.execute('''INSERT INTO sources(file_name,file_sha256,sheet_name,project_name,import_format,
            assembly_count,component_count,imported_at,imported_by) VALUES (?,?,?,?,?,?,?,?,?)''',
            (name,sha,sheet,'Orchid Office','conest_report',3,9,when or utc_now(),who)).lastrowid
    def receipt(self,c,name='prices-upload.xlsx',sha='lighting-hash',who=None,token='receipt'):
        report={'quotes_added':1,'groups_added':1,'lines_added':2,'quotes_skipped':0}
        c.execute('INSERT INTO lighting_import_receipts VALUES (?,?,?,?,?,?)',(token,who,name,sha,json.dumps(report),utc_now()))

    def test_nonadmin_owner_assigns_any_team_and_retains_full_control(self):
        with connect() as c:
            p=self.grant(c,team_ids=[self.d['teams'][1]],user_ids=[])
            self.assertTrue(p['can_manage']);self.assertTrue(p['can_delete'])
            self.assertEqual([r['id'] for r in p['teams']],[self.d['teams'][1]])
            self.assertTrue(self.permission(c,'viewer')['can_edit'])
            self.assertFalse(self.permission(c,'editor')['can_edit'])
            self.grant(c,team_ids=[])
            self.assertTrue(self.permission(c,'owner')['can_edit'])
            self.assertFalse(self.permission(c,'viewer')['can_edit'])

    def test_individual_access_is_project_specific_and_not_management(self):
        with connect() as c:
            before=c.execute('SELECT team_id FROM users WHERE id=?',(self.d['viewer']['id'],)).fetchone()[0]
            self.grant(c,user_ids=[self.d['viewer']['id']])
            access=self.permission(c,'viewer')
            self.assertTrue(access['can_edit']);self.assertTrue(access['is_individually_assigned'])
            self.assertFalse(access['can_manage']);self.assertFalse(access['can_delete'])
            self.assertEqual(c.execute('SELECT team_id FROM users WHERE id=?',(self.d['viewer']['id'],)).fetchone()[0],before)
            second=create_project(c,{'name':'Different project'})['project']['id']
            workspace.register_project(c,second,self.d['owner'])
            self.assertFalse(workspace.permissions(c,workspace.get_project(c,second),self.d['viewer'])['can_edit'])
            self.grant(c,user_ids=[])
            self.assertFalse(self.permission(c,'viewer')['can_edit'])
            self.assertTrue(self.permission(c,'viewer')['can_view'])

    def test_individual_access_survives_team_removal_but_not_deactivation(self):
        with connect() as c:
            self.grant(c,user_ids=[self.d['editor']['id']],team_ids=[])
            self.assertTrue(self.permission(c,'editor')['can_edit'])
            c.execute('UPDATE users SET team_id=NULL WHERE id=?',(self.d['editor']['id'],))
            self.assertTrue(self.permission(c,'editor')['can_edit'])
            c.execute('UPDATE users SET is_active=0 WHERE id=?',(self.d['editor']['id'],))
            self.assertFalse(self.permission(c,'editor')['can_view'])
            self.assertFalse(self.permission(c,'editor')['can_edit'])

    def test_editor_cannot_grant_change_brief_or_delete(self):
        with connect() as c:
            self.grant(c,user_ids=[self.d['viewer']['id']])
            for who in ('editor','viewer'):
                for payload in ({'team_ids':[]},{'user_ids':[]},{'scope_of_work':'unauthorized'}):
                    with self.subTest(who=who,payload=payload):
                        with self.assertRaises(accounts.AccessError):workspace.update_workflow(c,self.d['project_id'],payload,self.d[who])
                with self.assertRaises(accounts.AccessError):workspace.require_project(c,self.d['project_id'],self.d[who],'delete')

    def test_assignment_directory_is_minimal_and_manager_only(self):
        with connect() as c:
            options=workspace.project_access_options(c,self.d['project_id'],self.d['owner'])
            self.assertEqual(len(options['teams']),len(c.execute('SELECT id FROM teams').fetchall()))
            self.assertIn(self.d['viewer']['id'],[u['id'] for u in options['users']])
            self.assertNotIn(self.d['owner']['id'],[u['id'] for u in options['users']])
            for u in options['users']:
                self.assertEqual(set(u),{'id','name','username','team_id','is_active','team_name'})
            for who in ('editor','viewer'):
                with self.assertRaises(accounts.AccessError):workspace.project_access_options(c,self.d['project_id'],self.d[who])

    def test_invalid_assignment_payloads_do_not_change_other_fields(self):
        with connect() as c:
            p=workspace.get_project(c,self.d['project_id']);before=c.total_changes
            for payload in ({'user_ids':[True]},{'user_ids':['1']},{'user_ids':[999999]},
                            {'team_ids':[False]},{'team_ids':[999999]},{'user_ids':[self.d['admin']['id']]},
                            {'user_ids':[self.d['owner']['id']]},{'user_ids':None}):
                with self.subTest(payload=payload):
                    with self.assertRaises(ValueError):self.grant(c,award_status='won',**payload)
                    self.assertEqual(workspace.get_project(c,p['id'])['award_status'],p['award_status'])
            self.assertEqual(c.total_changes,before)
            c.execute('UPDATE users SET is_active=0 WHERE id=?',(self.d['viewer']['id'],))
            with self.assertRaises(ValueError):self.grant(c,user_ids=[self.d['viewer']['id']])

    def test_legacy_assignments_are_not_reactivated(self):
        with connect() as c:
            c.execute('INSERT INTO project_assignments VALUES (?,?,?,?)',(self.d['project_id'],self.d['viewer']['id'],self.d['admin']['id'],utc_now()))
            self.assertFalse(self.permission(c,'viewer')['can_edit'])

    def test_revision_check_and_activity_for_access_changes(self):
        with connect() as c:
            p=workspace.get_project(c,self.d['project_id'])
            after=self.grant(c,user_ids=[self.d['viewer']['id']],expected_revision=p['revision'])
            self.assertGreater(after['revision'],p['revision'])
            with self.assertRaises(accounts.AccessError):self.grant(c,user_ids=[],expected_revision=p['revision'])
            events=workspace.project_activity(c,p['id'],self.d['viewer'])
            self.assertIn('Changed individual project access',[e['action'] for e in events])
            self.assertIn(self.d['viewer']['name'],events[0]['details'])

    def test_owner_can_delete_teammate_revision(self):
        with connect() as c:
            self.assertTrue(productivity.revisions(c,self.d['project_id'],self.d['owner'])[0]['can_delete'])
            productivity.delete_revision(c,self.d['project_id'],self.d['revision_id'],self.d['owner'])
            self.assertFalse(c.execute('SELECT 1 FROM tender_revisions WHERE id=?',(self.d['revision_id'],)).fetchone())

    def test_delete_account_removes_grants_without_affecting_other_work(self):
        with connect() as c:
            self.grant(c,user_ids=[self.d['viewer']['id']])
            before=calculate_project(c,self.d['project_id'])['totals']
            delete_account(c,self.d['viewer']['id'],self.d['admin'],{'confirm_username':self.d['viewer']['username']})
            self.assertFalse(c.execute('SELECT 1 FROM project_user_access').fetchone())
            self.assertEqual(calculate_project(c,self.d['project_id'])['totals'],before)
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())

    def test_delete_project_cascades_individual_grants_not_catalogue(self):
        with connect() as c:
            self.grant(c,user_ids=[self.d['viewer']['id']])
            workspace.require_project(c,self.d['project_id'],self.d['owner'],'delete')
            delete_project(c,self.d['project_id'])
            self.assertFalse(c.execute('SELECT 1 FROM project_user_access').fetchone())
            self.assertTrue(c.execute('SELECT 1 FROM catalog_items WHERE id=?',(self.d['catalog_id'],)).fetchone())
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())

    def test_automatic_upgrade_from_24_preserves_existing_business_records(self):
        with sqlite3.connect(self.path) as c:
            c.execute('DROP TABLE project_user_access');c.execute('UPDATE schema_version SET version=24')
            c.execute("DELETE FROM app_migrations WHERE name='v2.3.3-project-access'")
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] not in ('schema_version','app_migrations','sqlite_sequence')]
            before={t:c.execute('SELECT * FROM "'+t+'"').fetchall() for t in tables}
        auto_upgrade._ready.clear()
        with connect() as c:
            self.assertEqual(c.execute('SELECT version FROM schema_version').fetchone()[0],26)
            for t in tables:self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM "'+t+'"')],before[t],t)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        snapshots=list((self.root/'upgrade_backups').glob('*.db'));self.assertEqual(len(snapshots),1)
        with sqlite3.connect(snapshots[0]) as c:self.assertEqual(c.execute('SELECT version FROM schema_version').fetchone()[0],24)
        auto_upgrade._ready.clear()
        with connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM project_user_access').fetchone()[0],0)

    def test_history_groups_catalogue_sheets_and_searches_details(self):
        with connect() as c:
            uid=self.d['owner']['id']
            self.source(c,sheet='Lighting takeoff',who=uid);self.source(c,sheet='Power takeoff',who=uid)
            before=c.total_changes
            result=list_uploads(c,self.d['owner'],{'kind':['catalog'],'q':['Power takeoff']})
            self.assertEqual(result['total'],1);row=result['uploads'][0]
            self.assertEqual((row['sheets'],row['items'],row['components']),(2,6,18))
            self.assertEqual(row['uploader_name'],self.d['owner']['name'])
            self.assertEqual(c.total_changes,before)

    def test_lighting_history_uses_actual_uploaded_filename_not_source_pdf(self):
        with connect() as c:
            c.execute('UPDATE quotes SET file_sha256=?',('lighting-hash',))
            self.receipt(c,who=self.d['viewer']['id'])
            result=list_uploads(c,self.d['viewer'],{'kind':['lighting'],'who':['me'],'q':['TEST-232-LIGHT']})
            self.assertEqual(result['total'],1);row=result['uploads'][0]
            self.assertEqual(row['filename'],'prices-upload.xlsx')
            self.assertEqual((row['quotes'],row['items'],row['components']),(1,1,2));self.assertFalse(row['legacy'])
            self.assertNotIn('token',row)
            self.assertEqual(list_uploads(c,self.d['viewer'],{'kind':['lighting']})['total'],1)

    def test_history_mine_filters_unknown_legacy_and_other_users(self):
        with connect() as c:
            self.source(c,who=self.d['owner']['id']);self.source(c,'unknown.xlsx','unknown',who=None)
            all_rows=list_uploads(c,self.d['owner'],{})
            mine=list_uploads(c,self.d['owner'],{'who':['me']})
            self.assertEqual(all_rows['total'],3);self.assertEqual(mine['total'],1)
            self.assertTrue(any(r['legacy'] for r in all_rows['uploads']))
            self.assertEqual(list_uploads(c,self.d['viewer'],{'who':['me']})['total'],0)

    def test_history_literal_wildcards_paging_validation_and_no_paths(self):
        with connect() as c:
            for n in range(5):self.source(c,f'/private/server/Fitting_{n}%.xlsx',str(n),who=self.d['owner']['id'])
            first=list_uploads(c,self.d['owner'],{'q':['%'],'limit':['2']});second=list_uploads(c,self.d['owner'],{'q':['%'],'limit':['2'],'offset':['2']})
            self.assertEqual(first['total'],5);self.assertTrue(first['has_more'])
            self.assertFalse({r['id'] for r in first['uploads']} & {r['id'] for r in second['uploads']})
            self.assertTrue(all('/' not in r['filename'] for r in first['uploads']))
            self.assertEqual(list_uploads(c,self.d['owner'],{'q':["' OR 1=1 --"]})['total'],0)
            for query in ({'kind':['no']},{'who':['99']},{'limit':['0']},{'offset':['-1']},{'q':['a'*201]}):
                with self.assertRaises(ValueError):list_uploads(c,self.d['owner'],query)
            c.execute('UPDATE users SET is_active=0 WHERE id=?',(self.d['owner']['id'],))
            with self.assertRaises(accounts.AccessError):list_uploads(c,self.d['owner'],{})

    def test_html_uploads_navigation_profile_and_access_controls(self):
        html=(Path(__file__).parents[1]/'assets/index.html').read_text()
        imports=html[html.index('<section id="imports-view"'):html.index('<section id="settings-view"')]
        self.assertLess(imports.index('id="import-form"'),imports.index('id="light-price-import-form"'))
        self.assertIn('import-history-button',imports);self.assertNotIn('Audit trail',imports);self.assertNotIn('source-rows',imports)
        self.assertNotIn('id="light-price-import-form"',html[html.index('id="light-prices-view"'):html.index('id="imports-view"')])
        self.assertLess(html.index('data-view="light-prices"'),html.index('data-view="imports"'))
        self.assertIn('Profile Photo',html);self.assertIn('Password &amp; Security',html)
        self.assertNotIn('profile-photo-help',html);self.assertNotIn('no photo history is kept',html)
        self.assertIn('id="project-access-fieldset" class="assignment-fieldset"',html)

if __name__=='__main__':unittest.main()
