"""v3.7.25: Breakdown activation is persistent and all workspaces use TEC EstiDoc."""
from pathlib import Path
import unittest

from conest_app import projects, estimate_areas
from conest_app.database import connect
import support_http_access as http_fixture

ROOT=Path(__file__).resolve().parents[1]


class BreakdownPersistenceHttpTests(unittest.TestCase):
    setUp=http_fixture.Http232Tests.setUp
    tearDown=http_fixture.Http232Tests.tearDown
    request=http_fixture.Http232Tests.request
    login_as=http_fixture.Http232Tests.login_as

    def test_active_until_explicitly_disabled_and_visible_to_another_account(self):
        pid=self.data['project_id']
        with connect() as conn:
            self.assertFalse(estimate_areas.breakdown_enabled(conn,pid))

        self.login_as('editor')
        code,body=self.request('GET',f'/api/projects/{pid}')
        self.assertEqual(code,200,body)
        code,body=self.request('POST',f'/api/projects/{pid}/breakdown/status',{
            'enabled':True,'expected_revision':body['project']['revision']})
        self.assertEqual(code,200,body)
        self.assertTrue(body['project']['breakdown_enabled'])
        for _ in range(2):
            # Emulates fresh connections/reopening the modal, not a browser-local toggle.
            with connect() as conn:
                self.assertTrue(estimate_areas.breakdown_enabled(conn,pid))
                self.assertTrue(projects.calculate_project(conn,pid)['project']['breakdown_enabled'])

        self.login_as('viewer')
        code,body=self.request('GET',f'/api/projects/{pid}/breakdown/status')
        self.assertEqual(code,200,body)
        self.assertTrue(body['enabled'])
        code,body=self.request('POST',f'/api/projects/{pid}/breakdown/status',{'enabled':False,'expected_revision':1})
        self.assertEqual(code,403,body)
        code,body=self.request('GET',f'/api/projects/{pid}/breakdown/status')
        self.assertTrue(body['enabled'])

        self.login_as('editor')
        code,body=self.request('GET',f'/api/projects/{pid}')
        self.assertTrue(body['project']['breakdown_enabled'])
        code,body=self.request('POST',f'/api/projects/{pid}/breakdown/status',{
            'enabled':False,'expected_revision':body['project']['revision']})
        self.assertEqual(code,200,body)
        self.assertFalse(body['project']['breakdown_enabled'])
        self.login_as('viewer')
        code,body=self.request('GET',f'/api/projects/{pid}/breakdown/status')
        self.assertEqual(code,200,body)
        self.assertFalse(body['enabled'])


class EstiDocBrandAndSearchTests(unittest.TestCase):
    def test_breakdown_search_present_in_both_views_and_does_not_change_allocations(self):
        src=(ROOT/'assets/estimate_areas.js').read_text()
        self.assertIn('data-breakdown-search-toggle',src)
        self.assertIn('data-breakdown-search-input',src)
        self.assertIn("e.line.reference_name,e.line.notes",src)
        self.assertIn("if(unallocatedOnly&&!unallocatedEntry(e)||!matches(e))return",src)
        self.assertIn('data-breakdown-active',src)
        self.assertIn('/breakdown/status',src)
        self.assertNotIn('data-tree-search',src)

    def test_rebrand_without_changing_legacy_data_identifiers(self):
        for file in ('assets/index.html','tenders_web/index.html','assets/app.js',
                     'tenders_frontend/src/components/tender-app.tsx','conest_app/exporter.py',
                     'conest_app/project_sharing.py'):
            text=(ROOT/file).read_text()
            self.assertNotIn('TEC ConEst',text,file)
            self.assertIn('TEC EstiDoc',text,file)
        # Existing exported projects and live database paths must continue to work.
        self.assertIn('tec-conest-project',(ROOT/'conest_app/project_json.py').read_text())
        self.assertIn('conest_catalog.db',(ROOT/'conest_app/database.py').read_text())

if __name__=='__main__': unittest.main()
