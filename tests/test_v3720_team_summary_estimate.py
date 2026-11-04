"""v3.7.20: admin period summary and safe approved-team Estimator creation."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

from conest_app import opportunities as op, tenders
from conest_app.database import connect
from conest_app import teams as team_api
from conest_app.team_summary import summary, period_dates
from conest_app.opportunity_estimate import create_estimate
from conest_app.accounts import AccessError
from conest_app.workspace import update_workflow


class TeamSummaryEstimateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ, {
            'CONEST_DB_PATH': str(Path(self.temp.name)/'catalog.db'),
            'CONEST_TENDERS_DB_PATH': str(Path(self.temp.name)/'tenders.db')})
        self.env.start()
        with connect() as db:
            self.admin=dict(db.execute("SELECT id,name,role,team_id FROM users WHERE role='admin' LIMIT 1").fetchone())
            stamp=tenders.timestamp()
            self.team=db.execute('INSERT INTO teams(name,created_at,updated_at) VALUES(?,?,?)',('TEC AU TEAM',stamp,stamp)).lastrowid
            self.other=db.execute('INSERT INTO teams(name,created_at,updated_at) VALUES(?,?,?)',('TEC BD TEAM',stamp,stamp)).lastrowid
            self.member=self.add_user(db,'au-member',self.team)
            self.outsider=self.add_user(db,'bd-member',self.other)
            self.no_team=self.add_user(db,'unassigned',None)
        self.store=tenders.Store(Path(self.temp.name)/'tenders.db')

    @staticmethod
    def add_user(db,name,team_id):
        stamp=tenders.timestamp()
        uid=db.execute('''INSERT INTO users(username,name,password_hash,role,team_id,is_active,must_change_password,created_at,updated_at)
            VALUES(?,?,?,'user',?,1,0,?,?)''',(name,name,'not-a-real-password',team_id,stamp,stamp)).lastrowid
        return {'id':uid,'name':name,'role':'user','team_id':team_id}

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def opp(self,**kwargs):
        return op.save(self.store, {'project':'Bondi refurbishment', 'region':'NSW',
            'location':'13 Sample Street, NSW','builders':['Builder A','Builder B'],
            'workingScope':'Lighting and power takeoff', 'remarks':'Cost estimate requested',
            'category':'Commercial','budget':'$1m-2m','link':'https://example.com/drawings',
            'due':'2026-11-05', 'assignedTeamIds':[self.team], **kwargs},self.admin)['opportunity']

    def test_create_estimate_copies_brief_shares_exact_team_and_links(self):
        item=self.opp()
        self.assertTrue(item['permissions']['createEstimate'])
        self.assertTrue(op.permissions(item,self.member)['createEstimate'])
        self.assertFalse(op.permissions(item,self.outsider)['createEstimate'])
        result=create_estimate(self.store,{'id':item['id'],'revision':item['revision']},self.member)
        pid=result['createdEstimatorProjectId']
        self.assertEqual(result['opportunity']['estimatorProjectId'],pid)
        self.assertTrue(result['journey']['estimatorProject']['available'])
        self.assertIn('Created and linked Estimator project',[event['action'] for event in result['activity']])
        with connect() as db:
            project=dict(db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone())
            self.assertEqual(project['name'],'Bondi refurbishment')
            self.assertEqual(project['status'],'draft')
            self.assertEqual(project['scope_of_work'],'Lighting and power takeoff')
            self.assertEqual(project['submission_deadline'],'2026-11-05')
            self.assertEqual(project['owner_id'],self.member['id'])
            self.assertIn('13 Sample Street',project['notes'])
            self.assertIn('Cost estimate requested',project['notes'])
            self.assertIn('https://example.com/drawings',project['notes'])
            self.assertIn('Builder A',project['client'])
            teams={r['team_id'] for r in db.execute('SELECT team_id FROM project_teams WHERE project_id=?',(pid,))}
            self.assertEqual(teams,{self.team})
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        with self.store.connect() as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        with self.assertRaises(tenders.ValidationError) as duplicate:
            create_estimate(self.store,{'id':item['id'],'revision':result['opportunity']['revision']},self.member)
        self.assertEqual(duplicate.exception.status,409)
        with connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM projects WHERE id=?',(pid,)).fetchone()[0],1)

    def test_only_assigned_team_admin_and_approved_opportunity_can_create(self):
        item=self.opp()
        for user in (self.outsider,self.no_team):
            with self.assertRaises(tenders.ValidationError) as error:
                create_estimate(self.store,{'id':item['id'],'revision':item['revision']},user)
            self.assertEqual(error.exception.status,403)
        pending=op.save(self.store,{'project':'Pending','region':'NSW','due':'2026-11-06','builders':[]},self.admin)['opportunity']
        with self.assertRaises(tenders.ValidationError) as error:
            create_estimate(self.store,{'id':pending['id'],'revision':pending['revision']},self.admin)
        self.assertEqual(error.exception.status,409)
        updated=op.save(self.store,{**item,'remarks':'Changed elsewhere'},self.admin)['opportunity']
        with self.assertRaises(tenders.ValidationError) as error:
            create_estimate(self.store,{'id':item['id'],'revision':item['revision']},self.admin)
        self.assertEqual(error.exception.status,409)
        # An admin can create for teams to which they do not belong.
        result=create_estimate(self.store,{'id':item['id'],'revision':updated['revision']},self.admin)
        with connect() as db:
            teams={r['team_id'] for r in db.execute('SELECT team_id FROM project_teams WHERE project_id=?',(result['createdEstimatorProjectId'],))}
        self.assertEqual(teams,{self.team})

    def test_existing_past_deadline_approved_and_multiple_teams(self):
        item=self.opp(due='2000-01-01',assignedTeamIds=[self.team,self.other])
        self.assertEqual(item['status'],'approved')
        result=create_estimate(self.store,{'id':item['id'],'revision':item['revision']},self.outsider)
        with connect() as db:
            project=db.execute('SELECT submission_deadline FROM projects WHERE id=?',(result['createdEstimatorProjectId'],)).fetchone()
            self.assertEqual(project[0],'2000-01-01')
            teams={r[0] for r in db.execute('SELECT team_id FROM project_teams WHERE project_id=?',(result['createdEstimatorProjectId'],))}
            self.assertEqual(teams,{self.team,self.other})

    def test_error_rolls_back_both_database_writes(self):
        item=self.opp()
        with patch.object(op,'_write',side_effect=RuntimeError('Simulated failure')):
            with self.assertRaisesRegex(RuntimeError,'Simulated failure'):
                create_estimate(self.store,{'id':item['id'],'revision':item['revision']},self.member)
        with connect() as db:
            self.assertFalse(db.execute("SELECT 1 FROM projects WHERE name='Bondi refurbishment'").fetchone())
        stored=op.detail(self.store,item['id'],self.member)['opportunity']
        self.assertEqual(stored['revision'],item['revision'])
        self.assertIsNone(stored.get('estimatorProjectId'))

    def test_admin_only_period_aggregation_and_week_month_filter(self):
        # TEC AU is Tenders-only by default; explicitly opt it into Estimator
        # for the existing report-count regression.
        with connect() as db:
            team_api.save_team(db, {'uses_estimator': True}, self.admin, self.team)
        item=self.opp(due='2026-11-05')
        result=create_estimate(self.store,{'id':item['id'],'revision':item['revision']},self.member)
        project_id=result['createdEstimatorProjectId']
        completed=self.opp(project='Submitted estimate',location='200 Other Road, NSW',due='2026-11-18')
        done=create_estimate(self.store,{'id':completed['id'],'revision':completed['revision']},self.admin)
        with connect() as db:
            update_workflow(db,done['createdEstimatorProjectId'],{'status':'submitted'},self.admin)
        data=summary(self.admin,mode='month',period='2026-11',store=self.store,today=date(2026,11,3))
        au=next(team for team in data['teams'] if team['id']==self.team)
        self.assertEqual((au['assigned_opportunities'],au['estimates_in_progress'],au['estimates_done']),(2,1,1))
        bd=next(team for team in data['teams'] if team['id']==self.other)
        self.assertEqual((bd['assigned_opportunities'],bd['estimates_in_progress'],bd['estimates_done']),(0,0,0))
        week=summary(self.admin,mode='week',period='2026-W45',store=self.store,today=date(2026,11,3))
        au_week=next(team for team in week['teams'] if team['id']==self.team)
        self.assertEqual((au_week['assigned_opportunities'],au_week['estimates_in_progress'],au_week['estimates_done']),(1,1,0))
        december=summary(self.admin,mode='month',period='2026-12',store=self.store,today=date(2026,11,3))
        self.assertTrue(all(team['assigned_opportunities']==0 and team['estimates_in_progress']==0 and team['estimates_done']==0 for team in december['teams']))
        for user in (self.member,self.outsider,{'id':self.member['id'],'role':'admin'}):
            with self.assertRaises(AccessError) as denied:
                summary(user,mode='month',period='2026-11',store=self.store)
            self.assertEqual(denied.exception.status,403)

    def test_estimator_setting_is_persistent_and_closed_is_not_done(self):
        first=self.opp(project='Working',location='11 Other Street, NSW',due='2026-11-05')
        first_project=create_estimate(self.store,{'id':first['id'],'revision':first['revision']},self.member)['createdEstimatorProjectId']
        second=self.opp(project='Submitted',location='22 Other Street, NSW',due='2026-11-06')
        second_project=create_estimate(self.store,{'id':second['id'],'revision':second['revision']},self.member)['createdEstimatorProjectId']
        third=self.opp(project='Discarded',location='33 Other Street, NSW',due='2026-11-07')
        third_project=create_estimate(self.store,{'id':third['id'],'revision':third['revision']},self.member)['createdEstimatorProjectId']
        with connect() as db:
            db.execute("UPDATE projects SET status='submitted' WHERE id=?",(second_project,))
            db.execute("UPDATE projects SET status='closed' WHERE id=?",(third_project,))
            self.assertFalse(team_api.team_uses_estimator(db,self.team,'TEC AU TEAM'))
            self.assertTrue(team_api.team_uses_estimator(db,self.other,'TEC BD TEAM'))
        def au():
            return next(t for t in summary(self.admin,mode='month',period='2026-11',store=self.store)['teams'] if t['id']==self.team)
        initial=au()
        self.assertEqual((initial['assigned_opportunities'],initial['estimates_in_progress'],initial['estimates_done']),(3,0,0))
        self.assertFalse(initial['uses_estimator'])
        with connect() as db:
            saved=team_api.save_team(db, {'uses_estimator':True},self.admin,self.team)
            self.assertTrue(saved['uses_estimator'])
        enabled=au()
        self.assertEqual((enabled['assigned_opportunities'],enabled['estimates_in_progress'],enabled['estimates_done']),(3,1,1))
        self.assertTrue(enabled['uses_estimator'])
        with connect() as db:
            # Rename must not reset a stored preference.
            team_api.save_team(db, {'name':'AU Team Renamed'},self.admin,self.team)
            self.assertTrue(team_api.list_teams(db,self.admin)[0]['uses_estimator'])
            team_api.save_team(db, {'uses_estimator':False},self.admin,self.team)
            with self.assertRaises(ValueError):
                team_api.save_team(db, {'uses_estimator':'false'},self.admin,self.team)
            with self.assertRaises(AccessError):
                team_api.save_team(db, {'uses_estimator':True},self.member,self.team)
        self.assertEqual((au()['estimates_in_progress'],au()['estimates_done']),(0,0))
        self.assertEqual(au()['assigned_opportunities'],3)

    def test_invalid_periods_rejected(self):
        for mode,value in [('month','2026-13'),('month','2026-2'),('week','2026-W00'),('week','2026-W54'),('week','2021-W53'),('month','javascript:bad')]:
            with self.subTest(mode=mode,value=value),self.assertRaises(ValueError):
                period_dates(mode,value)
        self.assertEqual(period_dates('week','2026-W45')['start'],'2026-11-02')

if __name__=='__main__':unittest.main()

# The HTTP route must enforce admin access, not merely hide the panel in HTML.
import test_http_v231 as _http
from conest_app import accounts

class TeamSummaryHttpTests(unittest.TestCase):
    setUp=_http.HttpPatchTests.setUp
    request=_http.HttpPatchTests.request

    def tearDown(self):
        tenders.close_store()
        _http.HttpPatchTests.tearDown(self)

    def test_admin_only_http_summary_and_retired_personal_endpoint(self):
        status, payload=self.request('GET','/api/team-summary?mode=month&period=2026-11')
        self.assertEqual(status,200,payload)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['window']['period'],'2026-11')
        self.assertNotIn('members',json.dumps(payload))
        status, old=self.request('GET','/api/team-workload')
        self.assertEqual(status,410,old)
        with connect() as db:
            stamp=tenders.timestamp()
            db.execute('''INSERT INTO users(username,name,password_hash,role,team_id,is_active,must_change_password,created_at,updated_at)
                VALUES(?,?,?,'user',NULL,1,0,?,?)''',
                ('outsider','Standard Team Member',accounts.password_hash('test-only-unauthorised'),stamp,stamp))
        status, user=self.request('POST','/api/auth/login',{'username':'outsider','password':'test-only-unauthorised'})
        self.assertEqual(status,200,user)
        status, forbidden=self.request('GET','/api/team-summary?mode=month&period=2026-11')
        self.assertEqual(status,403,forbidden)
        self.assertNotIn('teams',forbidden)
