"""TEC Flow branding and backwards-compatible technical identifiers."""
import json
import unittest
from pathlib import Path
from conest_app import __version__

ROOT = Path(__file__).resolve().parents[1]

class TECFlowBrandingTests(unittest.TestCase):
    def test_estimator_page_and_brand_message(self):
        html = (ROOT / 'assets/index.html').read_text(encoding='utf-8')
        for phrase in ('TEC Flow', 'Electrical Estimating &amp; Tender Management Platform', 'From Opportunity to Award'):
            self.assertIn(phrase, html)
        self.assertNotIn('TEC EstiDoc', html)

    def test_tender_page_and_source(self):
        html = (ROOT / 'tenders_frontend/index.html').read_text(encoding='utf-8')
        app = (ROOT / 'tenders_frontend/src/components/tender-app.tsx').read_text(encoding='utf-8')
        self.assertIn('TEC Flow', html)
        self.assertIn('From Opportunity to Award', html)
        self.assertIn('TEC Flow', app)
        self.assertNotIn('TEC EstiDoc', app)

    def test_export_branding_and_legacy_import_format(self):
        for file in ('conest_app/exporter.py', 'conest_app/tender_export.py', 'conest_app/project_sharing.py'):
            self.assertIn('TEC Flow', (ROOT / file).read_text(encoding='utf-8'))
        self.assertIn('tec-conest-project', (ROOT / 'conest_app/project_json.py').read_text(encoding='utf-8'))
        self.assertIn('conest_catalog.db', (ROOT / 'conest_app/database.py').read_text(encoding='utf-8'))
        self.assertIn('conest_session', (ROOT / 'conest_app/http_workspace.py').read_text(encoding='utf-8'))

    def test_release_versions(self):
        self.assertEqual(__version__, '3.8.3')
        pkg = json.loads((ROOT/'tenders_frontend/package.json').read_text())
        lock = json.loads((ROOT/'tenders_frontend/package-lock.json').read_text())
        self.assertEqual(pkg['version'], __version__)
        self.assertEqual(lock['version'], __version__)
        self.assertEqual(lock['packages']['']['version'], __version__)

if __name__ == '__main__':
    unittest.main()
