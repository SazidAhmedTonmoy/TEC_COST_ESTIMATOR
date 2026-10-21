"""v3.5: actual HTTP permissions, cross-session edits, audit and expiry."""
import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from conest_app import accounts, opportunities, tenders
from conest_app.database import connect
import test_http_v231 as helpers


class OpportunityTests(unittest.TestCase):
    request=helpers.HttpPatchTests.request

    def setUp(self):
        tenders._store=None
        helpers.HttpPatchTests.setUp(self)
        self.admin=(self.cookie,self.csrf)
        with connect() as db:
            self.team=db.execute('SELECT id FROM teams ORDER BY id LIMIT 1').fetchone()[0]
            now=tenders.timestamp()
            self.people={}
            for name,team in [('Creator',None),('Reviewer',self.team),('Editor',None),('Stranger',None)]:
                uid=db.execute('''INSERT INTO users(username,name,password_hash,role,team_id,is_active,
                    must_change_password,created_at,updated_at) VALUES (?,?,?,'user',?,1,0,?,?)''',
                    ('opportunity-'+name,name,'unused',team,now,now)).lastrowid
                token=accounts.start_session(db,uid)
                self.people[name]=(uid,'conest_session='+token,accounts.csrf_token(token))
        self.today=datetime.now(ZoneInfo('Australia/Sydney')).date()
        self.future=(self.today+timedelta(days=30)).isoformat()
        self.as_user('Creator')

    def tearDown(self):
        tenders._store=None
        helpers.HttpPatchTests.tearDown(self)

    def as_user(self,name):
        _,self.cookie,self.csrf=self.people[name]

    def create(self,**extra):
        body=dict(project='VIC Potential Project',region='ViC',builders=['Example Builder','example builder'],
                  deadline=self.future,teamId=self.team,scope='Electrical fitout',editorUsers=[],editorTeams=[])
        body.update(extra)
        status,data=self.request('POST','/api/tenders/opportunities',body)
        self.assertEqual(status,200,data)
        return data['opportunity']

    def get(self,item):
        status,result=self.request('GET','/api/tenders/opportunities/'+item['id'])
        self.assertEqual(status,200,result)
        return result

    def test_create_listing_suggestions_permissions_and_assignment(self):
        item=self.create()
        self.assertEqual(item['status'],'awaiting');self.assertEqual(item['region'],'VIC')
        self.assertEqual(item['builders'],['Example Builder'])
        self.assertFalse(item['canApprove']);self.assertTrue(item['canManage'])
        self.assertEqual(self.request('GET','/api/tenders/opportunities?team=mine')[1]['total'],0)
        status,data=self.request('GET','/api/tenders/opportunities?region=vic&q=ELECTRICAL')
        self.assertEqual(status,200);self.assertEqual(data['total'],1)
        self.assertIn('VIC',data['regions']);self.assertIn('Example Builder',data['builders'])
        self.as_user('Reviewer')
        view=self.get(item)['opportunity'];self.assertTrue(view['canApprove']);self.assertFalse(view['canEdit'])
        status,data=self.request('GET','/api/tenders/opportunities?team=mine')
        self.assertEqual(data['total'],1)
        status,inbox=self.request('GET','/api/tenders/opportunities/notifications')
        self.assertGreater(inbox['unread'],0)
        self.assertIn('Team assigned',[n['action'] for n in inbox['items']])
        self.request('POST','/api/tenders/opportunities/notifications/read',{'through':inbox['items'][0]['id']})
        self.assertEqual(self.request('GET','/api/tenders/opportunities/notifications')[1]['unread'],0)
        self.assertEqual(self.request('POST','/api/tenders/opportunities',{**item,'project':'Forged'})[0],403)
        status,approved=self.request('POST','/api/tenders/opportunities/action',{'id':item['id'],'revision':item['revision'],'action':'approve','reason':'Fits the scope'})
        self.assertEqual(status,200,approved);self.assertEqual(approved['opportunity']['status'],'approved')
        audit=self.get(item)['events'][0]
        self.assertEqual(audit['action'],'Approved');self.assertEqual(audit['actor_name'],'Reviewer')
        self.assertTrue(audit['details']['team'])

    def test_grants_live_membership_stale_writes_and_soft_delete(self):
        item=self.create(editorUsers=[self.people['Editor'][0]],editorTeams=[self.team])
        self.as_user('Editor')
        status,data=self.request('POST','/api/tenders/opportunities',{**item,'scope':'New scope'})
        self.assertEqual(status,200,data);new=data['opportunity']
        self.assertEqual(self.request('POST','/api/tenders/opportunities',item)[0],409)
        self.assertEqual(self.request('POST','/api/tenders/opportunities',{**new,'teamId':None})[0],403)
        self.assertEqual(self.request('POST','/api/tenders/opportunities/action',{'id':new['id'],'revision':new['revision'],'action':'delete'})[0],403)
        self.as_user('Reviewer')
        self.assertTrue(self.get(new)['opportunity']['canEdit'])
        with connect() as db:db.execute('UPDATE users SET team_id=NULL WHERE id=?',(self.people['Reviewer'][0],))
        self.assertFalse(self.get(new)['opportunity']['canEdit'])
        self.assertEqual(self.request('POST','/api/tenders/opportunities/action',{'id':new['id'],'revision':new['revision'],'action':'approve'})[0],403)
        self.as_user('Creator')
        status,d=self.request('POST','/api/tenders/opportunities/action',{'id':new['id'],'revision':new['revision'],'action':'delete'})
        self.assertEqual(status,200,d);self.assertEqual(d['opportunity']['status'],'deleted')
        self.assertEqual(self.request('GET','/api/tenders/opportunities')[1]['total'],0)
        self.assertEqual(self.request('GET','/api/tenders/opportunities?status=deleted')[1]['total'],1)
        self.assertIn('Deleted',[e['action'] for e in self.get(new)['events']])
        self.assertEqual(self.request('POST','/api/tenders/opportunities',{**d['opportunity'],'project':'Cannot edit deleted'})[0],403)

    def test_deadline_audit_notifications_no_cache_churn_and_restore(self):
        store=tenders.get_store()
        item=self.create(deadline=(self.today+timedelta(days=2)).isoformat())
        with store.connect() as db:generation=db.execute('SELECT value FROM tender_generation').fetchone()[0]
        opportunities.reconcile(store);opportunities.reconcile(store)
        self.assertEqual(sum(e['action']=='Deadline approaching' for e in self.get(item)['events']),1)
        # Read-only list and notifications do not invalidate the large tender cache.
        self.request('GET','/api/tenders/opportunities');self.request('GET','/api/tenders/opportunities/notifications')
        with store.connect() as db:self.assertEqual(db.execute('SELECT value FROM tender_generation').fetchone()[0],generation)
        opportunities.reconcile(store,(self.today+timedelta(days=4)).isoformat())
        current=self.get(item)['opportunity'];self.assertEqual(current['status'],'expired')
        self.assertEqual(sum(e['action']=='Expired' for e in self.get(item)['events']),1)
        status,new=self.request('POST','/api/tenders/opportunities',{**current,'deadline':self.future})
        self.assertEqual(status,200,new);self.assertEqual(new['opportunity']['status'],'awaiting')
        old=self.create(deadline=(self.today-timedelta(days=2)).isoformat())
        status,d=self.request('POST','/api/tenders/opportunities/action',{'id':old['id'],'revision':old['revision'],'action':'delete'})
        status,d=self.request('POST','/api/tenders/opportunities/action',{'id':old['id'],'revision':d['opportunity']['revision'],'action':'reopen'})
        self.assertEqual(status,200,d);self.assertEqual(d['opportunity']['status'],'expired')

    def test_guards_rejection_and_pagination(self):
        self.assertEqual(self.request('POST','/api/tenders/opportunities',{'project':'Bad'},csrf=False)[0],403)
        item=self.create()
        self.as_user('Stranger')
        self.assertEqual(self.request('POST','/api/tenders/opportunities/action',{'id':item['id'],'revision':0,'action':'reject','reason':'No'})[0],403)
        self.cookie,self.csrf=self.admin
        # Admin manages/deletes but cannot bypass the user's team-membership approval rule.
        self.assertEqual(self.request('POST','/api/tenders/opportunities/action',{'id':item['id'],'revision':0,'action':'approve'})[0],403)
        self.assertEqual(self.request('POST','/api/tenders/opportunities/action',{'id':item['id'],'revision':0,'action':'reject'})[0],400)
        status,d=self.request('POST','/api/tenders/opportunities/action',{'id':item['id'],'revision':0,'action':'reject','reason':'Outside scope'})
        self.assertEqual(status,200,d)
        self.as_user('Creator')
        for n in range(21):self.create(project=f'Paging {n}')
        status,d=self.request('GET','/api/tenders/opportunities?page=999')
        self.assertEqual(status,200);self.assertEqual(d['page'],2);self.assertEqual(len(d['items']),2)
        self.assertEqual(self.request('GET','/api/tenders/opportunities?q=%25')[1]['total'],0)
        self.cookie='';self.csrf=''
        self.assertEqual(self.request('GET','/api/tenders/opportunities')[0],401)

    def test_simultaneous_edits_only_one_commits_and_audit_matches(self):
        from concurrent.futures import ThreadPoolExecutor
        item=self.create();store=tenders.get_store()
        _,_,actor=opportunities.directory(self.people['Creator'][0])
        def write(scope):
            try:return opportunities.save(store,{**item,'scope':scope},actor)
            except tenders.ValidationError as e:return e.status
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(write,['Writer A','Writer B']))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertIn(409,results)
        detail=self.get(item)
        self.assertEqual(sum(e['action']=='Updated' for e in detail['events']),1)
        self.assertEqual(detail['opportunity']['revision'],1)


if __name__=='__main__':unittest.main()
