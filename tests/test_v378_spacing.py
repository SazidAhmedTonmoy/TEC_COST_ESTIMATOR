"""v3.7.8 opportunity pagination and consistent spacing asset checks."""
import unittest
import re
import json
from pathlib import Path
from tools.check_tender_css import served_mobile_css

ROOT = Path(__file__).resolve().parents[1]


class Layout378Tests(unittest.TestCase):
    def test_18_item_page_request_and_navigation(self):
        src = (ROOT / 'tenders_frontend/src/components/opportunities.tsx').read_text()
        html = (ROOT / 'tenders_web/index.html').read_text()
        # A GitHub Vite build renames chunks and may fold JS constants.
        # Find the *served* entry and its lazy opportunity chunk instead of
        # requiring the hand-packaged v378 filenames or a minifier spelling.
        main_match = re.search(r'<script\b[^>]*\bsrc="/tenders/assets/([^"?]+\.js)"', html)
        self.assertIsNotNone(main_match, 'No served Tender entry script')
        main_path = ROOT / 'tenders_web/assets' / main_match.group(1)
        self.assertTrue(main_path.is_file(), str(main_path))
        main = main_path.read_text()
        chunks = re.findall(r'opportunities[-\w.]+\.js', main)
        self.assertTrue(chunks, 'Built Tender entry has no opportunity chunk')
        for chunk in chunks:
            path = ROOT / 'tenders_web/assets' / chunk
            self.assertTrue(path.is_file(), f'Lazy opportunity chunk is missing: {chunk}')
        bundle = '\n'.join((ROOT / 'tenders_web/assets' / chunk).read_text() for chunk in chunks)
        self.assertIn('const OPPORTUNITY_PAGE_SIZE = 18;', src)
        self.assertIn('pageSize:String(OPPORTUNITY_PAGE_SIZE)', src)
        for expression in ['Math.ceil(data.total/OPPORTUNITY_PAGE_SIZE)',
                           'Math.ceil((result?.total||0)/OPPORTUNITY_PAGE_SIZE)',
                           '(currentPage-1)*OPPORTUNITY_PAGE_SIZE+1',
                           'Math.min(currentPage*OPPORTUNITY_PAGE_SIZE,result!.total)']:
            self.assertIn(expression, src)
        # Vite may fold the constant into an identifier (pageSize:String(N)).
        # The API/SQLite integration test below enforces the real value 18.
        self.assertIn('pageSize',bundle)
        self.assertNotRegex(bundle, r'pageSize\s*:\s*[`\"\']20[`\"\']')

    def test_backend_pagination_default_and_explicit_sizes(self):
        source = (ROOT / 'conest_app/opportunities.py').read_text()
        self.assertIn("size = _page(filters.get('pageSize'), 18, 100)", source)
        # Does not change notification pagination.
        self.assertIn("size = _page(filters.get('pageSize'), 30, 100)", source)

    def test_spacing_ship_for_both_workspaces(self):
        source = (ROOT / 'tenders_frontend/src/tender-v35.css').read_text()
        # Vite merges/minifies CSS, so check selectors in the actual served
        # stylesheet(s), not specific hand-built file names or declaration order.
        compiled = served_mobile_css(ROOT,'.op-card-meta','.op-card-footer','.tender-table')
        self.assertIn('3.7.8 - shared spacing rhythm', source)
        for token in ['.op-card-meta', '.op-card-footer', '.tender-table']:
            self.assertIn(token, source)
            self.assertIn(token, compiled)
        estimator = (ROOT / 'assets/spacing-v378.css').read_text()
        self.assertIn('.app-shell:not(.hidden)', estimator)
        self.assertIn('assets/spacing-v378.css?v=3.7.8', (ROOT / 'assets/index.html').read_text())

    def test_no_schema_reset(self):
        from conest_app import __version__
        self.assertGreaterEqual(tuple(map(int,__version__.split('.'))), (3,7,8))
        package = json.loads((ROOT / 'tenders_frontend/package.json').read_text())
        self.assertEqual(__version__, package['version'])


if __name__ == '__main__':
    unittest.main()

class Pagination378IntegrationTests(unittest.TestCase):
    """Real SQLite-backed 18/18/1 page boundaries, no lost or repeated projects."""
    from tests.test_opportunities import OpportunityTests as _Fixture
    setUp = _Fixture.setUp
    tearDown = _Fixture.tearDown
    make_user = staticmethod(_Fixture.make_user)
    create = _Fixture.create

    def test_server_pages_cover_every_opportunity_once(self):
        from conest_app import opportunities as op
        for index in range(37):
            self.create(project='Pagination test %02d' % index)
        pages = [op.list_opportunities(self.store, {'page': page, 'sort': 'name'}, self.admin)
                 for page in (1, 2, 3)]
        self.assertEqual([len(item['items']) for item in pages], [18, 18, 1])
        self.assertEqual([item['pageSize'] for item in pages], [18, 18, 18])
        self.assertEqual([item['total'] for item in pages], [37, 37, 37])
        identifiers = [item['id'] for group in pages for item in group['items']]
        self.assertEqual(len(set(identifiers)), 37)
        explicit = op.list_opportunities(self.store, {'pageSize': 5, 'page': 2}, self.admin)
        self.assertEqual(len(explicit['items']), 5)
        self.assertEqual(explicit['pageSize'], 5)
