import unittest
import test_opportunities as fixtures
from conest_app import opportunities as op
from conest_app.opportunity_quoting import unquote
from conest_app.database import connect


class OpportunityCorrectionTests(unittest.TestCase):
    setUp = fixtures.OpportunityTests.setUp
    tearDown = fixtures.OpportunityTests.tearDown
    make_user = staticmethod(fixtures.OpportunityTests.make_user)
    create = fixtures.OpportunityTests.create

    def test_creator_team_can_manage_without_assignment(self):
        with connect() as db:
            colleague = self.make_user(db, 'Colleague', self.team)
        item = op.save(self.store, {'project':'Team work','region':'NSW','builders':['Example']}, self.member)['opportunity']
        self.assertTrue(op.detail(self.store,item['id'],colleague)['opportunity']['permissions']['manage'])
        self.assertFalse(op.detail(self.store,item['id'],self.outsider)['opportunity']['permissions']['manage'])

    def test_form_can_save_with_retired_team(self):
        item = self.create(assignedTeamIds=[self.team,self.other_team])
        with connect() as db:
            db.execute('UPDATE users SET team_id=NULL WHERE team_id=?',(self.other_team,))
            db.execute('DELETE FROM teams WHERE id=?',(self.other_team,))
        saved = op.update_authority(self.store,item,self.admin,'assign')['opportunity']
        self.assertEqual(saved['assignedTeamIds'],[self.team])

    def test_unquote_then_quote_again(self):
        item = self.create()
        approved = op.decide(self.store,{**item,'decision':'approved'},self.admin)['opportunity']
        fields = {'value':1000,'builders':['Builder One','Builder Two']}
        quoted = op.quote(self.store,{**approved,**fields},self.member)['opportunity']
        restored = unquote(self.store,quoted,self.member)['opportunity']
        self.assertFalse(op._is_quoted(restored))
        self.assertEqual(restored['status'],'approved')
        again = op.quote(self.store,{**restored,**fields},self.member)['opportunity']
        self.assertEqual(len(again['submissionIds']),2)
