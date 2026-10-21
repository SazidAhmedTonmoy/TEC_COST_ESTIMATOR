"""Review lifecycle, migration, live permissions and shared reminders."""
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import unittest
import test_http_v231 as helpers
from fixtures_v232 import seed
from conest_app import workspace, productivity, auto_upgrade, projects
from conest_app.database import database_path, connect
from legacy_schema_fixture import drop_fixture_columns

class ReviewWorkflowTests(unittest.TestCase):
    request=helpers.HttpPatchTests.request
    setUp=helpers.HttpPatchTests.setUp
    tearDown=helpers.HttpPatchTests.tearDown

    def test_review_round_trip_reminders_and_estimate_unchanged(self):
        deadline=(date.today()+timedelta(days=14)).isoformat()
        with connect() as c:
            f=seed(c);pid=f['project_id'];before=projects.calculate_project(c,pid)
            p=workspace.update_workflow(c,pid,{'status':'in_review','review_deadline':deadline},f['editor'])
            self.assertEqual(p['review_deadline'],deadline)
            self.assertEqual(p['submission_deadline'],before['project']['submission_deadline'])
            self.assertEqual(projects.calculate_project(c,pid)['totals'],before['totals'])
            # Another team can see the review but still cannot edit it.
            other=productivity.reminders(c,f['viewer']);self.assertEqual(len(other),1)
            self.assertEqual(other[0]['kind'],'review');self.assertFalse(other[0]['read'])
            with self.assertRaises(workspace.AccessError):
                workspace.update_workflow(c,pid,{'status':'submitted'},f['viewer'])
            c.execute('INSERT INTO deadline_reads VALUES (?,?,?)',(f['viewer']['id'],other[0]['key'],'2026-09-28'))
            self.assertTrue(productivity.reminders(c,f['viewer'])[0]['read'])
            self.assertFalse(productivity.reminders(c,f['owner'])[0]['read'])
            p=workspace.update_workflow(c,pid,{'status':'submitted'},f['editor'])
            self.assertIsNone(p['review_deadline']);self.assertEqual(productivity.reminders(c,f['viewer']),[])
            self.assertEqual(productivity.reminders(c,f['owner']),[])
            p=workspace.update_workflow(c,pid,{'status':'in_review','review_deadline':deadline},f['owner'])
            self.assertEqual(p['review_cycle'],2)
            again=productivity.reminders(c,f['viewer'])[0]
            self.assertNotEqual(again['key'],other[0]['key']);self.assertFalse(again['read'])
            workspace.update_workflow(c,pid,{'review_deadline':(date.today()-timedelta(days=1)).isoformat()},f['editor'])
            self.assertEqual(productivity.reminders(c,f['viewer'])[0]['stage'],'overdue')
            self.assertEqual(projects.calculate_project(c,pid)['totals'],before['totals'])

    def test_invalid_dates_and_stale_save_are_atomic(self):
        with connect() as c:
            f=seed(c);pid=f['project_id'];original=workspace.get_project(c,pid)
            for deadline in [None,'','2026-02-30',123,True,'2026-1-03']:
                with self.assertRaises(ValueError):
                    workspace.update_workflow(c,pid,{'status':'in_review','review_deadline':deadline},f['owner'])
                self.assertEqual(workspace.get_project(c,pid),original)
            with self.assertRaises(ValueError):workspace.update_workflow(c,pid,{'status':'completed'},f['owner'])
            workspace.update_workflow(c,pid,{'status':'in_review','review_deadline':date.today().isoformat()},f['owner'])
            with self.assertRaises(workspace.AccessError):
                workspace.update_workflow(c,pid,{'status':'submitted','expected_revision':original['revision']},f['owner'])
            self.assertEqual(workspace.get_project(c,pid)['status'],'in_review')

    def test_schema26_upgrade_preserves_records_and_moves_completed_once(self):
        with connect() as c:
            f=seed(c);pid=f['project_id']
            c.execute("UPDATE projects SET status='completed',completed_at='2026-09-20',completed_by=? WHERE id=?",(f['owner']['id'],pid))
            before=projects.calculate_project(c,pid)
            events=c.execute('SELECT COUNT(*) FROM project_activity').fetchone()[0]
            drop_fixture_columns(c,'projects',('review_deadline','review_cycle'))
            c.execute('UPDATE schema_version SET version=26')
            c.execute('DELETE FROM app_migrations WHERE '+ '"'+c.execute('PRAGMA table_info(app_migrations)').fetchone()[1]+'"=?',('v3.0-review-workflow',))
        auto_upgrade._ready.pop(str(database_path()),None)
        with connect() as c:
            p=workspace.get_project(c,pid)
            self.assertEqual(p['status'],'submitted');self.assertIsNone(p['review_deadline'])
            self.assertEqual(p['revision'],before['project']['revision']+1)
            self.assertEqual(p['completed_at'],'2026-09-20')
            self.assertEqual(projects.calculate_project(c,pid)['totals'],before['totals'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM project_activity').fetchone()[0],events)
        snapshot=next((database_path().parent/'upgrade_backups').glob('*before-schema-31.db'))
        with sqlite3.connect(snapshot) as c:
            self.assertEqual(c.execute('SELECT status FROM projects WHERE id=?',(pid,)).fetchone()[0],'completed')
        auto_upgrade._ready.pop(str(database_path()),None)
        with connect() as c:self.assertEqual(workspace.get_project(c,pid)['revision'],p['revision'])
