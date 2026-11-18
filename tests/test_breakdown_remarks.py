"""v3.7.24: Breakdown preserves user-entered estimate item remarks."""
import unittest
from pathlib import Path
from conest_app.estimate_areas import summary

ROOT=Path(__file__).resolve().parents[1]

class BreakdownRemarksTests(unittest.TestCase):
    def test_item_summary_keeps_original_remarks(self):
        lines=[dict(id=1,name_snapshot='Downlights',reference_name='D1',notes='DALI / dimmable',category_key='Lighting',
                    quantity=5,uom='EA',included_in_total=True,area_allocations='[]',total_material=30,total_hours=2,total_labor=20,quoted_total=50)]
        result=summary(lines)
        item=result[0]['items'][0]
        self.assertEqual(item['reference'],'D1')
        self.assertEqual(item['remarks'],'DALI / dimmable')
        self.assertEqual(item['quoted'],50)

    def test_ui_displays_and_searches_remarks(self):
        source=(ROOT/'assets/estimate_areas.js').read_text()
        self.assertIn('x.e.line.notes',source)
        self.assertIn('breakdown-item-remarks',source)
        self.assertIn('Remarks: ${safe(l.notes)}',source)
        self.assertIn('Remarks: ${safe(e.line.notes)}',source)
        shared=(ROOT/'conest_app/project_sharing.py').read_text()
        self.assertIn("item.get('remarks')",shared)

if __name__=='__main__':unittest.main()

# Reuse the existing isolated HTTP fixtures without inheriting their whole suite.
import support_http_access as http_previous

class RevisionPreviewHttpTests(unittest.TestCase):
    setUp=http_previous.Http232Tests.setUp
    tearDown=http_previous.Http232Tests.tearDown
    request=http_previous.Http232Tests.request
    login_as=http_previous.Http232Tests.login_as

    def test_revision_view_is_read_only_and_avoids_comparison(self):
        project_id=self.data['project_id']
        revision_id=self.data['revision_id']
        status,view=self.request('GET',f'/api/projects/{project_id}/revisions/{revision_id}?view=1')
        self.assertEqual(status,200,view)
        self.assertIn('snapshot',view)
        self.assertNotIn('comparison',view)
        status,diff=self.request('GET',f'/api/projects/{project_id}/revisions/{revision_id}?compare=current')
        self.assertEqual(status,200,diff)
        self.assertIn('comparison',diff)
