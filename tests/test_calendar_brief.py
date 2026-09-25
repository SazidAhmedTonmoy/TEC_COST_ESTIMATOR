"""Calendar details must not calculate or transfer estimate lines."""
import unittest
from unittest.mock import patch
import test_http_v231 as helpers
from fixtures_v232 import seed

class CalendarBriefTests(unittest.TestCase):
    request=helpers.HttpPatchTests.request
    setUp=helpers.HttpPatchTests.setUp
    tearDown=helpers.HttpPatchTests.tearDown

    def test_brief_is_small_authenticated_and_matches_project(self):
        with helpers.connect() as conn:
            pid=seed(conn)['project_id']
        status,full=self.request('GET',f'/api/projects/{pid}')
        self.assertEqual(status,200,full)
        with patch('conest_app.projects.calculate_project',side_effect=AssertionError('Unexpected full estimate calculation')):
            status,brief=self.request('GET',f'/api/projects/{pid}/brief')
        self.assertEqual(status,200,brief)
        self.assertEqual(brief['project'],full['project'])
        self.assertNotIn('lines',brief)
        self.assertEqual(brief['history']['activity'],self.request('GET',f'/api/projects/{pid}/activity')[1]['activity'])
        self.assertEqual(brief['access']['teams'],self.request('GET',f'/api/projects/{pid}/access-options')[1]['teams'])
        self.cookie=''
        self.assertEqual(self.request('GET',f'/api/projects/{pid}/brief')[0],401)
