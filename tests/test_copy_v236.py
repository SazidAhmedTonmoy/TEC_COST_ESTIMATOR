import unittest
from datetime import date,timedelta
import test_http_v232 as previous
from conest_app.database import connect
from conest_app.projects import calculate_project

class Copy236Tests(unittest.TestCase):
    setUp=previous.Http232Tests.setUp
    tearDown=previous.Http232Tests.tearDown
    request=previous.Http232Tests.request
    login_as=previous.Http232Tests.login_as
    def test_old_project_copy_accepts_new_details_and_preserves_estimate(self):
        pid=self.data['project_id']
        with connect() as c:
            c.execute('UPDATE projects SET submission_deadline=? WHERE id=?',('2020-01-01',pid))
            original=calculate_project(c,pid)
        deadline=str(date.today()+timedelta(days=14))
        status,result=self.request('POST',f'/api/projects/{pid}/copy',{'name':'New tender','scope_of_work':'New scope','builders':['Builder A','Builder B'],'submission_deadline':deadline})
        self.assertEqual(status,201,result)
        p=result['project'];self.assertEqual(p['name'],'New tender');self.assertEqual(p['scope_of_work'],'New scope')
        self.assertEqual(p['builders'],['Builder A','Builder B']);self.assertEqual(p['submission_deadline'],deadline)
        with connect() as c:
            copied=calculate_project(c,p['id'])
            self.assertEqual(copied['totals'],original['totals'])
            self.assertEqual(len(copied['lines']),len(original['lines']))
            self.assertEqual(calculate_project(c,pid),original)
        status,result=self.request('POST',f'/api/projects/{pid}/copy',{'name':'Undated copy'})
        self.assertEqual(status,201,result);self.assertFalse(result['project']['submission_deadline'])
        status,result=self.request('POST',f'/api/projects/{pid}/copy',{'name':'Invalid copy','submission_deadline':'2020-01-01'})
        self.assertEqual(status,400,result)
