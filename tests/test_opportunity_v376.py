"""v3.7.6 team-member permissions and document-availability regression tests."""
import unittest

from conest_app import opportunities as op, tenders
from tests import test_opportunities as fixtures


class Opportunity376Tests(unittest.TestCase):
    setUp = fixtures.OpportunityTests.setUp
    tearDown = fixtures.OpportunityTests.tearDown
    make_user = staticmethod(fixtures.OpportunityTests.make_user)
    create = fixtures.OpportunityTests.create
    assert_denied = fixtures.OpportunityTests.assert_denied

    def test_active_team_member_can_edit_unassigned_opportunity(self):
        item = self.create(project='Team can edit')
        self.assertTrue(op.permissions(item, self.member)['edit'])
        changed = op.save(self.store, {'id': item['id'], 'revision': item['revision'],
            'project': 'Updated by team member', 'workingScope': 'New electrical scope'}, self.member)['opportunity']
        self.assertEqual(changed['project'], 'Updated by team member')
        self.assertEqual(changed['updatedBy'], self.member['id'])
        self.assertEqual(changed['status'], 'pending')
        self.assertEqual(op.detail(self.store, item['id'], self.admin)['opportunity']['workingScope'], 'New electrical scope')

    def test_team_member_assigns_and_auto_approves_expired_opportunity(self):
        item = self.create(project='Expired when assigned', due='2000-01-01')
        assigned = op.update_authority(self.store, {'id': item['id'], 'revision': item['revision'],
            'assignedTeamIds': [self.team], 'assignedUserIds': [self.creator['id']]}, self.outsider, 'assign')
        updated = assigned['opportunity']
        self.assertEqual(updated['status'], 'approved')
        self.assertEqual(updated['assignedTeamIds'], [self.team])
        self.assertEqual(updated['assignedUserIds'], [self.creator['id']])
        self.assertEqual(updated['decisionBy'], self.outsider['id'])
        actions = [entry['action'] for entry in assigned['activity']]
        self.assertIn('Assigned opportunity', actions)
        self.assertIn('Approved opportunity', actions)
        with self.store.connect() as db:
            recipient = db.execute("SELECT COUNT(*) FROM tender_notifications WHERE target_id=? AND kind='assignment'",
                (item['id'],)).fetchone()[0]
        self.assertGreater(recipient, 0)

    def test_team_members_cannot_delete_or_manage_editor_access(self):
        item = self.create(project='Restricted superauthority')
        p = op.permissions(item, self.member)
        self.assertTrue(p['edit'])
        self.assertTrue(p['assign'])
        self.assertFalse(p['manage'])
        self.assert_denied(lambda: op.update_authority(self.store, {'id': item['id'],
            'revision': item['revision'], 'editorUserIds': [self.member['id']]}, self.member, 'access'))
        self.assert_denied(lambda: op.delete(self.store, {'id': item['id'], 'revision': item['revision']}, self.member))
        self.assert_denied(lambda: op.save(self.store, {'id': item['id'], 'revision': item['revision'],
            'editorUserIds': [self.member['id']]}, self.member))
        # Creator still can manage access independently of team membership.
        allowed = op.update_authority(self.store, {'id': item['id'], 'revision': item['revision'],
            'editorUserIds': [self.member['id']]}, self.creator, 'access')
        self.assertEqual(allowed['opportunity']['editorUserIds'], [self.member['id']])

    def test_no_team_user_cannot_gain_team_authority_from_payload(self):
        item = self.create(project='Private opportunity')
        self.assert_denied(lambda: op.save(self.store, {'id': item['id'], 'revision': item['revision'],
            'project': 'Unpermitted edit'}, self.no_team))
        self.assert_denied(lambda: op.update_authority(self.store, {'id': item['id'],
            'revision': item['revision'], 'assignedTeamIds': [self.team]}, self.no_team, 'assign'))
        self.assert_denied(lambda: op.set_documents_available(self.store, {'id': item['id'],
            'revision': item['revision'], 'available': True}, self.no_team))

    def test_document_availability_is_boolean_persistent_and_audited(self):
        item = self.create(project='Document tracking')
        self.assertIs(item['documentsAvailable'], False)
        self.assertTrue(item['permissions']['edit'])  # creator
        result = op.set_documents_available(self.store, {'id': item['id'], 'revision': item['revision'],
            'available': True}, self.member)
        changed = result['opportunity']
        self.assertTrue(changed['documentsAvailable'])
        self.assertEqual(changed['revision'], item['revision'] + 1)
        self.assertEqual(result['activity'][0]['action'], 'Updated document availability')
        self.assertEqual(result['activity'][0]['details'], {
            'opportunityId': item['id'], 'before': False, 'after': True})
        self.assertTrue(op.detail(self.store, item['id'], self.creator)['opportunity']['documentsAvailable'])
        self.assertTrue(op.list_opportunities(self.store, {}, self.admin)['items'][0]['documentsAvailable'])
        with self.store.connect() as db:
            notice = db.execute("SELECT COUNT(*) FROM tender_notifications WHERE target_id=? AND event_key LIKE 'documents:%'",
                                (item['id'],)).fetchone()[0]
        self.assertGreater(notice, 0)
        # Explicit no-op must not create another activity event/revision.
        no_change = op.set_documents_available(self.store, {'id': item['id'], 'revision': changed['revision'],
            'available': True}, self.member)
        self.assertEqual(no_change['opportunity']['revision'], changed['revision'])
        clear = op.set_documents_available(self.store, {'id': item['id'], 'revision': changed['revision'],
            'available': False}, self.creator)['opportunity']
        self.assertFalse(clear['documentsAvailable'])

    def test_document_toggle_validates_boolean_and_revision(self):
        item = self.create(project='Validation')
        for value in ['true', 1, None, [], {}]:
            self.assert_denied(lambda: op.set_documents_available(self.store, {'id': item['id'],
                'revision': item['revision'], 'available': value}, self.member), 400)
        self.assert_denied(lambda: op.set_documents_available(self.store, {'id': item['id'],
            'revision': 100, 'available': True}, self.member), 409)
        self.assertFalse(op.detail(self.store, item['id'], self.admin)['opportunity']['documentsAvailable'])

    def test_document_toggle_not_allowed_after_expiry_or_rejection(self):
        expired = self.create(project='Expired docs', due='2000-01-01')
        self.assertEqual(expired['status'], 'expired')
        self.assert_denied(lambda: op.set_documents_available(self.store, {'id': expired['id'],
            'revision': expired['revision'], 'available': True}, self.admin), 409)
        pending = self.create(project='Rejected docs')
        rejected = op.decide(self.store, {'id': pending['id'], 'revision': pending['revision'],
            'decision': 'rejected'}, self.member)['opportunity']
        self.assert_denied(lambda: op.set_documents_available(self.store, {'id': rejected['id'],
            'revision': rejected['revision'], 'available': True}, self.admin), 409)
        # Reapproval makes the same saved field available for editing again.
        approved = op.decide(self.store, {'id': rejected['id'], 'revision': rejected['revision'],
            'decision': 'approved'}, self.member)['opportunity']
        changed = op.set_documents_available(self.store, {'id': approved['id'],
            'revision': approved['revision'], 'available': True}, self.member)['opportunity']
        self.assertTrue(changed['documentsAvailable'])

    def test_edit_and_excel_cannot_override_document_status(self):
        item = self.create(project='No spoofing', documentsAvailable=True)
        self.assertFalse(item['documentsAvailable'])
        item = op.set_documents_available(self.store, {'id': item['id'], 'revision': item['revision'],
            'available': True}, self.creator)['opportunity']
        edited = op.save(self.store, {'id': item['id'], 'revision': item['revision'],
            'project': 'Edited but docs remain', 'documentsAvailable': False}, self.member)['opportunity']
        self.assertTrue(edited['documentsAvailable'])
        self.assertNotEqual(edited['project'], item['project'])


if __name__ == '__main__':
    unittest.main()
