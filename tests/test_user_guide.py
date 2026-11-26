import unittest
import tempfile
from pathlib import Path

from tools.cleanup_retired_ai import RETIRED_FILES, retired_paths, remove_retired
import support_http as support


class GuideHTTPTests(unittest.TestCase):
    setUp=support.HttpPatchTests.setUp
    tearDown=support.HttpPatchTests.tearDown
    request=support.HttpPatchTests.request

    def test_guide_is_comprehensive_and_authenticated(self):
        status,payload=self.request('GET','/api/help/guide')
        self.assertEqual(status,200,payload)
        topics=[entry['id'] for group in payload['sections'] for entry in group['articles']]
        self.assertEqual(len(topics), 38)
        self.assertEqual(len(set(topics)), len(topics))
        for name in ['breakdown','revisions','estimate-export','opportunities','analytics','chase-up','users-teams','first-estimate','first-follow-up']:
            self.assertIn(name,topics)
        self.cookie='';self.csrf=''
        self.assertEqual(self.request('GET','/api/help/guide')[0],401)

    def test_quantity_search_and_clipboard_still_work(self):
        status, result = self.request('POST', '/api/catalog/match', {'text': '12 x downlight'})
        self.assertEqual((status, result['query'], result['quantity']), (200, 'downlight', 12))
        copied = {'name': 'D1', 'quantity': 12}
        self.assertEqual(self.request('POST', '/api/clipboard', {'component': copied})[0], 200)
        self.assertEqual(self.request('GET', '/api/clipboard')[1]['component'], copied)

    def test_retired_post_routes(self):
        self.assertEqual(self.request('GET', '/api/assistant/guide')[0], 404)
        for path in ('/api/assistant/chat', '/api/assistant/document', '/api/assistant/action', '/api/settings/test-llm'):
            self.assertEqual(self.request('POST', path, {})[0], 404)

class RetiredAICleanupTests(unittest.TestCase):
    def test_cleanup_is_targeted_and_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            protected = ('assets/user_guide.js', 'tests/test_user_guide.py',
                         'data/conest_catalog.db', 'data/tec_tenders.db',
                         '.env', 'passenger_wsgi.py', 'tests/test_release.py',
                         'assets/app.e749cf0581db.js', 'data/LOCAL_TESTING.md')
            for name in (*RETIRED_FILES, *protected):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name, encoding='utf-8')
            self.assertEqual(retired_paths(root), list(RETIRED_FILES))
            self.assertEqual(remove_retired(root), list(RETIRED_FILES))
            self.assertEqual(retired_paths(root), [])
            self.assertEqual(remove_retired(root), [])
            for name in protected:
                self.assertEqual((root / name).read_text(encoding='utf-8'), name)

    def test_cleanup_requires_replacement_guide(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = root / 'tests/test_help_assistant.py'
            old.parent.mkdir()
            old.write_text('old test', encoding='utf-8')
            with self.assertRaises(ValueError):
                remove_retired(root)
            self.assertTrue(old.exists())


if __name__=='__main__':unittest.main()
