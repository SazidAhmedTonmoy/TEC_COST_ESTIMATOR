"""Code-only release: photo replacement, company viewing and grounded Help."""
import base64
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

from conest_app import accounts, project_notes, productivity, workspace
from conest_app.database import connect
from conest_app.help_chat import prepare_context, answer_context
from conest_app.projects import calculate_project, create_project, update_project_line
from fixtures_v232 import seed


def image_url(color):
    out=io.BytesIO();Image.new('RGB',(64,64),color).save(out,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()


class Patch232Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'CONEST_DB_PATH':str(self.root/'main.db'),'CONEST_LLM_ENABLED':'0'});self.env.start()
        with connect() as c:self.data=seed(c)
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()
    def answer(self,c,question,**extra):
        return answer_context(prepare_context(c,self.data['viewer'],{'question':question,**extra}))

    def test_company_wide_view_for_every_workflow_status(self):
        with connect() as c:
            for status in workspace.STATUSES:
                c.execute('UPDATE projects SET status=? WHERE id=?',(status,self.data['project_id']))
                p=workspace.get_project(c,self.data['project_id'])
                access=workspace.permissions(c,p,self.data['viewer'])
                self.assertTrue(access['can_view']);self.assertFalse(access['can_edit']);self.assertFalse(access['can_manage']);self.assertFalse(access['can_delete'])
                self.assertIn(p['id'],[r['id'] for r in workspace.visible_projects(c,self.data['viewer'])])

    def test_owner_admin_and_assigned_team_edit_permissions_are_live(self):
        with connect() as c:
            p=workspace.get_project(c,self.data['project_id'])
            for who in ('owner','admin','editor'):
                self.assertTrue(workspace.permissions(c,p,self.data[who])['can_edit'])
            c.execute('UPDATE users SET team_id=? WHERE id=?',(self.data['teams'][0],self.data['viewer']['id']))
            self.assertTrue(workspace.permissions(c,p,self.data['viewer'])['can_edit'])
            c.execute('UPDATE users SET team_id=NULL WHERE id=?',(self.data['viewer']['id'],))
            self.assertFalse(workspace.permissions(c,p,self.data['viewer'])['can_edit'])
            c.execute('UPDATE users SET team_id=NULL WHERE id=?',(self.data['owner']['id'],))
            self.assertTrue(workspace.permissions(c,p,self.data['owner'])['can_edit'])

    def test_inactive_accounts_cannot_view_or_use_help(self):
        with connect() as c:
            c.execute('UPDATE users SET is_active=0 WHERE id=?',(self.data['viewer']['id'],))
            self.assertFalse(workspace.permissions(c,workspace.get_project(c,self.data['project_id']),self.data['viewer'])['can_view'])
            with self.assertRaises(accounts.AccessError):workspace.visible_projects(c,self.data['viewer'])
            with self.assertRaises(accounts.AccessError):self.answer(c,'Show all projects')

    def test_readonly_notes_and_revisions_reject_all_mutations(self):
        with connect() as c:
            d=self.data;pid=d['project_id'];user=d['viewer']
            notes=project_notes.list_notes(c,pid,user);self.assertEqual(len(notes),1);self.assertFalse(notes[0]['can_delete'])
            revs=productivity.revisions(c,pid,user);self.assertEqual(len(revs),1);self.assertFalse(revs[0]['can_delete'])
            productivity.revision_snapshot(c,pid,d['revision_id'],user)
            operations=[lambda:project_notes.add_note(c,pid,user,{'body':'unauthorized'}),
                lambda:project_notes.delete_note(c,pid,d['note_id'],user),
                lambda:productivity.save_revision(c,pid,user,{'label':'forbidden'}),
                lambda:productivity.delete_revision(c,pid,d['revision_id'],user),
                lambda:workspace.update_workflow(c,pid,{'status':'completed'},user)]
            before=c.total_changes
            for action in operations:
                with self.assertRaises(accounts.AccessError) as error:action()
                self.assertEqual(error.exception.status,403)
            self.assertEqual(c.total_changes,before)
            # Personal read acknowledgements do not edit project content.
            self.assertEqual(project_notes.mark_notes_read(c,pid,user,{'note_ids':[d['note_id']]})['unread_count'],0)

    def test_revision_author_loses_delete_access_after_leaving_team(self):
        with connect() as c:
            d=self.data;c.execute('UPDATE users SET team_id=? WHERE id=?',(d['teams'][1],d['editor']['id']))
            self.assertFalse(productivity.revisions(c,d['project_id'],d['editor'])[0]['can_delete'])
            with self.assertRaises(accounts.AccessError):productivity.delete_revision(c,d['project_id'],d['revision_id'],d['editor'])

    def test_activity_history_is_paginated_without_gaps(self):
        with connect() as c:
            d=self.data
            for n in range(211):workspace.record_activity(c,d['project_id'],d['owner'],'Test change',str(n),touch=False)
            page=workspace.project_activity(c,d['project_id'],d['viewer']);self.assertEqual(len(page),200)
            next_page=workspace.project_activity(c,d['project_id'],d['viewer'],before_id=page[-1]['id'])
            seen=[r['id'] for r in page+next_page]
            self.assertEqual(len(seen),len(set(seen)))
            self.assertEqual(len(seen),c.execute('SELECT COUNT(*) FROM project_activity WHERE project_id=?',(d['project_id'],)).fetchone()[0])
            with self.assertRaises(ValueError):workspace.project_activity(c,d['project_id'],d['viewer'],before_id=-1)

    def test_replacing_photo_keeps_one_row_and_only_latest_bytes(self):
        with connect() as c:
            actor=self.data['admin'];uid=actor['id'];old=None
            for color in ('red','green','blue'):
                saved=accounts.edit_user(c,uid,{'photo_data_url':image_url(color)},actor,admin=True)
                current=bytes(c.execute('SELECT image FROM user_avatars WHERE user_id=?',(uid,)).fetchone()[0])
                self.assertNotEqual(old,current);old=current
                self.assertEqual(c.execute('SELECT COUNT(*) FROM user_avatars WHERE user_id=?',(uid,)).fetchone()[0],1)
            self.assertEqual(saved['avatar_version'],3)
            accounts.edit_user(c,uid,{'remove_photo':True},actor,admin=True)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM user_avatars WHERE user_id=?',(uid,)).fetchone()[0],0)

    def test_invalid_replacement_and_database_failure_keep_old_photo(self):
        with connect() as c:
            actor=self.data['admin'];uid=actor['id']
            accounts.edit_user(c,uid,{'photo_data_url':image_url('red')},actor,admin=True)
            before=tuple(c.execute('SELECT * FROM user_avatars WHERE user_id=?',(uid,)).fetchone())
            with self.assertRaises(ValueError):accounts.edit_user(c,uid,{'photo_data_url':'data:image/png;base64,bad'},actor,admin=True)
            self.assertEqual(tuple(c.execute('SELECT * FROM user_avatars WHERE user_id=?',(uid,)).fetchone()),before)
            c.execute("CREATE TEMP TRIGGER fail_avatar BEFORE INSERT ON user_avatars BEGIN SELECT RAISE(ABORT,'test disk failure'); END")
            with self.assertRaises(sqlite3.IntegrityError):accounts.edit_user(c,uid,{'photo_data_url':image_url('blue')},actor,admin=True)
            self.assertEqual(tuple(c.execute('SELECT * FROM user_avatars WHERE user_id=?',(uid,)).fetchone()),before)

    def test_help_project_totals_and_activity_are_from_live_records(self):
        with connect() as c:
            actual=calculate_project(c,self.data['project_id'])['totals']
            with patch('conest_app.help_chat.assistant._gemini_generate') as ai:
                reply=self.answer(c,'Summarise Orchid Office and its latest updates')
            ai.assert_not_called()
            self.assertIn(f"AUD {actual['material']:,.2f}",reply['answer']);self.assertIn(f"AUD {actual['labor']:,.2f}",reply['answer'])
            self.assertIn('Confirmed D1 supply quantity',reply['answer']);self.assertIn('read-only for you',reply['answer'])
            self.assertEqual(reply['sources'][0]['url'],f"#/estimate/{self.data['project_id']}")

    def test_help_exact_reference_quantity_does_not_count_d10(self):
        with connect() as c:
            reply=self.answer(c,'How many D1 are in this project?',project_id=self.data['project_id'])['answer']
            self.assertIn('Matching quantity: 7 EA',reply);self.assertIn('[Ref: D1]',reply);self.assertNotIn('[Ref: D10]',reply)
            reply=self.answer(c,'How many D99 are in this project?',project_id=self.data['project_id'])['answer']
            self.assertIn('No estimate lines match d99',reply)

    def test_help_catalog_name_alias_and_components(self):
        with connect() as c:
            for question in ['Find LED Batten in catalog','Find test linear fitting in catalog','Find Cable accessories in catalog']:
                with self.subTest(question=question):
                    reply=self.answer(c,question)['answer']
                    self.assertIn('LED Batten',reply);self.assertIn('0.4 hours',reply);self.assertIn('30.00 fixed-price labour',reply)
                    self.assertIn('2.5 mm2',reply)

    def test_help_light_nickname_and_connected_components(self):
        with connect() as c:
            for question in ['What is the light price for DL-100?', 'Find light price Orchid favourite']:
                reply=self.answer(c,question)['answer']
                self.assertIn('AUD 102.50',reply);self.assertIn('AUD 1,025.00',reply);self.assertIn('DALI driver',reply)
                self.assertIn('Quote TEST-232-LIGHT',reply)

    def test_help_missing_included_price_never_reports_complete_unit_price(self):
        with connect() as c:
            c.execute("UPDATE lines SET total_ex=NULL WHERE group_id=? AND cat_no='DRV-100'",(self.data['light_id'],))
            reply=self.answer(c,'Explain this light price',light_group_id=self.data['light_id'])['answer']
            self.assertIn('NOT AVAILABLE',reply);self.assertIn('1 included row(s) without a price',reply)
            self.assertNotIn('Connected unit price: AUD',reply)

    def test_help_selected_total_mode_and_excluded_components(self):
        with connect() as c:
            c.execute("UPDATE lines SET total_ex=890 WHERE group_id=? AND cat_no='DL-100'",(self.data['light_id'],))
            c.execute("UPDATE lines SET included=0 WHERE group_id=? AND cat_no='DRV-100'",(self.data['light_id'],))
            reply=self.answer(c,'Explain this light price',light_group_id=self.data['light_id'])['answer']
            self.assertIn('AUD 89.00',reply);self.assertIn('EXCLUDED: DALI driver',reply);self.assertIn('differs from quantity x rate',reply)

    def test_help_followup_resolves_record_and_rejects_deleted_record(self):
        with connect() as c:
            reply=self.answer(c,'Find LED Batten in catalog')
            follow=self.answer(c,'What are its components?',follow_up=reply['follow_up'])
            self.assertIn('Cable accessories',follow['answer'])
            with self.assertRaises(LookupError):self.answer(c,'What are its components?',follow_up={'kind':'catalog','id':999999})

    def test_help_unknown_named_project_does_not_use_open_project(self):
        with connect() as c:
            reply=self.answer(c,'What is the total for Missing Warehouse project?',project_id=self.data['project_id'])
            self.assertIn('No matching project',reply['answer']);self.assertNotIn('Orchid Office (project',reply['answer'])

    def test_help_can_read_all_project_notes_and_revisions(self):
        with connect() as c:
            reply=self.answer(c,'Show notes and revisions for Orchid Office')['answer']
            self.assertIn('specified D1 dimming driver',reply);self.assertIn('Original',reply)

    def test_help_is_read_only_and_never_contains_credentials(self):
        with connect() as c:
            before=c.total_changes
            reply=self.answer(c,'Show all projects')
            self.assertEqual(before,c.total_changes)
            encoded=json.dumps(reply)
            self.assertNotIn('password_hash',encoded);self.assertNotIn('gemini_api_key',encoded)
            self.assertIn('Orchid Office',encoded)

    def test_help_input_ids_and_scopes_are_validated(self):
        with connect() as c:
            for extra in [{'project_id':True},{'catalog_item_id':-2},{'light_group_id':'1'},{'scope':'sql'},
                          {'follow_up':{'kind':'users','id':1}},{'follow_up':{'kind':'project','id':1,'sql':'delete'}}]:
                with self.subTest(extra=extra),self.assertRaises(ValueError):self.answer(c,'Show data',**extra)

    def test_monthly_material_and_labor_values_match_estimate_calculation(self):
        with connect() as c:
            expected=calculate_project(c,self.data['project_id'])['totals']
            board=next(p for p in workspace.visible_projects(c,self.data['viewer']) if p['id']==self.data['project_id'])
            self.assertEqual(board['totals'],expected)
            self.assertAlmostEqual(expected['direct'],expected['material']+expected['labor'])
            self.assertAlmostEqual(expected['quoted'],expected['direct']*1.05)
            self.assertAlmostEqual(expected['labor'],4*90+10*30)

if __name__=='__main__':unittest.main()
