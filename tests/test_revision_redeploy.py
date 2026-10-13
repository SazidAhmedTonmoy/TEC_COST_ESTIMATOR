import unittest
from conest_app import productivity, projects
from conest_app.database import connect
import test_http_v232 as previous

class RedeployTests(unittest.TestCase):
    setUp=previous.Http232Tests.setUp
    tearDown=previous.Http232Tests.tearDown
    request=previous.Http232Tests.request
    login_as=previous.Http232Tests.login_as
    # Only these focused HTTP scenarios; reuse setup, not the parent test suite.
    def test_restore_and_safety_copy(self):
        self.login_as('owner'); d=self.data; pid=d['project_id']
        with connect() as c:
            original=projects.calculate_project(c,pid)
            rid=productivity.save_revision(c,pid,d['owner'],{'label':'Restore target'})
        status,changed=self.request('PATCH',f"/api/projects/{pid}/lines/{d['line_id']}",{'quantity':19})
        self.assertEqual(status,200,changed)
        status,result=self.request('POST',f'/api/projects/{pid}/revisions/{rid}/redeploy',{'expected_revision':changed['project']['revision']})
        self.assertEqual(status,200,result)
        with connect() as c:
            restored=projects.calculate_project(c,pid)
            safety=productivity.revision_snapshot(c,pid,result['safety_revision_id'],d['owner'])
            self.assertEqual(restored['totals'],original['totals'])
            self.assertEqual(restored['lines'],original['lines'])
            self.assertEqual(safety['totals'],changed['totals'])
            self.assertGreater(restored['project']['revision'],changed['project']['revision'])
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
        status,result=self.request('POST',f'/api/projects/{pid}/revisions/{rid}/redeploy',{'expected_revision':changed['project']['revision']})
        self.assertEqual(status,409,result)
    def test_readonly_and_missing_version_rejected(self):
        d=self.data;url=f"/api/projects/{d['project_id']}/revisions/{d['revision_id']}/redeploy"
        status,result=self.request('POST',url,{'expected_revision':0});self.assertEqual(status,403,result)
        self.login_as('owner')
        status,result=self.request('POST',url,{});self.assertEqual(status,400,result)

if __name__=='__main__':unittest.main()
