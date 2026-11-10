"""Focused v3.7.21 analytics, source-recency and access regressions."""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

from test_opportunities import OpportunityTests
from conest_app import opportunities as op, tenders
from conest_app.opportunity_analytics import summary


class V3721Features(OpportunityTests):
    def test_analytics_uses_action_dates_and_correct_people(self):
        with patch.object(tenders,'timestamp',return_value='2026-10-30T09:00:00Z'):
            old=self.create(project='October opportunity')
        with patch.object(tenders,'timestamp',return_value='2026-11-05T09:00:00Z'):
            item=self.create(project='November opportunity')
        with patch.object(tenders,'timestamp',return_value='2026-11-07T09:00:00Z'):
            approved=op.decide(self.store,{'id':item['id'],'revision':item['revision'],'decision':'approved'},self.member)['opportunity']
        with patch.object(tenders,'timestamp',return_value='2026-11-08T09:00:00Z'):
            op.quote(self.store,{'id':approved['id'],'revision':approved['revision'],
                'value':10000,'note':'Test quote','quoteNo':'Q1','builders':['Builder One'],
                'submittedDate':'2026-11-08','submittedByTeamId':self.team},self.member)
        november=summary(self.store,{'mode':'month','month':'2026-11'},self.admin)
        self.assertEqual(november['counts'],{'added':1,'approved':1,'quoted':1})
        self.assertEqual(november['contributors']['added'][0]['id'],self.creator['id'])
        self.assertEqual(november['contributors']['approved'][0]['id'],self.member['id'])
        self.assertEqual(november['contributors']['quoted'][0]['id'],self.member['id'])
        self.assertEqual(november['from'],'2026-11-01')
        october=summary(self.store,{'mode':'custom','from':'2026-10-01','to':'2026-10-31'},self.admin)
        self.assertEqual(october['counts'],{'added':1,'approved':0,'quoted':0})
        year=summary(self.store,{'mode':'year','year':'2026'},self.admin)
        self.assertEqual(len(year['monthly']),12)
        self.assertEqual(year['monthly'][9]['added'],1)
        self.assertEqual(year['monthly'][10]['added'],1)
        self.assertEqual(year['monthly'][10]['quoted'],1)

    def test_analytics_requires_real_admin_and_checks_ranges(self):
        self.assert_denied(lambda:summary(self.store,{'mode':'month','month':'2026-11'},self.member))
        self.assert_denied(lambda:summary(self.store,{'mode':'month','month':'2026-11'},
                                 {**self.member,'role':'admin'}))
        for arguments in ({'mode':'custom','from':'2026-11-10','to':'2026-11-09'},
                          {'mode':'month','month':'2026-13'},
                          {'mode':'year','year':'twenty'}):
            with self.subTest(arguments=arguments):
                with self.assertRaises(tenders.ValidationError):
                    summary(self.store,arguments,self.admin)

    def test_imported_opportunities_count_once_and_explicit_approval(self):
        with patch.object(tenders,'timestamp',return_value='2026-11-05T10:00:00Z'):
            result=op.import_records(self.store,[{'project':'Imported for analytics','region':'NSW','sourceStatus':'approved'}],self.creator,'import.xlsx')
        month=summary(self.store,{'mode':'month','month':'2026-11'},self.admin)
        self.assertEqual(month['counts']['added'],1)
        self.assertEqual(month['counts']['approved'],0)  # historical source status isn't a user approval
        self.assertEqual(month['contributors']['added'][0]['id'],self.creator['id'])

    def test_outcomes_are_current_status_of_months_created_opportunities(self):
        """A creator gets credit for outcomes, not the person pressing Approve."""
        stamp='2026-11-05T10:00:00Z'
        with patch.object(tenders,'timestamp',return_value=stamp):
            to_quote=self.create(project='Quoted job')
            not_quoted=self.create(project='Approved but waiting for quote')
            rejected=self.create(project='Rejected job')
            expired=self.create(project='Expired job',due='2000-01-01')
            pending=self.create(project='Awaiting approval')
            in_review=self.create(project='Under review')
        with patch.object(tenders,'timestamp',return_value='2026-12-03T10:00:00Z'):
            quoted_approval=op.decide(self.store,{'id':to_quote['id'],'revision':to_quote['revision'],
                         'decision':'approved'},self.member)['opportunity']
            op.decide(self.store,{'id':not_quoted['id'],'revision':not_quoted['revision'],
                         'decision':'approved'},self.member)
            op.decide(self.store,{'id':rejected['id'],'revision':rejected['revision'],
                         'decision':'rejected'},self.member)
            op.decide(self.store,{'id':in_review['id'],'revision':in_review['revision'],
                         'decision':'review'},self.member)
            op.quote(self.store,{'id':quoted_approval['id'],'revision':quoted_approval['revision'],
                'value':10000,'note':'Quoted','quoteNo':'Q1','builders':['Builder One'],
                'submittedDate':'2026-12-03','submittedByTeamId':self.team},self.member)
        november=summary(self.store,{'mode':'month','month':'2026-11'},self.admin)
        outcomes=november['outcomes']
        self.assertEqual(outcomes,{
            'added':6,'approved':2,'approvedNotQuoted':1,'approvedQuoted':1,
            'rejected':1,'expired':1,'pending':1,'review':1,
        })
        self.assertEqual(outcomes['approved'],outcomes['approvedQuoted']+outcomes['approvedNotQuoted'])
        self.assertEqual(outcomes['added'],sum(outcomes[key] for key in
            ('approved','rejected','expired','pending','review')))
        self.assertEqual(len(november['creators']),1)
        self.assertEqual(november['creators'][0]['id'],self.creator['id'])
        self.assertEqual(november['creators'][0]['approved'],2)
        self.assertEqual(november['monthlyOutcomes'][0]['approvedNotQuoted'],1)
        december=summary(self.store,{'mode':'month','month':'2026-12'},self.admin)
        self.assertEqual(december['outcomes']['added'],0)
        self.assertEqual(december['outcomes']['approved'],0)

    def test_outcome_breakdown_by_creator_and_rejection_replaces_approval(self):
        with patch.object(tenders,'timestamp',return_value='2026-11-05T09:00:00Z'):
            first=self.create(project='Creator first opportunity')
            second=op.save(self.store,{'project':'Different person project','region':'NSW',
                     'builders':['Builder One'],'due':'2099-01-01'},self.member)['opportunity']
        with patch.object(tenders,'timestamp',return_value='2026-11-06T09:00:00Z'):
            approved=op.decide(self.store,{'id':first['id'],'revision':first['revision'],
                     'decision':'approved'},self.member)['opportunity']
        with patch.object(tenders,'timestamp',return_value='2026-11-07T09:00:00Z'):
            op.decide(self.store,{'id':approved['id'],'revision':approved['revision'],
                     'decision':'rejected'},self.member)
        result=summary(self.store,{'mode':'month','month':'2026-11'},self.admin)
        self.assertEqual(result['outcomes']['added'],2)
        self.assertEqual(result['outcomes']['rejected'],1)
        self.assertEqual(result['outcomes']['approved'],0)
        people={row['id']:row for row in result['creators']}
        self.assertEqual(people[self.creator['id']]['rejected'],1)
        self.assertEqual(people[self.member['id']]['pending'],1)

    def test_cohort_outcomes_handle_sydney_time_and_monthly_year(self):
        with patch.object(tenders,'timestamp',return_value='2026-10-31T23:50:00Z'):
            item=self.create(project='Sydney first of November')
        result=summary(self.store,{'mode':'year','year':'2026'},self.admin)
        self.assertEqual(result['monthlyOutcomes'][10]['added'],1)
        self.assertEqual(result['monthlyOutcomes'][9]['added'],0)
        november=summary(self.store,{'mode':'custom','from':'2026-11-01','to':'2026-11-01'},self.admin)
        self.assertEqual(november['outcomes']['added'],1)
        october=summary(self.store,{'mode':'month','month':'2026-10'},self.admin)
        self.assertEqual(october['outcomes']['added'],0)

    def test_seed_approved_status_counts_as_approved_outcome_without_approver(self):
        with patch.object(tenders,'timestamp',return_value='2026-11-05T09:00:00Z'):
            op.import_records(self.store,[{'project':'Historical seed approved','region':'NSW',
                       'sourceStatus':'approved','due':'2099-12-01'}],None,'history.xlsx',seed_key='outcome-test-seed')
        month=summary(self.store,{'mode':'month','month':'2026-11'},self.admin)
        self.assertEqual(month['outcomes']['approved'],1)
        self.assertEqual(month['outcomes']['approvedNotQuoted'],1)
        self.assertEqual(month['counts']['approved'],0)  # Compatibility audit metric still means user action.

    def test_past_due_pending_counts_expired_without_writing(self):
        with patch.object(tenders,'timestamp',return_value='2026-11-01T00:05:00Z'):
            item=self.create(project='Pending deadline fixture')
        with self.store.connect() as db:
            row=db.execute('SELECT body FROM opportunities WHERE id=?',(item['id'],)).fetchone()
            body=json.loads(row['body'])
            body['due']='2026-11-02'
            db.execute('UPDATE opportunities SET body=?,due=? WHERE id=?',
                       (json.dumps(body),'2026-11-02',item['id']))
        result=summary(self.store,{'mode':'month','month':'2026-11'},self.admin,now=date(2026,11,10))
        self.assertEqual(result['outcomes']['expired'],1)
        self.assertEqual(result['outcomes']['pending'],0)
        with self.store.connect() as db:
            row=db.execute('SELECT status FROM opportunities WHERE id=?',(item['id'],)).fetchone()
            self.assertEqual(row['status'],'pending')  # Analytics does not perform writes.

    def test_default_period_is_current_sydney_month(self):
        result=summary(self.store,{},self.admin,now=date(2026,11,10))
        self.assertEqual((result['mode'],result['from'],result['to']),('month','2026-11-01','2026-11-30'))

