"""Desktop and mobile workspace navigation must be unmistakable and accessible."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]

class WorkspaceTabs379Tests(unittest.TestCase):
    def test_estimator_source_and_compiled_has_tabs(self):
        source=(ROOT/'assets/workspace_switch.js').read_text()
        self.assertIn("tabs.className='workspace-tabs'",source)
        self.assertIn("tabs.setAttribute('aria-label','Switch workspace')",source)
        self.assertIn("['Estimator','/',!inTenders]",source)
        self.assertIn("['Tenders','/tenders/',inTenders]",source)
        self.assertIn("tab.className='workspace-tab'+(active?' is-active':' workspace-swap')",source)
        self.assertNotIn('swap.innerHTML',source)
        html=(ROOT/'assets/index.html').read_text()
        match=re.search(r'/assets/(app\.[a-f0-9]{12}\.js)',html)
        self.assertIsNotNone(match)
        self.assertIn('workspace-tabs',(ROOT/'assets'/match.group(1)).read_text())

    def test_estimator_mobile_tabs_are_visible_with_drawer_closed(self):
        css=(ROOT/'assets/styles.css').read_text()
        mobile=(ROOT/'assets/mobile-v3512.css').read_text()
        for token in ('nav.workspace-tabs','.workspace-tab','grid-template-columns:repeat(2,minmax(0,1fr))'):
            self.assertIn(token,css)
        self.assertIn('sidebar:not(.menu-open) .workspace-tabs',mobile)
        self.assertIn('sidebar.menu-open nav.workspace-tabs',mobile)

    def test_tender_source_has_two_tabs_on_both_headers(self):
        source=(ROOT/'tenders_frontend/src/components/tender-app.tsx').read_text()
        self.assertIn('function WorkspaceTabs()',source)
        self.assertIn('className="workspace-tab workspace-swap"',source)
        self.assertIn('href="/tenders/" aria-current="page"',source)
        self.assertIn('aria-label="Switch workspace"',source)
        self.assertGreaterEqual(source.count('<WorkspaceTabs/>'),2)
        self.assertNotIn('<RefreshCw/></a>',source)
        css=(ROOT/'tenders_frontend/src/globals.css').read_text()
        for token in ('.workspace-tabs .workspace-tab.is-active','.mobile-brand-bar .conest-brand','min-height:42px'):
            self.assertIn(token,css)

    def test_tender_compiled_entry_provides_tabs(self):
        html=(ROOT/'tenders_web/index.html').read_text()
        match=re.search(r'<script\b[^>]*\bsrc="/tenders/assets/([^"?]+\.js)"',html)
        self.assertIsNotNone(match)
        path=ROOT/'tenders_web/assets'/match.group(1)
        self.assertTrue(path.is_file())
        entry=path.read_text()
        self.assertIn('workspace-tabs',entry)
        self.assertIn('Switch to Estimator',entry)
        self.assertIn('aria-current',entry)
        self.assertIn('Tenders',entry)

if __name__=='__main__':unittest.main()
