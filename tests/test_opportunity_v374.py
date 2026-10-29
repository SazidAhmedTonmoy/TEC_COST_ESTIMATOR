import json
import unittest
from tests import test_opportunities as fixtures
from conest_app import opportunities as op, opportunity_matching as matching, tenders

class Opportunity374Tests(unittest.TestCase):
    setUp = fixtures.OpportunityTests.setUp
    tearDown = fixtures.OpportunityTests.tearDown
    make_user = staticmethod(fixtures.OpportunityTests.make_user)
    create = fixtures.OpportunityTests.create
    assert_denied = fixtures.OpportunityTests.assert_denied

    def approved(self, **fields):
        item = self.create(**fields)
        return op.decide(self.store, {'id':item['id'], 'revision':item['revision'], 'decision':'approved'}, self.admin)['opportunity']

    def tender(self, name='Existing project', builder='Builder One'):
        result = self.store.save_submission({'project':name, 'builder':builder, 'value':100,
             'status':'Open', 'builderStatus':'In Progress', 'due':'2026-10-16',
             'location':'1 High St', 'region':'NSW', 'pricing':'Competitive',
             'author':self.creator['name'], '_actor_id':self.creator['id']})
        return result['id']

    def test_duplicate_case_address_acknowledgement_and_race(self):
        a = self.create(project='Retail Centre', location='12 HIGH ST, Sydney')
        payload = {'project':'RETAIL centre', 'location':'12 high st Sydney', 'region':'NSW'}
        check = matching.check_duplicates(self.store, payload, self.creator)
        self.assertEqual(check['duplicateCount'], 1)
        self.assertEqual(check['duplicates'][0]['reason'], 'Same project name and address')
        blocked = op.save(self.store, payload, self.creator)
        self.assertTrue(blocked['requiresDuplicateReview'])
        self.assertEqual(op.list_opportunities(self.store, {}, self.admin)['total'], 1)
        payload['duplicateToken'] = check['duplicateToken']
        saved = op.save(self.store, payload, self.creator)['opportunity']
        self.assertNotEqual(a['id'], saved['id'])
        self.assertTrue(op.save(self.store, payload, self.creator)['requiresDuplicateReview'])
        self.assertEqual(matching.check_duplicates(self.store, {'project':'Other', 'location':'12 high st sydney'}, self.creator)['duplicateCount'],2)
        self.assertEqual(matching.check_duplicates(self.store, {'project':'Unrelated', 'location':''}, self.creator)['duplicateCount'],0)

    def test_category_canonicalization_and_edit_self_exclusion(self):
        a = self.create(category='rEtAiL')
        self.assertEqual(a['category'], 'Retail')
        listed = op.list_opportunities(self.store, {}, self.admin)
        self.assertEqual(sum(c.casefold()=='retail' for c in listed['categories']),1)
        check = matching.check_duplicates(self.store, {'project':a['project'],'id':a['id']},self.creator)
        self.assertEqual(check['duplicateCount'],0)
        edited=op.save(self.store, {'id':a['id'],'revision':a['revision'],'category':'EDUCATION'},self.creator)
        self.assertEqual(edited['opportunity']['category'],'Education')

    def test_link_existing_expired_approved_preserves_data_and_retry(self):
        item = self.approved(due='2020-01-01')
        sid = self.tender()
        self.tender(builder='Builder Two')
        before = self.store.all_data()
        old = {s['id']:dict(s) for s in before['submissions']}
        body = {'id':item['id'],'revision':item['revision'],'submissionId':sid}
        linked = matching.link_project(self.store,body,self.admin)['opportunity']
        self.assertEqual(len(linked['submissionIds']),2)
        self.assertEqual(linked['status'],'approved')
        self.assertEqual(linked['linkedByName'],self.admin['name'])
        self.assertNotIn('quotedBy', linked)
        after = self.store.all_data()
        self.assertEqual(len(after['submissions']),len(before['submissions']))
        for row in after['submissions']:
            previous=old[row['id']]
            self.assertEqual(row['revision'],previous['revision']+(1 if row['id'] in linked['submissionIds'] else 0))
            self.assertEqual({k:v for k,v in row.items() if k not in ('revision','opportunityId')},
                             {k:v for k,v in previous.items() if k not in ('revision','opportunityId')})
        self.assertEqual(before['chases'],after['chases'])
        self.assertEqual(before['reminders'],after['reminders'])
        self.assertTrue(matching.link_project(self.store,body,self.admin)['alreadyLinked'])
        self.assertEqual(after,self.store.all_data())
        actions=op.detail(self.store,item['id'],self.admin)['activity']
        self.assertEqual(sum(e['action']=='Linked existing tender project' for e in actions),1)

    def test_link_permissions_revision_conflicting_links_and_choices(self):
        item=self.approved(project='Opportunity A');sid=self.tender()
        body={'id':item['id'],'revision':item['revision'],'submissionId':sid}
        self.assert_denied(lambda:matching.link_project(self.store,body,self.no_team))
        self.assert_denied(lambda:matching.link_project(self.store,{**body,'revision':0},self.admin),409)
        self.assertEqual(matching.project_choices(self.store,{'id':item['id'],'q':'EXISTING'},self.admin)['total'],1)
        matching.link_project(self.store,body,self.member)
        other=self.approved(project='Opportunity B')
        move={**body,'id':other['id'],'revision':other['revision']}
        review=matching.link_project(self.store,move,self.admin)
        self.assertTrue(review['requiresLinkReview'])
        self.assertFalse(matching.project_choices(self.store,{'id':other['id'],'q':'Existing project'},self.admin)['items'][0]['blocked'])
        matching.link_project(self.store,{**move,'reviewToken':review['reviewToken']},self.admin)
        old=op.detail(self.store,item['id'],self.admin)['opportunity']
        self.assertFalse(old.get('submissionIds'))
        self.assertFalse(old.get('quoteStatus'))
        new=op.detail(self.store,other['id'],self.admin)['opportunity']
        self.assertIn(sid,new['submissionIds'])
        pending=self.create(project='Pending')
        self.assert_denied(lambda:matching.link_project(self.store,{**body,'id':pending['id'],'revision':pending['revision']},self.admin),409)

    def test_change_project_and_stale_transfer_review(self):
        item=self.approved(project='First opportunity')
        one=self.tender(name='Project One')
        two=self.tender(name='Project Two')
        item=matching.link_project(self.store,{'id':item['id'],'revision':item['revision'],'submissionId':one},self.admin)['opportunity']
        request={'id':item['id'],'revision':item['revision'],'submissionId':two}
        review=matching.link_project(self.store,request,self.admin)
        self.assertTrue(review['requiresLinkReview'])
        self.assertEqual(review['previousProjects'],['Project One'])
        # A concurrent tender edit invalidates the proposed transfer.
        with self.store.connect(write=True) as db:
            db.execute('UPDATE submissions SET revision=revision+1 WHERE id=?',(two,))
        stale=matching.link_project(self.store,{**request,'reviewToken':review['reviewToken']},self.admin)
        self.assertTrue(stale['requiresLinkReview'])
        self.assertNotEqual(stale['reviewToken'],review['reviewToken'])
        result=matching.link_project(self.store,{**request,'reviewToken':stale['reviewToken']},self.admin)
        self.assertEqual(result['opportunity']['submissionIds'],[two])
        data={row['id']:row for row in self.store.all_data()['submissions']}
        self.assertFalse(data[one].get('opportunityId'))
        self.assertEqual(data[two]['opportunityId'],item['id'])
        self.assertEqual(data[one]['value'],100)
        self.assertEqual(data[two]['value'],100)

if __name__=='__main__' :unittest.main()
