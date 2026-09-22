"""Exercise real HTTP routes with private temporary databases (no live server)."""
from contextlib import contextmanager
import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from app import ConEstHandler
from conest_app import accounts
from conest_app.database import connect
from conest_app.quotation_parser import ImportDependencyError
from test_v231 import photo_url, FIXTURES


class QuietHandler(ConEstHandler):
    def log_message(self, *args):
        pass


class HttpPatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ, {'CONEST_DB_PATH': str(Path(self.tmp.name)/'http.db')})
        self.env.start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.cookie='';self.csrf=''
        # First request, not an explicit initialize(), must prepare the database.
        status,health=self.request('GET','/api/health')
        self.assertEqual((status,health['schema_version']),(200,26))
        with connect() as conn:
            row=conn.execute("SELECT * FROM users WHERE role='admin' LIMIT 1").fetchone()
            self.username=row['username']; self.user_id=row['id']
            conn.execute('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?',
                         (accounts.password_hash('test-password-only-231'),self.user_id))
        status,result=self.request('POST','/api/auth/login',{'username':self.username,'password':'test-password-only-231'})
        self.assertEqual(status,200,result)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.env.stop();self.tmp.cleanup()

    def request(self,method,path,payload=None,raw=None,content_type=None,csrf=True):
        headers={}
        if self.cookie:headers['Cookie']=self.cookie
        if method not in ('GET','HEAD'):
            headers['X-ConEst-Request']='1'
            if csrf and self.csrf:headers['X-CSRF-Token']=self.csrf
        body=raw
        if payload is not None:
            body=json.dumps(payload).encode();content_type='application/json'
        if content_type:headers['Content-Type']=content_type
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=15)
        try:
            client.request(method,path,body=body,headers=headers)
            response=client.getresponse();self.last_headers=dict(response.getheaders())
            data=response.read();status=response.status
            if response.getheader('Set-Cookie'):self.cookie=response.getheader('Set-Cookie').split(';',1)[0]
            if 'application/json' in response.getheader('Content-Type',''):
                data=json.loads(data)
                if data.get('csrf_token'):self.csrf=data['csrf_token']
            return status,data
        finally:client.close()

    def test_app_defaults_save_destination_and_hours_markup(self):
        status,result=self.request('GET','/api/settings')
        self.assertEqual(result['settings']['default_save_mode'],'estimate')
        for mode in ('update','new','estimate'):
            status,result=self.request('PATCH','/api/settings',{'default_save_mode':mode,'default_labor_hours_markup':.125})
            self.assertEqual(status,200,result)
            status,result=self.request('GET','/api/settings')
            self.assertEqual(result['settings']['default_save_mode'],mode)
            self.assertEqual(float(result['settings']['default_labor_hours_markup']),.125)
        status,result=self.request('PATCH','/api/settings',{'default_save_mode':'invalid'})
        self.assertEqual(status,400)
        status,result=self.request('PATCH','/api/settings',{'default_labor_hours_markup':-1})
        self.assertEqual(status,400)

    def upload(self,filename='tle_standard.pdf',content=None,path='/api/light-prices/preview'):
        boundary='----test-fixture-boundary-231'
        content=content if content is not None else (FIXTURES/filename).read_bytes()
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
              'Content-Type: application/pdf\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
        return self.request('POST',path,raw=body,content_type=f'multipart/form-data; boundary={boundary}')

    def test_upload_review_commit_and_renamed_duplicate(self):
        status,review=self.upload();self.assertEqual(status,200,review)
        self.assertEqual(review['quotes'][0]['status'],'new')
        with connect() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM quotes').fetchone()[0],0)
        status,result=self.request('POST','/api/light-prices/import',{'preview_id':review['preview_id'],'selected':['0']})
        self.assertEqual(status,200,result);self.assertEqual(result['quotes_added'],1)
        status,review=self.upload('renamed.pdf',(FIXTURES/'tle_standard.pdf').read_bytes())
        self.assertEqual(status,200,review);self.assertEqual(review['quotes'][0]['status'],'identical')
        self.assertFalse(review['quotes'][0]['can_import'])
        status,cancel=self.request('DELETE','/api/light-prices/previews/'+review['preview_id'])
        self.assertEqual(status,200,cancel)

    def test_cached_direct_import_fails_safely_and_requires_review(self):
        status,result=self.upload(path='/api/light-prices/import')
        self.assertEqual(status,409,result);self.assertIn('refresh',result['error'].lower())
        with connect() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM quotes').fetchone()[0],0)

    def test_invalid_encrypted_and_missing_dependency_responses(self):
        status,result=self.upload('bad.pdf',b'not a pdf');self.assertEqual(status,400,result)
        self.assertNotIn('Unexpected server error',result['error'])
        status,result=self.upload('tle_encrypted.pdf');self.assertEqual(status,400,result)
        self.assertIn('password',result['error'].lower())
        with patch('conest_app.quotation_parser.parse_content',side_effect=ImportDependencyError('PDF support is not installed in the production Python environment.')):
            status,result=self.upload();self.assertEqual(status,503,result)
            self.assertIn('production Python',result['error'])

    def test_profile_image_contact_session_rotation_and_removal(self):
        before=self.cookie
        status,result=self.request('PATCH','/api/auth/profile',{'contact_number':'+880 1712 345678','photo_data_url':photo_url()})
        self.assertEqual(status,200,result);self.assertNotEqual(self.cookie,before)
        self.assertEqual(result['user']['contact_number'],'+880 1712 345678')
        status,image=self.request('GET','/api/auth/profile/photo')
        self.assertEqual(status,200);self.assertTrue(self.last_headers['Content-Type'].startswith('image/'))
        self.assertEqual(self.last_headers['Cache-Control'],'private, no-store')
        status,result=self.request('GET','/api/auth/session');self.assertEqual(result['user']['has_avatar'],1)
        status,result=self.request('PATCH','/api/auth/profile',{'remove_photo':True})
        self.assertEqual(status,200,result)
        status,result=self.request('GET','/api/auth/profile/photo');self.assertEqual(status,404,result)

    def test_csrf_and_private_photo_authentication(self):
        status,result=self.request('PATCH','/api/auth/profile',{'contact_number':'123456'},csrf=False)
        self.assertEqual(status,403,result)
        self.cookie='';self.csrf=''
        status,result=self.request('GET','/api/auth/profile/photo');self.assertEqual(status,401,result)
        status,result=self.upload();self.assertEqual(status,401,result)

    def test_titles_and_assets_have_no_visible_version(self):
        status,html=self.request('GET','/');self.assertEqual(status,200)
        self.assertIn(b'<title>TEC ConEst</title>',html)
        self.assertIn(b'id="profile-contact"',html)
        self.assertNotIn(b'ESTIMATOR V2.3',html.upper())
        for filename in ('styles.css','profile.js','quotation_import.js'):
            status,data=self.request('GET','/assets/'+filename);self.assertEqual(status,200,filename)


if __name__=='__main__':unittest.main()
