"""Builder metadata tests on isolated databases, never production data."""
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from conest_app import accounts, workspace, productivity, help_chat
from conest_app.builders import read_builders, stored_builders, validate_builders
from conest_app.database import connect
from conest_app.estimate_tools import copy_project
from conest_app.exporter import export_project
from conest_app.projects import create_project, calculate_project, update_project, list_projects
from fixtures_v232 import seed


class Builders235Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = tempfile.TemporaryDirectory()
        cls.template = Path(cls.master.name)/'fixture.db'
        with patch.dict(os.environ, {'CONEST_DB_PATH': str(cls.template), 'CONEST_LLM_ENABLED':'0'}):
            with connect() as c:
                cls.data = seed(c)
    @classmethod
    def tearDownClass(cls):
        cls.master.cleanup()
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name);self.path = self.root/'main.db'
        with sqlite3.connect(self.template) as src, sqlite3.connect(self.path) as dst:
            src.backup(dst)
        self.env = patch.dict(os.environ, {'CONEST_DB_PATH':str(self.path),'CONEST_LLM_ENABLED':'0'});self.env.start()
        self.d = copy.deepcopy(self.data)
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()
    def save(self,c,**payload):
        return workspace.update_workflow(c,self.d['project_id'],payload,self.d['owner'])

    def test_none_single_multiple_and_punctuation_round_trip(self):
        cases=[([],[]),(['Kane'],['Kane']),(['  Acme, Smith & Co  ','Beta; Group','acme, smith & co',' '],['Acme, Smith & Co','Beta; Group'])]
        with connect() as c:
            for names,expected in cases:
                p=create_project(c,{'name':'Builder test','builders':names})['project']
                self.assertEqual(p['builders'],expected)
                self.assertEqual(p['client'],'\n'.join(expected))
                self.assertEqual(calculate_project(c,p['id'])['project']['builders'],expected)

    def test_legacy_names_are_read_without_rewriting_database(self):
        with connect() as c:
            before=c.execute('SELECT client FROM projects WHERE id=?',(self.d['project_id'],)).fetchone()[0]
            self.assertEqual(before,'Sample Client')
            self.assertEqual(calculate_project(c,self.d['project_id'])['project']['builders'],['Sample Client'])
            self.assertEqual(c.execute('SELECT client FROM projects WHERE id=?',(self.d['project_id'],)).fetchone()[0],before)
            p=create_project(c,{'name':'Comma name','client':'One, Two & Three'})['project']
            self.assertEqual(p['builders'],['One, Two & Three'])
            self.assertEqual(c.execute('SELECT version FROM schema_version').fetchone()[0],26)

    def test_manager_add_clear_reopen_and_activity(self):
        with connect() as c:
            before=calculate_project(c,self.d['project_id'])['totals']
            p=self.save(c,builders=['Builder Alpha','Builder Beta'])
            self.assertEqual(p['builders'],['Builder Alpha','Builder Beta'])
            self.assertEqual(calculate_project(c,p['id'])['totals'],before)
            events=workspace.project_activity(c,p['id'],self.d['viewer'])
            self.assertEqual(events[0]['action'],'Updated project builders')
            self.assertIn('Builder Beta',events[0]['details'])
            self.assertEqual(self.save(c,builders=[])['builders'],[])
        with connect() as c:
            self.assertEqual(calculate_project(c,self.d['project_id'])['project']['builders'],[])

    def test_editor_and_nonmember_cannot_manage_builders(self):
        with connect() as c:
            before=calculate_project(c,self.d['project_id'])
            for actor in ('editor','viewer'):
                with self.assertRaises(accounts.AccessError):
                    workspace.update_workflow(c,self.d['project_id'],{'builders':['Forbidden']},self.d[actor])
            self.assertEqual(calculate_project(c,self.d['project_id']),before)

    def test_invalid_values_are_rejected_before_other_changes(self):
        cases=[None,'Builder',{'name':'Builder'},[1],[None],['a\nb'],['a\x00b'],['x'*501],['x']*101,['x'*500]*50]
        with connect() as c:
            before=calculate_project(c,self.d['project_id'])
            for value in cases:
                # Last case needs unique names to exceed the total-length limit.
                if value==['x'*500]*50: value=[str(i)+'x'*497 for i in range(50)]
                with self.subTest(value=str(value)[:70]):
                    with self.assertRaises(ValueError):self.save(c,builders=value,award_status='won')
                    self.assertEqual(calculate_project(c,self.d['project_id']),before)
            self.assertEqual(validate_builders([' ','']),[])

    def test_unrelated_settings_preserve_multiple_builders(self):
        with connect() as c:
            p=self.save(c,builders=['Alpha','Beta'])
            after=update_project(c,p['id'],{'labor_rate':95})['project']
            self.assertEqual(after['builders'],['Alpha','Beta'])
            self.assertEqual(after['client'],'Alpha\nBeta')

    def test_stale_workflow_conflict_keeps_latest_builders(self):
        with connect() as c:
            p=calculate_project(c,self.d['project_id'])['project']
            self.save(c,builders=['First'],expected_revision=p['revision'])
            with self.assertRaises(accounts.AccessError) as e:self.save(c,builders=['Stale'],expected_revision=p['revision'])
            self.assertEqual(e.exception.status,409)
            self.assertEqual(calculate_project(c,p['id'])['project']['builders'],['First'])

    def test_copy_and_revision_preserve_order_and_snapshot(self):
        with connect() as c:
            p=self.save(c,builders=['First builder','Second builder'])
            rid=productivity.save_revision(c,p['id'],self.d['owner'],{'label':'Builders saved'})
            copied=copy_project(c,p['id'],self.d['viewer'],{'name':'Independent copy'})
            self.assertEqual(calculate_project(c,copied)['project']['builders'],p['builders'])
            self.save(c,builders=['Later builder'])
            archived=productivity.revision_snapshot(c,p['id'],rid,self.d['viewer'])
            self.assertEqual(archived['project']['builders'],p['builders'])
            delta=productivity.compare_snapshots(archived,calculate_project(c,p['id']))
            self.assertIn('client',delta['settings'])
            self.assertEqual(delta['settings']['client']['before'],'First builder\nSecond builder')

    def test_every_reader_and_help_receive_builder_names(self):
        with connect() as c:
            self.save(c,builders=['Builder Alpha','Builder Beta'])
            for collection in (list_projects(c),workspace.visible_projects(c,self.d['viewer'])):
                p=next(p for p in collection if p['id']==self.d['project_id'])
                self.assertEqual(p['builders'],['Builder Alpha','Builder Beta'])
            facts=help_chat.project_facts(c,self.d['project_id'],'Which builders are on this project?',self.d['viewer'])
            self.assertIn('Builder Beta',help_chat._project_answer(facts,'builders'))

    def test_excel_names_are_multiline_text_not_formulas(self):
        from openpyxl import load_workbook
        with connect() as c:
            self.save(c,builders=['=1+1','A, B & Partners'])
            target=export_project(c,self.d['project_id'],self.root/'builders.xlsx')
        wb=load_workbook(target)
        ws=wb['COST ESTIMATE']
        self.assertEqual(ws['G2'].value,'BUILDERS')
        self.assertEqual(ws['H2'].value,'=1+1\nA, B & Partners')
        self.assertEqual(ws['H2'].data_type,'s')
        self.assertTrue(ws['H2'].alignment.wrap_text)
        self.assertGreaterEqual(ws.row_dimensions[2].height,44)
        self.assertEqual(wb['CONNECTED COST DETAIL'].row_dimensions[2].height,24)
        wb.close()

if __name__=='__main__':unittest.main()
