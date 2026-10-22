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
from conest_app.auto_upgrade import CURRENT_SCHEMA
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
        self.assertEqual((status,health['schema_version']),(200,CURRENT_SCHEMA))
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

    def test_compact_estimate_edits_reorder_and_zero_copy(self):
        from fixtures_v232 import seed
        from conest_app.projects import calculate_project
        with connect() as conn:
            sample=seed(conn);pid=sample['project_id']
        status,base=self.request('GET',f'/api/projects/{pid}')
        def metadata(data):
            return {'_known_lines':{str(l['id']):l['revision'] for l in data['lines']},
                    '_known_pricing':[data['project'].get(k,0) for k in ('material_markup','labor_rate','labor_hours_markup','overhead_markup','crew_size','hours_per_day','excluded_categories')]}
        ids=[l['id'] for l in base['lines']][::-1]
        with patch('app.calculate_project',side_effect=AssertionError('Reorder must not recalculate estimate')):
            status,ordered=self.request('POST',f'/api/projects/{pid}/reorder',dict(metadata(base),ids=ids,expected_revision=base['project']['revision']))
        self.assertEqual(status,201,ordered);self.assertTrue(ordered['estimate_order']);self.assertNotIn('lines',ordered)
        status,base=self.request('GET',f'/api/projects/{pid}');self.assertEqual([l['id'] for l in base['lines']],ids)
        lid=ids[0]
        status,changed=self.request('PATCH',f'/api/projects/{pid}/lines/{lid}',dict(metadata(base),quantity=12,expected_revision=base['lines'][0]['revision']))
        self.assertEqual(status,200,changed);self.assertTrue(changed['estimate_delta']);self.assertEqual([l['id'] for l in changed['lines']],[lid])
        status,full=self.request('GET',f'/api/projects/{pid}');self.assertEqual(changed['totals'],full['totals'])
        status,copied=self.request('POST',f'/api/projects/{pid}/lines/{lid}/copy',dict(metadata(full),expected_revision=full['lines'][0]['revision']))
        self.assertEqual(status,201,copied);self.assertTrue(copied['estimate_delta']);self.assertEqual(len(copied['lines']),1);self.assertEqual(len(copied['line_order']),3)
        with connect() as conn:
            conn.execute('UPDATE project_line_components SET fixed_quantity=1 WHERE project_line_id=?',(lid,))
            source=calculate_project(conn,pid)
        status,zero=self.request('POST',f'/api/projects/{pid}/copy',{'name':'Zero copy','zero_quantities':True})
        self.assertEqual(status,201,zero);self.assertTrue(all(l['quantity']==0 for l in zero['lines']));self.assertEqual(zero['totals']['quoted'],0)
        with connect() as conn:self.assertEqual(calculate_project(conn,pid)['totals'],source['totals'])
        status,normal=self.request('POST',f'/api/projects/{pid}/copy',{'name':'Normal copy'})
        self.assertEqual(status,201,normal);self.assertEqual(normal['totals'],source['totals'])

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

    def test_estimator_bootstrap_matches_authenticated_data(self):
        status,result=self.request('GET','/api/bootstrap')
        self.assertEqual(status,200,result)
        self.assertEqual(result['user']['id'],self.user_id)
        self.assertEqual(result['csrf_token'],self.csrf)
        self.assertEqual(result['dashboard'],self.request('GET','/api/dashboard')[1])
        self.assertEqual(result['settings'],self.request('GET','/api/settings')[1]['settings'])
        self.assertNotIn('gemini_api_key',result['settings'])
        with connect() as conn:
            conn.execute('UPDATE users SET must_change_password=1 WHERE id=?',(self.user_id,))
        status,result=self.request('GET','/api/bootstrap')
        self.assertEqual(status,200,result)
        self.assertTrue(result['user']['must_change_password'])
        self.assertNotIn('dashboard',result)
        self.assertNotIn('settings',result)
        self.cookie=''
        self.assertEqual(self.request('GET','/api/bootstrap')[0],401)

    def test_titles_and_assets_have_no_visible_version(self):
        status,html=self.request('GET','/');self.assertEqual(status,200)
        self.assertIn(b'<title>TEC ConEst Estimator</title>',html)
        self.assertIn(b'id="profile-contact"',html)
        self.assertNotIn(b'ESTIMATOR V2.3',html.upper())
        for filename in ('styles.css','profile.js','quotation_import.js'):
            status,data=self.request('GET','/assets/'+filename);self.assertEqual(status,200,filename)


if __name__=='__main__':unittest.main()
