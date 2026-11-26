import unittest
import support_http as support


class GuideHTTPTests(unittest.TestCase):
    setUp=support.HttpPatchTests.setUp
    tearDown=support.HttpPatchTests.tearDown
    request=support.HttpPatchTests.request

    def test_guide_is_comprehensive_and_authenticated(self):
        status,payload=self.request('GET','/api/help/guide')
        self.assertEqual(status,200,payload)
        topics=[entry['id'] for group in payload['sections'] for entry in group['articles']]
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
        for path in ('/api/assistant/chat', '/api/assistant/document', '/api/assistant/action', '/api/settings/test-llm'):
            self.assertEqual(self.request('POST', path, {})[0], 404)

if __name__=='__main__':unittest.main()
