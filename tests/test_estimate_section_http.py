"""Section actions use the normal authenticated estimate transport."""
import unittest

import test_http_v232 as previous
from conest_app.database import connect


class EstimateSectionHTTPTests(unittest.TestCase):
    setUp = previous.Http232Tests.setUp
    tearDown = previous.Http232Tests.tearDown
    request = previous.Http232Tests.request
    login_as = previous.Http232Tests.login_as

    def test_inclusion_endpoint_and_concurrent_delta_use_current_settings(self):
        pid=self.data['project_id']
        url=f'/api/projects/{pid}/sections/inclusion'
        self.assertEqual(self.request('POST',url,{'category':'Lighting','included':False,'expected_revision':0})[0],403)
        self.login_as('owner')
        _,before=self.request('GET',f'/api/projects/{pid}')
        known={'_known_lines':{str(line['id']):line['revision'] for line in before['lines']},
               '_known_pricing':[before['project'].get(key,0) for key in
                   ('material_markup','labor_rate','labor_hours_markup','overhead_markup','crew_size','hours_per_day','excluded_categories')]}
        body={'category':'Lighting','included':False,'expected_revision':before['project']['revision'],**known}
        status,after=self.request('POST',url,body)
        self.assertEqual(status,201,after)
        self.assertFalse(after.get('estimate_delta',False))
        self.assertEqual(len(after['lines']),len(before['lines']))
        self.assertTrue(all(not line['included_in_total'] for line in after['lines']))
        self.assertEqual(after['totals']['quoted'],0)
        _,reloaded=self.request('GET',f'/api/projects/{pid}')
        self.assertEqual(reloaded['totals'],after['totals'])
        # Another tab's old pricing fingerprint must not merge stale On flags.
        line=before['lines'][0]
        status,edited=self.request('PATCH',f'/api/projects/{pid}/lines/{line["id"]}',
            {'quantity':line['quantity']+1,'expected_revision':line['revision'],**known})
        self.assertEqual(status,200,edited)
        self.assertFalse(edited.get('estimate_delta',False))
        self.assertTrue(all(not row['included_in_total'] for row in edited['lines']))
        self.assertEqual(edited['totals']['quoted'],0)
        with connect() as conn:
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertTrue(conn.execute("SELECT 1 FROM project_activity WHERE project_id=? AND action='Excluded estimate section'",(pid,)).fetchone())


if __name__ == '__main__':
    unittest.main()
