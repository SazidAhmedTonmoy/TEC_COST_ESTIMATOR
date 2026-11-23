"""TEC Flow: release metadata and current documentation."""
import json
import unittest
from pathlib import Path
from conest_app import __version__
from conest_app.help_guide import guide_payload

ROOT=Path(__file__).resolve().parents[1]

class ReleaseIdentityTests(unittest.TestCase):
    def test_versions_and_guide_are_consistent(self):
        self.assertEqual(__version__, '3.8.7')
        pkg=json.loads((ROOT/'tenders_frontend/package.json').read_text())
        lock=json.loads((ROOT/'tenders_frontend/package-lock.json').read_text())
        self.assertEqual(pkg['version'],__version__)
        self.assertEqual(lock['version'],__version__)
        self.assertEqual(lock['packages']['']['version'],__version__)
        self.assertEqual(guide_payload()['version'],__version__)
    def test_documentation_has_current_open_awarded_workflow(self):
        for file in ('README.md','USER_GUIDE.md'):
            body=(ROOT/file).read_text(encoding='utf-8')
            self.assertIn('v3.8',body.lower())
            self.assertIn('Open',body)
        guide=(ROOT/'USER_GUIDE.md').read_text(encoding='utf-8')
        for phrase in ('Add contact person','Add phone','Add email','Calendar','View project'):
            self.assertIn(phrase,guide)
        articles=[x for section in guide_payload()['sections']
                  for x in section['articles'] if x['id']=='open-awarded']
        self.assertEqual(len(articles),1)

if __name__=='__main__':unittest.main()