from test_hours_markup import HoursMarkupTests
from conest_app.catalog import create_manual_catalog_item,search_catalog,get_catalog_item
from conest_app.database import connect

class V3721CatalogRecency(HoursMarkupTests):
    def test_newest_uploaded_precedes_unused_and_recent_use_wins(self):
        with connect() as db:
            old=create_manual_catalog_item(db,{'name':'Catalog recency sample','components':[{'description':'A','quantity_per_unit':1,'unit_material':1}]})
            newer=create_manual_catalog_item(db,{'name':'Catalog recency sample','components':[{'description':'B','quantity_per_unit':1,'unit_material':2}]})
            for item,number,stamp in [(old,1,'2026-09-01T00:00:00Z'),(newer,2,'2026-11-09T00:00:00Z')]:
                db.execute('INSERT INTO sources(file_name,file_sha256,sheet_name,import_format,imported_at) VALUES(?,?,?,?,?)',
                           (f'source-{number}.xlsx',f'test-v3721-{number}','Sheet1','v5',stamp))
                source=db.execute('SELECT last_insert_rowid()').fetchone()[0]
                db.execute('INSERT INTO source_occurrences(catalog_item_id,source_id,source_row) VALUES(?,?,?)',
                           (item['id'],source,number))
        with connect() as db:
            first=search_catalog(db,'Catalog recency sample',sort_by='recent',limit=2)
            self.assertEqual(first[0]['id'],newer['id'])
            self.assertEqual(first[0]['last_uploaded_at'],'2026-11-09T00:00:00Z')
            self.assertEqual(get_catalog_item(db,newer['id'])['occurrences'][0]['file_name'],'source-2.xlsx')
            db.execute('INSERT INTO project_lines(project_id,catalog_item_id,name_snapshot,created_at,updated_at) '
                       'VALUES(?,?,?,?,?)', (self.data['project_id'],old['id'],'Catalog recency sample',
                                             '2026-11-10T00:00:00Z','2026-11-10T00:00:00Z'))
        with connect() as db:
            self.assertEqual(search_catalog(db,'Catalog recency sample',sort_by='recent',limit=1)[0]['id'],old['id'])
            self.assertEqual(search_catalog(db,'Catalog recency sample',sort_by='uploaded',limit=1)[0]['id'],newer['id'])
