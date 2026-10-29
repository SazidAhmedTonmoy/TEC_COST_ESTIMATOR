"""v3.7.7: route, creator, form layout and asset consistency regressions."""
from pathlib import Path
import json
import re
import shutil
import subprocess
import unittest
from urllib.parse import parse_qs, urlparse

from conest_app import __version__

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / 'tenders_frontend' / 'src'
FORM = (FRONT / 'components' / 'opportunities.tsx').read_text(encoding='utf-8')
HTML = (ROOT / 'tenders_web' / 'index.html').read_text(encoding='utf-8')


class Opportunity377Tests(unittest.TestCase):
    def test_release_matches_package_and_mobile_regression_is_not_version_pinned(self):
        package = json.loads((ROOT / 'tenders_frontend' / 'package.json').read_text())
        self.assertEqual(__version__, package['version'])
        self.assertGreaterEqual(tuple(map(int, __version__.split('.'))), (3, 7, 7))
        regression = (ROOT / 'tests' / 'test_v3512_mobile.py').read_text()
        self.assertIn("package['version']", regression)
        self.assertNotIn('self.assertEqual(__version__, "3.7.5")', regression)

    def test_form_field_swap_preserves_region_mapping(self):
        text = FORM.split('<Dialog open={!!form}', 1)[1]
        fields = ['Project name', 'Added date', 'Closing deadline', 'Project location',
                  'Working scope', 'Estimated tender value (AUD)', 'Region', 'Distance (km)']
        offsets = [text.index('>' + field + '<') for field in fields]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn("distanceOrigin:existing?.origin||''", text)
        self.assertIn('value={form.addedDate}', text)
        self.assertIn('value={form.region}', text)

    def test_card_credits_creator_and_clicks_location_only_when_present(self):
        cards = FORM.split('className="op-cards"', 1)[1].split('className="op-pagination"', 1)[0]
        self.assertIn('Created by <strong>{item.createdByName', cards)
        self.assertIn('item.location?.trim()?', cards)
        self.assertIn('className="op-card-route"', cards)
        self.assertIn('rel="noopener noreferrer"', cards)
        self.assertIn('aria-label={\'View route to \'+item.location}', cards)
        self.assertIn('Location to be confirmed', cards)
        self.assertIn('opportunityRouteUrl(item,regions)', cards)
        self.assertIn('opportunityRouteUrl(selected,regions)', FORM)

    def test_served_assets_exist_and_include_route_and_creator(self):
        match = re.search(r'src="(/tenders/assets/[^"?]+\.js)"', HTML)
        self.assertIsNotNone(match)
        main = ROOT / match.group(1).replace('/tenders/assets/', 'tenders_web/assets/', 1)
        self.assertTrue(main.is_file(), str(main))
        css = re.search(r'href="(/tenders/assets/[^"?]+\.css)"', HTML)
        self.assertIsNotNone(css)
        self.assertTrue((ROOT / css.group(1).replace('/tenders/assets/', 'tenders_web/assets/', 1)).is_file())
        # Both the distributed module and a fresh Vite build are supported.
        modules = list((ROOT / 'tenders_web' / 'assets').glob('opportunities-*.js'))
        self.assertTrue(modules)
        self.assertTrue(any('Created by' in p.read_text() and 'View route to' in p.read_text()
                            for p in modules))

    @unittest.skipUnless(shutil.which('node'), 'Node is required to exercise TypeScript URL helper')
    def test_directions_url_uses_region_and_nominated_origins(self):
        script = """import {opportunityRouteUrl} from './tenders_frontend/src/lib/opportunity-display.ts';
const regions=[{code:'VIC',origin:'CBD, Melbourne'},{code:'NSW',origin:'Silverwater, NSW'}];
const cases=[
  {location:'101 Collins St, Melbourne VIC',region:'VIC',distanceOrigin:''},
  {location:'Martin Place, Sydney',region:'NSW',distanceOrigin:'Parramatta Road, NSW'},
  {location:'',region:'NSW',distanceOrigin:''}
];
for(const item of cases)console.log(opportunityRouteUrl(item,regions));"""
        result = subprocess.run(['node', '--experimental-strip-types', '--input-type=module', '-e', script],
                                cwd=ROOT, capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stderr)
        items = result.stdout.splitlines()
        self.assertEqual(len(items), 3)
        self.assertEqual(parse_qs(urlparse(items[0]).query)['origin'], ['CBD, Melbourne'])
        self.assertEqual(parse_qs(urlparse(items[1]).query)['origin'], ['Parramatta Road, NSW'])
        self.assertEqual(parse_qs(urlparse(items[0]).query)['destination'], ['101 Collins St, Melbourne VIC'])
        self.assertEqual(parse_qs(urlparse(items[1]).query)['destination'], ['Martin Place, Sydney'])
        self.assertEqual(items[2], '')


if __name__ == '__main__':
    unittest.main()
