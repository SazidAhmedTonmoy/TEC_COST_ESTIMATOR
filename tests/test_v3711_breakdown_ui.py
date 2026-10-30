"""Regression: project Breakdown is the only area allocation editor."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BreakdownOnlyUiTests(unittest.TestCase):
    def test_item_button_and_legacy_dialog_are_removed(self):
        source = (ROOT / 'assets/app.js').read_text()
        allocation_ui = (ROOT / 'assets/estimate_areas.js').read_text()
        self.assertNotIn('class="text-button area-allocate"', source)
        self.assertNotIn("closest('.area-allocate')", allocation_ui)
        self.assertNotIn('<h2>Areas / floors</h2>', allocation_ui)
        self.assertIn('Edit area quantities using the project Breakdown button', source)
        self.assertIn('data-breakdown="${project.id}"', (ROOT / 'assets/workspace.js').read_text())
        self.assertIn("closest('[data-breakdown]')", allocation_ui)
        self.assertIn('data-add-breakdown', allocation_ui)
        self.assertIn('data-total=', allocation_ui)
        self.assertIn('rows:entries.map(e=>', allocation_ui)
        self.assertIn('/breakdown', allocation_ui)
        self.assertIn('area_allocations', allocation_ui)

    def test_compiled_bundle_has_current_ui_and_is_loaded(self):
        html = (ROOT / 'assets/index.html').read_text()
        match = re.search(r'src="/assets/(app\.[0-9a-f]{12}\.js)"', html)
        self.assertIsNotNone(match)
        bundle = (ROOT / 'assets' / match.group(1)).read_text()
        self.assertNotIn('class="text-button area-allocate"', bundle)
        self.assertNotIn("closest('.area-allocate')", bundle)
        self.assertIn("closest('[data-breakdown]')", bundle)
        self.assertIn('Edit area quantities using the project Breakdown button', bundle)


if __name__ == '__main__':
    unittest.main()
