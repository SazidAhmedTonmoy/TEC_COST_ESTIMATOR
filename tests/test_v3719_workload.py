"""v3.7.19: deterministic team workload and privacy regression checks."""
import unittest
from datetime import date

from conest_app.accounts import AccessError
from conest_app.database import connect
from conest_app.projects import create_project
from conest_app.team_workload import workload
from conest_app.utils import utc_now
from conest_app.workspace import register_project
from fixtures_v232 import seed
from test_http_v231 import HttpPatchTests


class WorkloadHttpTests(unittest.TestCase):
    setUp=HttpPatchTests.setUp
    tearDown=HttpPatchTests.tearDown
    request=HttpPatchTests.request
    def test_member_deadlines_and_read_only_team_scope(self):
        with connect() as conn:
            data=seed(conn)
            owner,editor,viewer=(data[k] for k in ('owner','editor','viewer'))
            pid=data['project_id'];team_id=owner['team_id']
            conn.execute('UPDATE projects SET status=?,submission_deadline=? WHERE id=?',
                         ('in_progress','2026-11-05',pid))
            conn.execute('INSERT INTO project_user_access VALUES (?,?,?,?)',
                         (pid,editor['id'],data['admin']['id'],utc_now()))
            # Another active project is team-visible, but only the admin is its owner;
            # do not credit it as active work for every member.
            shared=create_project(conn,{'name':'Unassigned Team Quote'})['project']
            register_project(conn,shared['id'],data['admin'])
            conn.execute('INSERT INTO project_teams VALUES (?,?,?,?)',
                         (shared['id'],team_id,data['admin']['id'],utc_now()))
            conn.execute('UPDATE projects SET status=?,submission_deadline=? WHERE id=?',
                         ('in_progress','2026-11-09',shared['id']))
            # A review deadline takes priority over the old submission deadline.
            other=create_project(conn,{'name':'Review Needs Action'})['project']
            register_project(conn,other['id'],viewer)
            conn.execute('UPDATE projects SET status=?,review_deadline=?,submission_deadline=? WHERE id=?',
                         ('in_review','2026-11-01','2026-11-05',other['id']))
            before=conn.total_changes
            result=workload(conn,data['admin'],today=date(2026,11,2))
            self.assertEqual(conn.total_changes,before)
            teams={t['id']:t for t in result['teams']}
            self.assertEqual(teams[team_id]['active_estimates'],2)
            self.assertEqual(teams[team_id]['shared_unassigned'],1)
            members={m['id']:m for t in result['teams'] for m in t['members']}
            for person in (owner,editor):
                self.assertEqual(members[person['id']]['active_estimates'],1)
                self.assertEqual(members[person['id']]['upcoming_deadlines'],1)
                self.assertEqual(members[person['id']]['overdue_deadlines'],0)
            self.assertEqual(members[viewer['id']]['upcoming_deadlines'],0)
            self.assertEqual(members[viewer['id']]['overdue_deadlines'],1)
            restricted=workload(conn,owner,today=date(2026,11,2))
            self.assertEqual({t['id'] for t in restricted['teams']},{team_id})
            self.assertNotIn(viewer['id'],{m['id'] for t in restricted['teams'] for m in t['members']})
            conn.execute('UPDATE users SET team_id=NULL WHERE id=?',(viewer['id'],))
            unaffiliated=workload(conn,viewer,today=date(2026,11,2))
            self.assertEqual([m['id'] for t in unaffiliated['teams'] for m in t['members']],[viewer['id']])
            conn.execute('UPDATE users SET is_active=0 WHERE id=?',(owner['id'],))
            with self.assertRaises(AccessError):workload(conn,owner,today=date(2026,11,2))

    def test_previous_personal_endpoint_retired_and_no_schema_change(self):
        status,data=self.request('GET','/api/team-workload')
        self.assertEqual(status,410,data)
        self.assertIn('retired',data['error'])
        self.assertNotIn('teams',data)
        status,health=self.request('GET','/api/health')
        self.assertEqual((status,health['schema_version']),(200,34))
        from conest_app import __version__
        self.assertEqual(health['release'],__version__)


if __name__=='__main__':unittest.main()
