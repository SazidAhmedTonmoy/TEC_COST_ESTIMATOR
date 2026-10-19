import unittest
import test_http_v232 as previous
from conest_app.database import connect

class SharingTests(unittest.TestCase):
    setUp=previous.Http232Tests.setUp
    tearDown=previous.Http232Tests.tearDown
    request=previous.Http232Tests.request
    login_as=previous.Http232Tests.login_as

    def test_public_is_scoped_readonly_revocable_and_escaped(self):
        self.login_as('owner');pid=self.data['project_id'];endpoint=f'/api/projects/{pid}/share'
        with connect() as c:c.execute('UPDATE projects SET name=? WHERE id=?',('<script>alert(1)</script> Shared estimate',pid))
        status,result=self.request('POST',endpoint,{'action':'create'});self.assertEqual(status,200,result);link=result['path']
        cookie,csrf=self.cookie,self.csrf;self.cookie='';self.csrf=''
        status,body=self.request('GET',link);self.assertEqual(status,200,body)
        self.assertIn(b'&lt;script&gt;',body);self.assertNotIn(b'<script>',body)
        self.assertIn(b'Component',body);self.assertNotIn(b'password_hash',body)
        self.assertEqual(self.last_headers['Cache-Control'],'no-store')
        for endpoint2 in [f'/api/projects/{pid}','/api/projects',f'/api/projects/{pid}/activity']:
            self.assertEqual(self.request('GET',endpoint2)[0],401)
        self.assertEqual(self.request('POST',link,{'name':'evil'})[0],405)
        self.assertEqual(self.request('GET',link[:-1]+('A' if link[-1]!='A' else 'B'))[0],404)
        self.cookie,self.csrf=cookie,csrf
        status,result=self.request('POST',endpoint,{'action':'create'});self.assertEqual(status,200,result)
        self.assertEqual(self.request('GET',link)[0],404)
        link=result['path'];self.assertEqual(self.request('GET',link)[0],200)
        self.assertEqual(self.request('POST',endpoint,{'action':'revoke'})[0],200)
        self.assertEqual(self.request('GET',link)[0],404)

    def test_only_project_manager_can_share_and_csrf_required(self):
        url=f"/api/projects/{self.data['project_id']}/share"
        for who in ['viewer','editor']:
            self.login_as(who);self.assertEqual(self.request('POST',url,{'action':'create'})[0],403)
        self.login_as('owner');self.assertEqual(self.request('POST',url,{'action':'create'},csrf=False)[0],403)
        status,result=self.request('POST',url,{'action':'create'});self.assertEqual(status,200,result)
        with connect() as c:
            token=c.execute('SELECT token_hash FROM project_public_links').fetchone()[0]
            self.assertNotEqual(token,result['path'].split('/')[-1])
            c.execute('DELETE FROM projects WHERE id=?',(self.data['project_id'],))
        self.assertEqual(self.request('GET',result['path'])[0],404)

if __name__=='__main__':unittest.main()
