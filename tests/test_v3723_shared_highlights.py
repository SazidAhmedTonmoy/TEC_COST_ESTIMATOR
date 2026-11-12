"""v3.7.23: shared estimate highlights and individual homepage selection."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from conest_app import accounts, teams
from conest_app.auto_upgrade import CURRENT_SCHEMA, MIGRATION_KEY, _ready
from conest_app.database import connect, _raw_connect
from conest_app.projects import calculate_project
from fixtures_v232 import seed
from test_http_v232 import Http232Tests


class SharedHighlightHTTPTests(unittest.TestCase):
    setUp=Http232Tests.setUp
    tearDown=Http232Tests.tearDown
    request=Http232Tests.request
    login_as=Http232Tests.login_as

    def test_changes_saved_for_every_account_and_no_price_revision(self):
        pid,lid=self.data['project_id'],self.data['line_id']
        self.login_as('editor')
        status,initial=self.request('GET',f'/api/projects/{pid}')
        self.assertEqual(status,200)
        old_revision=initial['project']['revision']
        old_totals=initial['totals']
        self.assertEqual(next(l for l in initial['lines'] if l['id']==lid)['highlight_level'],0)
        for old,new in [(0,1),(1,2),(2,0)]:
            status,result=self.request('PATCH',f'/api/projects/{pid}/lines/{lid}/highlight',
                                       {'level':new,'expected_level':old})
            self.assertEqual(status,200,result)
            self.assertEqual(result['level'],new)
            self.login_as('viewer')
            status,listing=self.request('GET',f'/api/projects/{pid}/highlights')
            self.assertEqual(status,200,listing)
            self.assertEqual(next(m for m in listing['highlights'] if m['id']==lid)['level'],new)
            status,project=self.request('GET',f'/api/projects/{pid}')
            self.assertEqual(status,200)
            self.assertEqual(next(l for l in project['lines'] if l['id']==lid)['highlight_level'],new)
            self.assertEqual(project['project']['revision'],old_revision)
            self.assertEqual(project['totals'],old_totals)
            self.login_as('editor')

    def test_read_only_cannot_mark_and_stale_updates_rejected(self):
        pid,lid=self.data['project_id'],self.data['line_id']
        self.login_as('viewer')
        status,record=self.request('PATCH',f'/api/projects/{pid}/lines/{lid}/highlight',
                                   {'level':1,'expected_level':0})
        self.assertEqual(status,403,record)
        self.login_as('editor')
        status,_=self.request('PATCH',f'/api/projects/{pid}/lines/{lid}/highlight',
                               {'level':1,'expected_level':0})
        self.assertEqual(status,200)
        status,_=self.request('PATCH',f'/api/projects/{pid}/lines/{lid}/highlight',
                               {'level':2,'expected_level':0})
        self.assertEqual(status,409)
        for value in (True,3,-1,'1',None):
            with self.subTest(level=value):
                status,_=self.request('PATCH',f'/api/projects/{pid}/lines/{lid}/highlight',
                                       {'level':value,'expected_level':1})
                self.assertEqual(status,400)
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT highlight_level FROM project_lines WHERE id=?',(lid,)).fetchone()[0],1)

    def test_homepage_is_personal_even_for_admin_and_unassigned(self):
        with connect() as conn:
            admin=self.data['admin']
            viewer=self.data['viewer']
            self.assertEqual(teams.effective_homepage(conn,admin['id'],'admin',[],None),'estimator')
            self.assertEqual(accounts.edit_user(conn,admin['id'],{'homepage':'tenders'},admin)['homepage'],'tenders')
            self.assertEqual(accounts.edit_user(conn,admin['id'],{'homepage':'auto'},admin)['homepage'],'estimator')
            teams.set_user_teams(conn,viewer['id'],[])
            self.assertEqual(teams.effective_homepage(conn,viewer['id'],'user',[],None),'tenders')
            self.assertEqual(accounts.edit_user(conn,viewer['id'],{'homepage':'estimator'},viewer)['homepage'],'estimator')
            self.assertEqual(accounts.edit_user(conn,viewer['id'],{'homepage':'auto'},viewer)['homepage'],'tenders')


class HighlightMigrationTests(unittest.TestCase):
    def test_upgrades_v35_records_without_losing_estimate_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'existing.db'
            with patch.dict(os.environ,{'CONEST_DB_PATH':str(path)}):
                with connect() as conn:
                    data=seed(conn)
                    before=calculate_project(conn,data['project_id'])
                    self.assertEqual(conn.execute('SELECT version FROM schema_version').fetchone()[0],CURRENT_SCHEMA)
                # Emulate a genuine schema-35 database without the new column.
                with _raw_connect(path) as conn:
                    conn.execute('ALTER TABLE project_lines DROP COLUMN highlight_level')
                    conn.execute('DELETE FROM app_migrations WHERE name=?',(MIGRATION_KEY,))
                    conn.execute('UPDATE schema_version SET version=35')
                # A restart clears the in-process ready cache before upgrading.
                _ready.pop(str(path.resolve()),None)
                with connect() as conn:
                    after=calculate_project(conn,data['project_id'])
                    self.assertEqual(conn.execute('SELECT version FROM schema_version').fetchone()[0],CURRENT_SCHEMA)
                    self.assertEqual(conn.execute('PRAGMA quick_check').fetchone()[0],'ok')
                    self.assertEqual(after['totals'],before['totals'])
                    self.assertEqual([(x['id'],x['reference_name'],x['quantity']) for x in after['lines']],
                                     [(x['id'],x['reference_name'],x['quantity']) for x in before['lines']])
                    self.assertTrue(all(l['highlight_level']==0 for l in after['lines']))
                backups=list((path.parent/'upgrade_backups').glob(f'{path.stem}-before-schema-{CURRENT_SCHEMA}.db'))
                self.assertEqual(len(backups),1)


if __name__=='__main__':unittest.main()
