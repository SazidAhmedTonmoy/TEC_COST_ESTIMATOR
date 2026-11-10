"""v3.7.18 UI contract checks for existing Estimator workflows."""
import json
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class EstimatorUx3718Tests(unittest.TestCase):
    def test_version_and_no_schema_change(self):
        from conest_app import __version__
        self.assertGreaterEqual(tuple(map(int, __version__.split('.'))), (3, 7, 20))
        package=json.loads((ROOT/'tenders_frontend/package.json').read_text())
        self.assertEqual(package['version'],__version__)
        self.assertNotIn('DROP TABLE', (ROOT/'assets/estimator_ux.js').read_text())

    def test_save_status_and_optional_cost_separation(self):
        html=(ROOT/'assets/index.html').read_text()
        js=(ROOT/'assets/app.js').read_text()
        for key in ('estimate-save-state','estimate-optional-total','estimate-included-total','estimate-setup-guide'):
            self.assertIn('id="'+key+'"',html)
        for status in ('saving','saved','dirty','error'):
            self.assertIn("setEstimateSaveState('"+status+"')",js)
        self.assertIn('line.included_in_total===false',js)
        self.assertIn('OPTIONAL COSTS (excluded)',js)
        self.assertIn('INCLUDED QUOTED TOTAL',js)

    def test_breakdown_unallocated_and_reversible_drafts(self):
        js=(ROOT/'assets/estimate_areas.js').read_text()
        for marker in ('data-only-unallocated','breakdown-unallocated-count','data-undo','data-redo','undoStack','redoStack','data-tree-node','saveExpanded','localStorage.setItem'):
            self.assertIn(marker,js)
        self.assertIn("const total=allGroups.reduce",js)
        self.assertIn('expected_revision:project.project.revision',js)
        self.assertNotIn('DROP TABLE',js)

    def test_quick_catalog_and_revision_comparison(self):
        app=(ROOT/'assets/app.js').read_text()
        productivity=(ROOT/'assets/productivity.js').read_text()
        self.assertIn('data-quick-add',app)
        self.assertIn('addCatalogItem(item.id',app)
        self.assertIn('revision-side-by-side',productivity)
        self.assertIn('Item-level differences',productivity)
        self.assertIn('labour hours',productivity.lower())

    def test_compiled_files_referenced_and_have_features(self):
        html=(ROOT/'assets/index.html').read_text()
        assets=re.findall(r'/assets/(app\.[a-f0-9]{12}\.js|styles\.[a-f0-9]{12}\.css)',html)
        self.assertEqual(len(assets),2)
        for name in assets:
            self.assertTrue((ROOT/'assets'/name).exists(),name)
        js=(ROOT/'assets'/next(n for n in assets if n.endswith('.js'))).read_text()
        for feature in ('Show unallocated only','estimate-setup-guide','Item-level differences','suggestion-quick-add'):
            self.assertIn(feature,js)

if __name__=='__main__':
    unittest.main()
