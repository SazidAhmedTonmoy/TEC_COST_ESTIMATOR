"""Open-Awarded card contact and awarded-date persistence (no schema changes)."""
import unittest
from conest_app import tenders
import support_http as helpers

class OpenAwardedTests(unittest.TestCase):
    request=helpers.HttpPatchTests.request
    def setUp(self):
        tenders._store=None
        helpers.HttpPatchTests.setUp(self)
    def tearDown(self):
        tenders._store=None
        helpers.HttpPatchTests.tearDown(self)

    def create(self,project='Award contact test',builder='Awarded Builder'):
        result=self.request('POST','/api/tenders/submissions',{'project':project,'builder':builder,'status':'Open','builderStatus':'Awarded','value':12345.67,'contact':'Original estimator','email':'original@example.com'})
        self.assertEqual(result[0],200,result)
        return result[1]['submission']

    def test_contact_and_award_date_save_without_changing_original_contact(self):
        s=self.create()
        payload={'id':s['id'],'revision':s['revision'],'awardedDate':'2026-11-12',
                 'awardContactName':'Contract administrator','awardContactEmail':'admin@builder.com.au',
                 'awardContactPhone':'+61 2 9812 3456'}
        self.assertEqual(self.request('POST','/api/tenders/open-awarded/contact',payload,csrf=False)[0],403)
        status,response=self.request('POST','/api/tenders/open-awarded/contact',payload)
        self.assertEqual(status,200,response)
        updated=response['submission']
        self.assertEqual(updated['awardContactName'],payload['awardContactName'])
        self.assertEqual(updated['awardContactEmail'],payload['awardContactEmail'])
        self.assertEqual(updated['awardContactPhone'],payload['awardContactPhone'])
        self.assertEqual(updated['awardedDate'],payload['awardedDate'])
        self.assertEqual(updated['contact'],'Original estimator')
        self.assertEqual(updated['email'],'original@example.com')
        self.assertEqual(updated['value'],12345.67)
        self.assertEqual(updated['status'],'Open')
        self.assertEqual(updated['builderStatus'],'Awarded')
        self.assertEqual(self.request('POST','/api/tenders/open-awarded/contact',payload)[0],409)
        reloaded=self.request('GET','/api/tenders/data')[1]
        self.assertEqual(next(i for i in reloaded['submissions'] if i['id']==s['id'])['awardedDate'],'2026-11-12')
        self.assertIn('Updated awarded-project follow-up details', [i['action'] for i in self.activities(s['id'])])
        self.assertEqual(self.request('POST','/api/tenders/submissions',updated)[0],200)
        reloaded=self.request('GET','/api/tenders/data')[1]
        self.assertEqual(next(i for i in reloaded['submissions'] if i['id']==s['id'])['awardContactPhone'],payload['awardContactPhone'])

    def activities(self,sid):
        store=tenders.get_store()
        with store.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM tender_activity WHERE submission_id=?',(sid,))]

    def test_partial_contacts_and_empty_date_are_accepted(self):
        s=self.create('Partial contact')
        status,d=self.request('POST','/api/tenders/open-awarded/contact',{'id':s['id'],'revision':s['revision'],'awardContactName':'Jane'})
        self.assertEqual(status,200,d)
        self.assertEqual(d['submission']['awardContactName'],'Jane')
        self.assertEqual(d['submission']['awardedDate'],'')
        self.assertEqual(d['submission']['awardContactEmail'],'')

    def test_validation_and_non_awarded_rejection(self):
        s=self.create('Contact validation')
        base={'id':s['id'],'revision':s['revision'],'awardContactName':'Jane'}
        for change in ({'awardedDate':'2026-02-30'},{'awardContactEmail':'bad url'},{'awardContactPhone':'javascript:alert(1)'},):
            status,d=self.request('POST','/api/tenders/open-awarded/contact',{**base,**change})
            self.assertEqual(status,400,(change,d))
        self.assertEqual(self.request('POST','/api/tenders/submissions',{**s,'builderStatus':'Unsuccessful'})[0],200)
        current=next(i for i in self.request('GET','/api/tenders/data')[1]['submissions'] if i['id']==s['id'])
        self.assertEqual(self.request('POST','/api/tenders/open-awarded/contact',{**base,'revision':current['revision']})[0],409)
        self.assertEqual(self.request('POST','/api/tenders/open-awarded/contact',{'id':'nonexistent','revision':0})[0],404)

    def test_separate_builder_contacts(self):
        first=self.create('Same Project','Builder One')
        second=self.create('Same Project','Builder Two')
        self.assertEqual(self.request('POST','/api/tenders/open-awarded/contact',{'id':first['id'],'revision':first['revision'],'awardContactName':'First builder manager'})[0],200)
        data=self.request('GET','/api/tenders/data')[1]
        one=next(i for i in data['submissions'] if i['id']==first['id'])
        two=next(i for i in data['submissions'] if i['id']==second['id'])
        self.assertEqual(one['awardContactName'],'First builder manager')
        self.assertFalse(two.get('awardContactName'))

    def test_all_authenticated_users_and_no_unauthorized_access(self):
        s=self.create('General user access')
        original_cookie,original_csrf=self.cookie,self.csrf
        self.cookie='';self.csrf=''
        self.assertEqual(self.request('POST','/api/tenders/open-awarded/contact',{'id':s['id'],'revision':s['revision']})[0],401)
        self.cookie,self.csrf=original_cookie,original_csrf
        # Authenticate as an ordinary user (the feature is not admin-only).
        from conest_app import accounts
        from conest_app.database import connect
        with connect() as conn:
            row=conn.execute("SELECT id,username FROM users WHERE role!='admin' LIMIT 1").fetchone()
            self.assertIsNotNone(row)
            conn.execute('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?',(accounts.password_hash('general-user-test-password'),row['id']))
        self.cookie='';self.csrf=''
        status,d=self.request('POST','/api/auth/login',{'username':row['username'],'password':'general-user-test-password'})
        self.assertEqual(status,200,d)
        self.assertEqual(self.request('GET','/api/tenders/data')[0],200)
        status,d=self.request('POST','/api/tenders/open-awarded/contact',{'id':s['id'],'revision':s['revision'],'awardContactPhone':'+61 410 222 111'})
        self.assertEqual(status,200,d)
        self.assertEqual(d['submission']['awardContactPhone'],'+61 410 222 111')

if __name__=='__main__':unittest.main()
