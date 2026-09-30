"""Real local HTTP checks for company-wide read access and immutable viewing."""
import unittest
from conest_app import accounts, workspace, project_notes, productivity
from conest_app.database import connect
from conest_app.projects import calculate_project
import test_http_v231 as previous_http
from fixtures_v232 import seed, PASSWORD
from test_v232 import image_url


class Http232Tests(unittest.TestCase):
    request=previous_http.HttpPatchTests.request
    tearDown=previous_http.HttpPatchTests.tearDown

    def setUp(self):
        previous_http.HttpPatchTests.setUp(self)
        with connect() as conn:self.data=seed(conn)
        self.login_as('viewer')

    def login_as(self,who):
        self.cookie='';self.csrf=''
        status,result=self.request('POST','/api/auth/login',{'username':self.data[who]['username'],'password':PASSWORD})
        self.assertEqual(status,200,result)

    def test_nonmember_reads_project_notes_activity_revisions_and_exports(self):
        d=self.data;pid=d['project_id']
        for suffix in ('','/notes','/notes/status','/activity','/revisions',f"/revisions/{d['revision_id']}",'/export',f"/revisions/{d['revision_id']}/export"):
            with self.subTest(suffix=suffix):
                status,result=self.request('GET',f'/api/projects/{pid}'+suffix)
                self.assertEqual(status,200,result)
                if not suffix:self.assertFalse(result['project']['can_edit'])
                if suffix=='/notes':self.assertFalse(result['can_edit']);self.assertFalse(result['notes'][0]['can_delete'])
        status,result=self.request('GET','/api/projects');self.assertEqual(status,200)
        self.assertIn(pid,[p['id'] for p in result['projects']])

    def test_nonmember_all_mutation_routes_fail_before_changing_project(self):
        d=self.data;pid=d['project_id'];lid=d['line_id']
        with connect() as c:before=calculate_project(c,pid)
        cases=[('PATCH','',{'name':'Forbidden'}),('DELETE','',{}),('PATCH','/workflow',{'status':'completed'}),
            ('POST','/lines',{'catalog_item_id':d['catalog_id'],'quantity':99}),('PATCH',f'/lines/{lid}',{'quantity':99}),
            ('DELETE',f'/lines/{lid}',{}),('POST',f'/lines/{lid}/copy',{}),('POST','/manual-items',{}),
            ('POST',f'/lines/{lid}/manual-item',{}),('POST','/reorder',{}),('POST',f'/lines/{lid}/components/reorder',{}),
            ('POST','/notes',{'body':'Forbidden'}),('DELETE',f"/notes/{d['note_id']}",{}),
            ('POST','/revisions',{'label':'Forbidden'}),('DELETE',f"/revisions/{d['revision_id']}",{})]
        for method,suffix,payload in cases:
            with self.subTest(method=method,suffix=suffix):
                status,result=self.request(method,f'/api/projects/{pid}'+suffix,payload)
                self.assertEqual(status,403,result)
        with connect() as c:self.assertEqual(calculate_project(c,pid),before)

    def test_member_edits_are_visible_to_nonmember_with_new_revision(self):
        d=self.data;pid=d['project_id'];self.login_as('editor')
        status,result=self.request('PATCH',f"/api/projects/{pid}/lines/{d['line_id']}",{'quantity':12})
        self.assertEqual(status,200,result);revision=result['project']['revision'];totals=result['totals']
        self.request('POST',f'/api/projects/{pid}/notes',{'body':'Latest member note'})
        self.login_as('viewer')
        status,result=self.request('GET',f'/api/projects/{pid}');self.assertEqual(result['totals'],totals)
        status,result=self.request('POST',f'/api/projects/{pid}/presence',{'tab_id':'test-view-tab-232'})
        self.assertEqual(status,200,result);self.assertEqual(result['revision'],revision);self.assertFalse(result['can_edit'])
        status,result=self.request('GET',f'/api/projects/{pid}/notes');self.assertEqual(result['notes'][0]['body'],'Latest member note')
        ids=[r['id'] for r in result['notes']]
        status,result=self.request('POST',f'/api/projects/{pid}/notes/read',{'note_ids':ids})
        self.assertEqual(status,200,result);self.assertEqual(result['unread_count'],0)

    def test_live_team_change_revokes_http_edit_with_same_session(self):
        d=self.data;pid=d['project_id'];self.login_as('editor')
        with connect() as c:c.execute('UPDATE users SET team_id=? WHERE id=?',(d['teams'][1],d['editor']['id']))
        status,result=self.request('DELETE',f"/api/projects/{pid}/revisions/{d['revision_id']}",{})
        self.assertEqual(status,403,result)
        status,result=self.request('GET',f'/api/projects/{pid}/revisions')
        self.assertEqual(status,200,result);self.assertFalse(result['revisions'][0]['can_delete'])

    def test_activity_endpoint_pages_all_history_and_validates_cursor(self):
        d=self.data;pid=d['project_id']
        with connect() as c:
            for n in range(205):workspace.record_activity(c,pid,d['owner'],'Edited',str(n),touch=False)
        status,result=self.request('GET',f'/api/projects/{pid}/activity');self.assertEqual(status,200,result)
        self.assertEqual(len(result['activity']),200);cursor=result['next_before_id']
        status,second=self.request('GET',f'/api/projects/{pid}/activity?before_id={cursor}')
        self.assertEqual(status,200,second);self.assertIsNone(second['next_before_id'])
        self.assertEqual(len(result['activity'])+len(second['activity']),result['total_activity'])
        for bad in ('-1','text','0'):
            status,error=self.request('GET',f'/api/projects/{pid}/activity?before_id={bad}');self.assertEqual(status,400,error)

    def test_help_route_reads_other_team_and_lighting_and_catalogue(self):
        d=self.data
        for payload,expected in [({'question':'Show material and labour for Orchid Office project'},'Material cost:'),
            ({'question':'Show catalog LED Batten components'},'Cable accessories'),
            ({'question':'Explain light price for Orchid favourite'},'AUD 102.50')]:
            status,result=self.request('POST','/api/assistant/help',payload)
            self.assertEqual(status,200,result);self.assertIn(expected,result['answer']);self.assertTrue(result['sources'])
        status,error=self.request('POST','/api/assistant/help',{'question':'Show all projects'},csrf=False)
        self.assertEqual(status,403,error)
        self.cookie='';self.csrf=''
        status,error=self.request('POST','/api/assistant/help',{'question':'Show all projects'});self.assertEqual(status,401,error)
        status,error=self.request('GET',f"/api/projects/{d['project_id']}");self.assertEqual(status,401,error)

    def test_profile_http_replacement_serves_new_bytes_only(self):
        uid=self.data['viewer']['id'];old=None
        for color in ('red','blue'):
            status,saved=self.request('PATCH','/api/auth/profile',{'photo_data_url':image_url(color)})
            self.assertEqual(status,200,saved)
            status,image=self.request('GET','/api/auth/profile/photo');self.assertEqual(status,200)
            self.assertNotEqual(old,image);old=image
            with connect() as c:
                photos=c.execute('SELECT image FROM user_avatars WHERE user_id=?',(uid,)).fetchall()
                self.assertEqual(len(photos),1);self.assertEqual(bytes(photos[0]['image']),image)
        status,error=self.request('PATCH','/api/auth/profile',{'photo_data_url':'not an image'})
        self.assertEqual(status,400,error)
        status,image=self.request('GET','/api/auth/profile/photo');self.assertEqual(image,old)

    def test_copy_by_viewer_creates_own_project_without_modifying_original(self):
        pid=self.data['project_id']
        with connect() as c:original=calculate_project(c,pid)
        status,result=self.request('POST',f'/api/projects/{pid}/copy',{'name':'My separate copy'})
        self.assertEqual(status,201,result);self.assertNotEqual(result['project']['id'],pid)
        self.assertTrue(result['project']['can_edit'])
        with connect() as c:self.assertEqual(calculate_project(c,pid),original)

    def test_release_health_and_new_assets(self):
        status,result=self.request('GET','/api/health');self.assertEqual((status,result['release'],result['schema_version']),(200,'3.1',29))
        status,html=self.request('GET','/');self.assertEqual(status,200)
        self.assertIn(b'help-chat-scope',html);self.assertIn(b'notes-readonly',html)
        status,css=self.request('GET','/assets/styles.css');self.assertEqual(status,200);self.assertIn(b'calendar-metric-grid',css)

if __name__=='__main__':unittest.main()
