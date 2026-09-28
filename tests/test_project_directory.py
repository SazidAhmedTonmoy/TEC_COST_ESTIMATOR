"""List metadata batching preserves user access and attribution."""
import unittest
from concurrent.futures import ThreadPoolExecutor
import test_http_v231 as helpers
from fixtures_v232 import seed
from conest_app import workspace, projects
from conest_app.utils import utc_now

class ProjectDirectoryTests(unittest.TestCase):
    request = helpers.HttpPatchTests.request
    setUp = helpers.HttpPatchTests.setUp
    tearDown = helpers.HttpPatchTests.tearDown

    def test_batch_matches_individual_and_reduces_queries(self):
        with helpers.connect() as conn:
            f = seed(conn)
            for i in range(9):
                pid = projects.create_project(conn, {'name': f'Board project {i}'})['project']['id']
                workspace.register_project(conn, pid, f['owner'])
                workspace.record_activity(conn, pid, f['editor'], 'Added project note', 'Review')
            conn.execute('INSERT INTO project_user_access VALUES (?,?,?,?)',
                         (f['project_id'], f['viewer']['id'], f['admin']['id'], utc_now()))
            for actor in (f['admin'], f['owner'], f['editor'], f['viewer']):
                queries = []
                conn.set_trace_callback(queries.append)
                actual = workspace.visible_projects(conn, actor, include_totals=False)
                batch_count = len(queries)
                queries.clear()
                expected = [workspace.decorate_project(conn, row, actor) for row in
                            conn.execute('SELECT * FROM projects ORDER BY updated_at DESC,id DESC')]
                individual_count = len(queries)
                conn.set_trace_callback(None)
                self.assertEqual(actual, expected)
                self.assertLess(batch_count, individual_count * .5)
            # A list request must pick up both membership and name changes immediately.
            conn.execute('UPDATE users SET team_id=NULL,name=? WHERE id=?', ('Updated editor', f['editor']['id']))
            rows = workspace.visible_projects(conn, f['editor'], include_totals=False)
            self.assertFalse(any(p['can_edit'] for p in rows))
            self.assertTrue(any(c['name'] == 'Updated editor' for p in rows for c in p['contributors']))
            conn.execute('UPDATE users SET is_active=0 WHERE id=?', (f['viewer']['id'],))
            with self.assertRaises(workspace.AccessError):
                workspace.visible_projects(conn, f['viewer'], include_totals=False)

    def test_concurrent_accounts_keep_their_own_access(self):
        with helpers.connect() as conn:
            f = seed(conn)
        actors = [f['admin'], f['owner'], f['editor'], f['viewer']] * 4
        def read(actor):
            with helpers.connect() as conn:
                conn.execute('BEGIN')
                row = next(p for p in workspace.visible_projects(conn, actor) if p['id'] == f['project_id'])
                self.assertEqual(row['can_edit'], actor['id'] != f['viewer']['id'])
                return row['totals']
        with ThreadPoolExecutor(max_workers=8) as pool:
            totals = list(pool.map(read, actors))
        self.assertTrue(all(t == totals[0] for t in totals))
