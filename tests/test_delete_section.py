import unittest
import test_http_v232 as previous
from conest_app.database import connect
class DeleteSectionTests(unittest.TestCase):
    setUp=previous.Http232Tests.setUp
    tearDown=previous.Http232Tests.tearDown
    request=previous.Http232Tests.request
    login_as=previous.Http232Tests.login_as
    def test_scoped_atomic_delete_with_safety_and_access_checks(self):
        pid=self.data['project_id'];url=f'/api/projects/{pid}/sections/remove'
        self.assertEqual(self.request('POST',url,{'category':'Lighting','expected_revision':0})[0],403)
        self.login_as('owner')
        with connect() as c:
            ids=[r[0] for r in c.execute('SELECT id FROM project_lines WHERE project_id=? ORDER BY id',(pid,))]
            c.execute('UPDATE project_lines SET category_snapshot=? WHERE id=?',('Keep',ids[-1]))
            catalog=c.execute('SELECT COUNT(*) FROM catalog_items').fetchone()[0]
        _,before=self.request('GET',f'/api/projects/{pid}')
        category=before['lines'][0]['category_snapshot'];revision=before['project']['revision']
        self.assertEqual(self.request('POST',url,{'category':category,'expected_revision':revision-1})[0],409)
        status,result=self.request('POST',url,{'category':category,'expected_revision':revision});self.assertEqual(status,201,result)
        self.assertTrue(all(l['category_snapshot']!=category for l in result['lines']))
        self.assertTrue(any(l['category_snapshot']=='Keep' for l in result['lines']))
        with connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM catalog_items').fetchone()[0],catalog)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertTrue(c.execute("SELECT 1 FROM tender_revisions WHERE project_id=? AND label LIKE 'Before section deletion%'",(pid,)).fetchone())
        self.assertLess(result['totals']['quoted'],before['totals']['quoted'])
if __name__=='__main__':unittest.main()
