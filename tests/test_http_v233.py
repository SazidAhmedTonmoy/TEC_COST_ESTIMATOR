"""HTTP authorization tests for owner management, direct editing and import info."""
import unittest
import test_http_v232 as previous
import test_http_v231 as http_helpers
from conest_app.database import connect
from conest_app import workspace
from test_v231 import workbook_bytes


class Http233Tests(unittest.TestCase):
    setUp=previous.Http232Tests.setUp
    tearDown=previous.Http232Tests.tearDown
    request=previous.Http232Tests.request
    login_as=previous.Http232Tests.login_as
    upload=http_helpers.HttpPatchTests.upload

    def test_owner_can_assign_teams_and_individuals_but_not_administer_accounts(self):
        self.login_as('owner');pid=self.data['project_id']
        status,options=self.request('GET',f'/api/projects/{pid}/access-options')
        self.assertEqual(status,200,options);self.assertEqual(len(options['teams']),2)
        self.assertIn(self.data['viewer']['id'],[u['id'] for u in options['users']])
        status,error=self.request('GET','/api/users');self.assertEqual(status,403,error)
        status,result=self.request('PATCH',f'/api/projects/{pid}/workflow',{'team_ids':[self.data['teams'][1]],'user_ids':[self.data['editor']['id']]})
        self.assertEqual(status,200,result);self.assertTrue(result['project']['can_manage'])
        self.assertEqual([u['id'] for u in result['project']['individual_users']],[self.data['editor']['id']])
        status,error=self.request('POST','/api/teams',{'name':'Cannot create a team'});self.assertEqual(status,403,error)

    def test_grant_and_revoke_apply_to_existing_session_on_next_write(self):
        pid=self.data['project_id'];lid=self.data['line_id']
        viewer_cookie,viewer_csrf=self.cookie,self.csrf
        self.login_as('owner');owner_cookie,owner_csrf=self.cookie,self.csrf
        status,result=self.request('PATCH',f'/api/projects/{pid}/workflow',{'user_ids':[self.data['viewer']['id']]})
        self.assertEqual(status,200,result)
        self.cookie,self.csrf=viewer_cookie,viewer_csrf
        status,result=self.request('PATCH',f'/api/projects/{pid}/lines/{lid}',{'quantity':11})
        self.assertEqual(status,200,result)
        for method,suffix,body in [('GET','/access-options',None),('PATCH','/workflow',{'user_ids':[]}),('DELETE','',{})]:
            status,error=self.request(method,f'/api/projects/{pid}'+suffix,body);self.assertEqual(status,403,error)
        self.cookie,self.csrf=owner_cookie,owner_csrf
        status,result=self.request('PATCH',f'/api/projects/{pid}/workflow',{'user_ids':[]});self.assertEqual(status,200,result)
        self.cookie,self.csrf=viewer_cookie,viewer_csrf
        status,error=self.request('PATCH',f'/api/projects/{pid}/lines/{lid}',{'quantity':12});self.assertEqual(status,403,error)
        status,result=self.request('GET',f'/api/projects/{pid}');self.assertEqual(status,200,result);self.assertFalse(result['project']['can_edit'])
        self.assertEqual(next(l['quantity'] for l in result['lines'] if l['id']==lid),11)

    def test_owner_deletes_project_after_removing_team_access(self):
        self.login_as('owner');pid=self.data['project_id']
        status,result=self.request('PATCH',f'/api/projects/{pid}/workflow',{'team_ids':[],'user_ids':[]})
        self.assertEqual(status,200,result);self.assertTrue(result['project']['can_delete'])
        status,result=self.request('DELETE',f'/api/projects/{pid}',{'expected_revision':result['project']['revision']})
        self.assertEqual(status,200,result)
        with connect() as c:
            self.assertFalse(c.execute('SELECT 1 FROM projects WHERE id=?',(pid,)).fetchone())
            self.assertTrue(c.execute('SELECT 1 FROM catalog_items WHERE id=?',(self.data['catalog_id'],)).fetchone())

    def test_access_changes_require_csrf_and_current_revision(self):
        self.login_as('owner');pid=self.data['project_id']
        status,error=self.request('PATCH',f'/api/projects/{pid}/workflow',{'user_ids':[self.data['viewer']['id']]},csrf=False)
        self.assertEqual(status,403,error)
        status,error=self.request('PATCH',f'/api/projects/{pid}/workflow',{'user_ids':[self.data['viewer']['id']],'expected_revision':-1})
        self.assertEqual(status,409,error)
        with connect() as c:self.assertFalse(c.execute('SELECT 1 FROM project_user_access').fetchone())

    def test_real_quotation_import_is_in_searchable_personal_history(self):
        status,preview=self.upload('actual-upload.xlsx',workbook_bytes(reference='TEST-233-HTTP'))
        self.assertEqual(status,200,preview)
        status,result=self.request('POST','/api/light-prices/import',{'preview_id':preview['preview_id'],'selected':['0']})
        self.assertEqual(status,200,result)
        status,history=self.request('GET','/api/import-history?kind=lighting&who=me&q=TEST-233-HTTP')
        self.assertEqual(status,200,history);self.assertEqual(history['total'],1)
        self.assertEqual(history['uploads'][0]['filename'],'actual-upload.xlsx')
        self.assertEqual(history['uploads'][0]['uploader_name'],self.data['viewer']['name'])
        self.login_as('owner')
        status,history=self.request('GET','/api/import-history?who=me&q=actual-upload')
        self.assertEqual(history['total'],0)
        status,history=self.request('GET','/api/import-history?who=all&q=actual-upload');self.assertEqual(history['total'],1)

    def test_history_and_directory_require_authentication(self):
        status,result=self.request('GET','/api/import-history?limit=-1');self.assertEqual(status,400,result)
        self.cookie='';self.csrf=''
        for path in ('/api/import-history',f"/api/projects/{self.data['project_id']}/access-options"):
            status,result=self.request('GET',path);self.assertEqual(status,401,result)

if __name__=='__main__':unittest.main()
