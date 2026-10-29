"""3.5.12 regression: compiled mobile behaviour and source/build parity."""
from pathlib import Path
import unittest
import json

from conest_app import __version__
from tools.check_tender_css import served_mobile_css

ROOT=Path(__file__).resolve().parents[1]

class Mobile3512Tests(unittest.TestCase):
    def test_release_and_html_assets(self):
        package=json.loads((ROOT/'tenders_frontend/package.json').read_text())
        self.assertEqual(__version__, package['version'])
        self.assertGreaterEqual(tuple(int(part) for part in __version__.split('.')), (3,5,12))
        html=(ROOT/'assets/index.html').read_text()
        self.assertIn('estimator-menu-backdrop',html)
        self.assertIn('/assets/mobile-v3512.css?v=3.5.12',html)
        tender=(ROOT/'tenders_web/index.html').read_text()
        # Either the prebuilt direct stylesheet or Vite's hashed CSS is valid.
        import re
        self.assertRegex(tender,r'<link\b[^>]*href="/tenders/assets/[^"?]+\.css(?:\?[^"]*)?"')

    def test_login_float_guard(self):
        css=(ROOT/'assets/mobile-v3512.css').read_text()
        self.assertIn('body:has(#login-screen:not(.hidden))',css)
        self.assertIn('#toggle-all-categories',css)
        self.assertIn('body:not(:has(#estimate-view.active))',css)

    def test_estimator_drawer_script_in_compiled_bundle(self):
        source=(ROOT/'assets/mobile.js').read_text()
        import re
        html=(ROOT/'assets/index.html').read_text()
        match=re.search(r'/assets/(app\.[a-f0-9]{12}\.js)',html)
        self.assertIsNotNone(match)
        compiled=(ROOT/'assets'/match.group(1)).read_text()
        self.assertIn('estimator-menu-backdrop',source)
        self.assertIn('estimator-menu-backdrop',compiled)
        for fragment in ('Escape','hashchange','mobile.addEventListener',"aria-expanded"):
            self.assertIn(fragment,source)
        css=(ROOT/'assets/mobile-v3512.css').read_text()
        self.assertIn('.app-shell > .sidebar.menu-open',css)
        self.assertIn('grid-template-columns:none!important',css)

    def test_tender_kpi_grid_matches_served_asset(self):
        source=(ROOT/'tenders_frontend/src/mobile-v3512.css').read_text()
        self.assertIn('grid-template-columns:repeat(2,minmax(0,1fr))',source.replace(' ',''))
        self.assertIn('overflow:visible!important',source)
        self.assertIn('mobile-v3512.css',(ROOT/'tenders_frontend/src/main.tsx').read_text())
        # Vite emits a fingerprinted CSS bundle, not a stable mobile-v3512.css.
        # The actual HTML stylesheet must include the required mobile rules.
        served_mobile_css(
            ROOT,
            'grid-template-columns:repeat(2,minmax(0,1fr))!important',
            'overflow:visible!important',
            'scroll-snap-type:none!important',
        )
