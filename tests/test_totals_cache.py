"""Totals remain exact across threads, direct edits and rollback."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import test_http_v231 as helpers
from fixtures_v232 import seed
from conest_app import projects

class TotalsCacheTests(unittest.TestCase):
    request=helpers.HttpPatchTests.request
    setUp=helpers.HttpPatchTests.setUp
    tearDown=helpers.HttpPatchTests.tearDown

    def test_concurrent_reads_share_calculation_and_return_independent_results(self):
        with helpers.connect() as conn:pid=seed(conn)['project_id']
        with projects._totals_lock:projects._totals_cache.clear()
        def read(_):
            with helpers.connect() as conn:
                conn.execute('BEGIN')
                return projects.project_totals(conn,pid)
        with patch.object(projects,'_calculate_rows',wraps=projects._calculate_rows) as calculate:
            with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(read,range(16)))
            self.assertEqual(calculate.call_count,1)
        with helpers.connect() as conn:expected=projects.calculate_project(conn,pid)['totals']
        self.assertTrue(all(r==expected for r in results))
        results[0]['quoted']=-1
        self.assertEqual(read(None),expected)

    def test_direct_edits_and_rollback_cannot_reuse_stale_totals(self):
        with helpers.connect() as conn:pid=seed(conn)['project_id']
        with helpers.connect() as conn:original=projects.project_totals(conn,pid)
        with helpers.connect() as conn:
            conn.execute('BEGIN')
            conn.execute('UPDATE project_line_components SET unit_material=unit_material+17 WHERE project_line_id IN (SELECT id FROM project_lines WHERE project_id=?)',(pid,))
            changed=projects.project_totals(conn,pid)
            self.assertEqual(changed,projects.calculate_project(conn,pid)['totals'])
            self.assertNotEqual(changed,original)
            conn.rollback()
            self.assertEqual(projects.project_totals(conn,pid),original)
            conn.execute('UPDATE projects SET labor_rate=labor_rate+50 WHERE id=?',(pid,))
            self.assertEqual(projects.project_totals(conn,pid),projects.calculate_project(conn,pid)['totals'])
            conn.commit()
        with helpers.connect() as other:
            self.assertEqual(projects.project_totals(other,pid),projects.calculate_project(other,pid)['totals'])
            self.assertNotEqual(projects.project_totals(other,pid),original)
