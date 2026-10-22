"""3.5.12 regression: compiled mobile behaviour and source/build parity."""
from pathlib import Path
import unittest

from conest_app import __version__

ROOT=Path(__file__).resolve().parents[1]

class Mobile3512Tests(unittest.TestCase):
    def test_release_and_html_assets(self):
        self.assertEqual(__version__, "3.5.12")
        html=(ROOT/'assets/index.html').read_text()
        self.assertIn('estimator-menu-backdrop',html)
        self.assertIn('/assets/mobile-v3512.css?v=3.5.12',html)
        tender=(ROOT/'tenders_web/index.html').read_text()
        self.assertIn('/tenders/assets/mobile-v3512.css?v=3.5.12',tender)

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
        source=(ROOT/'tenders_frontend/src/mobile-v3512.css').read_bytes()
        deployed=(ROOT/'tenders_web/assets/mobile-v3512.css').read_bytes()
        self.assertEqual(source,deployed)
        self.assertIn(b'grid-template-columns:repeat(2,minmax(0,1fr))',deployed)
        self.assertIn(b'overflow:visible!important',deployed)
        self.assertIn('mobile-v3512.css',(ROOT/'tenders_frontend/src/main.tsx').read_text())
