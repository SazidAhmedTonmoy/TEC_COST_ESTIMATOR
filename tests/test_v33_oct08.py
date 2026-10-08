import base64
import unittest
from conest_app import tenders
import test_http_v231 as helpers

class Oct08Tests(unittest.TestCase):
 request=helpers.HttpPatchTests.request
 def setUp(self):
  tenders._store=None;helpers.HttpPatchTests.setUp(self)
 def tearDown(self):
  tenders._store=None;helpers.HttpPatchTests.tearDown(self)
 def test_memory_document_clipboard_and_isolation(self):
  status,data=self.request('POST','/api/clipboard',{'component':{'description':'Isolator','unit_material':12},'userId':999});self.assertEqual(status,200,data);self.assertEqual(data['userId'],self.user_id)
  self.assertEqual(self.request('GET','/api/clipboard')[1]['component']['description'],'Isolator')
  self.assertEqual(self.request('POST','/api/clipboard',{'component':{}},csrf=False)[0],403)
  self.assertEqual(self.request('POST','/api/assistant/memory',{'note':'Prefer concise answers'})[0],200)
  status,d=self.request('POST','/api/assistant/document',{'name':'rates.txt','content':base64.b64encode(b'Isolator allowance AUD 125 per unit.').decode()});self.assertEqual(status,200,d);self.assertNotIn('text',d['documents'][0])
  status,d=self.request('POST','/api/assistant/chat',{'question':'What does the uploaded file say about isolator?','scope':'guide'});self.assertEqual(status,200,d);self.assertIn('125',d['answer'])
  status,m=self.request('GET','/api/assistant/memory');self.assertEqual(len(m['messages']),2)
  status,report=self.request('GET',f'/api/users/{self.user_id}/performance');self.assertEqual(status,200,report);self.assertTrue(any(x['kind']=='Help attachment' and x['count']==1 for x in report['uploads']['byType']))
  self.assertEqual(self.request('GET',f'/api/users/{self.user_id}/performance?since=2026-10-10&until=2026-10-01')[0],400)
  self.assertEqual(self.request('POST','/api/assistant/memory',{'clear':True})[0],200)
  self.assertEqual(self.request('GET','/api/assistant/memory')[1].get('messages',[]),[])
  cookie=self.cookie;self.cookie='';self.assertEqual(self.request('GET','/api/clipboard')[0],401);self.cookie=cookie
 def test_tender_help_and_contributor_ids(self):
  status,d=self.request('POST','/api/assistant/chat',{'question':'Open tenders','scope':'tender'});self.assertEqual(status,200,d);self.assertIn('matching tender submissions',d['answer'])
  store=tenders.get_store()
  with helpers.connect() as db:
   users={r['username'].lower():r['id'] for r in db.execute("SELECT id,username FROM users WHERE username IN ('Tonmoy','Yunus')")}
  for s in store.all_data()['submissions']:
   if 'tonmoy' in users and s.get('legacyImported'):self.assertEqual(s['importedBy'],users['tonmoy'])
  for c in store.all_data()['chases']:
   if 'yunus' in users and c.get('legacyChase'):self.assertEqual(c['authorId'],users['yunus'])

 def test_date_boundaries_and_other_user_isolation(self):
  with helpers.connect() as db:
   db.execute("INSERT INTO document_uploads(user_id,filename,kind,created_at) VALUES(?,?,?,?)",(self.user_id,'in.txt','Help attachment','2026-01-31T13:00:00+00:00'))
   db.execute("INSERT INTO document_uploads(user_id,filename,kind,created_at) VALUES(?,?,?,?)",(self.user_id,'out.txt','Help attachment','2026-02-01T13:00:00+00:00'))
  status,r=self.request('GET',f'/api/users/{self.user_id}/performance?since=2026-02-01&until=2026-02-01');self.assertEqual(status,200,r)
  self.assertEqual(next(x['count'] for x in r['uploads']['byType'] if x['kind']=='Help attachment'),1)
  self.request('POST','/api/clipboard',{'component':{'description':'Private copy'}})
  self.request('POST','/api/assistant/memory',{'note':'Private memory'})
  with helpers.connect() as db:
   other=db.execute('SELECT id,username FROM users WHERE id<>? LIMIT 1',(self.user_id,)).fetchone()
   db.execute('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?',(helpers.accounts.password_hash('other-test-password'),other['id']))
  status,_=self.request('POST','/api/auth/login',{'username':other['username'],'password':'other-test-password'});self.assertEqual(status,200)
  self.assertEqual(self.request('GET','/api/clipboard')[1],{})
  self.assertEqual(self.request('GET','/api/assistant/memory')[1].get('note'),None)

 def test_ai_requires_explicit_opt_in_and_uses_bounded_context(self):
  from unittest.mock import patch
  with patch('conest_app.assistant._api_key',return_value='test-key'),patch('conest_app.assistant._enabled',return_value=True),patch('conest_app.assistant._gemini_generate',return_value='Grounded answer') as generate:
   status,d=self.request('POST','/api/assistant/chat',{'question':'How do I import a tender?','scope':'guide','useAI':False});self.assertEqual(status,200,d);generate.assert_not_called()
   status,d=self.request('POST','/api/assistant/chat',{'question':'Explain tender import','scope':'guide','useAI':True});self.assertEqual(status,200,d);self.assertEqual(d['answer'],'Grounded answer');generate.assert_called_once();self.assertNotIn('test-key',generate.call_args.args[2])
