"""Batched contact rendering keeps selections, revisions and live access intact."""
import base64
from contextlib import contextmanager
import os
import secrets
import unittest
from unittest.mock import patch

import test_opportunities as fixtures
from conest_app import builder_contacts as contacts, opportunities as op, tenders
from conest_app.database import connect


class OpportunityContactBatchTests(unittest.TestCase):
    make_user = staticmethod(fixtures.OpportunityTests.make_user)
    create = fixtures.OpportunityTests.create

    def setUp(self):
        self.key_env = patch.dict(os.environ, {
            'CONEST_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            'CONEST_ENCRYPTION_KEY_FILE': '',
        })
        self.key_env.start()
        self.addCleanup(self.key_env.stop)
        fixtures.OpportunityTests.setUp(self)

    tearDown = fixtures.OpportunityTests.tearDown

    def seed_contacts(self):
        people = [
            {'name': 'Zoe Contact', 'phones': ['0400 111 222', '02 9000 1000'],
             'emails': ['zoe@example.test', 'zoe.office@example.test']},
            {'name': 'Aaron Contact', 'phones': [], 'emails': ['aaron@example.test']},
        ]
        with patch.object(tenders, 'timestamp', return_value='2026-01-01T12:00:00Z'):
            first = self.create(project='Alpha contact page', builders=['Empty Builder', 'Selected Builder'],
                builderContacts=[{'builder': 'Selected Builder', 'contacts': people}])
        selected = first['builderContacts'][1]['contacts']
        with patch.object(tenders, 'timestamp', return_value='2026-01-02T12:00:00Z'):
            latest = self.create(project='Zulu latest contact', builders=['Selected Builder'],
                builderContacts=[{'builder': 'Selected Builder', 'contacts': list(reversed(selected))}])
        op.process_due(self.store)
        return first, latest

    def test_page_and_latest_share_one_query_preserving_empty_groups_and_contact_order(self):
        first, latest = self.seed_contacts()
        statements = []
        original = self.store.connect
        @contextmanager
        def traced(*args, **kwargs):
            with original(*args, **kwargs) as db:
                db.set_trace_callback(statements.append)
                yield db
        with patch.object(self.store, 'connect', traced), \
             patch.object(contacts, '_links', side_effect=AssertionError('Per-builder queries must not run')):
            listed = op.list_opportunities(self.store, {'sort': 'name', 'pageSize': 1}, self.admin)
        self.assertEqual(sum('FROM builder_contact_links' in sql for sql in statements), 1)
        self.assertEqual(listed['items'][0]['id'], first['id'])
        self.assertEqual(listed['latestOpportunity']['id'], latest['id'])
        self.assertEqual(listed['items'][0]['builderContacts'], first['builderContacts'])
        self.assertEqual(listed['latestOpportunity']['builderContacts'], latest['builderContacts'])
        self.assertEqual(listed['items'][0]['builderContacts'][0], {'builder': 'Empty Builder', 'contacts': []})
        self.assertEqual([person['name'] for person in listed['items'][0]['builderContacts'][1]['contacts']],
                         ['Zoe Contact', 'Aaron Contact'])

    def test_preloaded_views_are_independent_and_next_request_reads_current_contact_revision(self):
        first, latest = self.seed_contacts()
        with self.store.connect() as db:
            preloaded = contacts.opportunity_contact_map(db, [first['id'], latest['id'], first['id']])
            left = contacts.opportunity_view(db, first, contact_map=preloaded)
            right = contacts.opportunity_view(db, first, contact_map=preloaded)
            left['builderContacts'][1]['contacts'][0]['phones'].append('caller mutation')
            self.assertEqual(right['builderContacts'], first['builderContacts'])
        person = first['builderContacts'][1]['contacts'][0]
        contacts.save(self.store, {'builder': 'Selected Builder',
            'contacts': [{**person, 'phones': ['0400 999 888'], 'emails': ['updated@example.test']}]}, self.admin)
        listed = op.list_opportunities(self.store, {'sort': 'name'}, self.admin)
        by_id = {item['id']: item for item in listed['items']}
        for identifier, position in ((first['id'], 0), (latest['id'], 1)):
            group = next(group for group in by_id[identifier]['builderContacts'] if group['builder'] == 'Selected Builder')
            current = group['contacts'][position]
            self.assertEqual(current['phones'], ['0400 999 888'])
            self.assertEqual(current['emails'], ['updated@example.test'])
            self.assertEqual(current['revision'], person['revision'] + 1)

    def test_list_permissions_still_recheck_membership_and_account_state(self):
        self.seed_contacts()
        listed = op.list_opportunities(self.store, {}, self.no_team)
        self.assertFalse(any(item['permissions']['edit'] for item in listed['items']))
        with connect() as db:
            db.execute('INSERT INTO user_team_memberships(user_id,team_id) VALUES(?,?)',
                       (self.no_team['id'], self.team))
        listed = op.list_opportunities(self.store, {}, self.no_team)
        self.assertTrue(all(item['permissions']['edit'] for item in listed['items']))
        with connect() as db:
            db.execute('DELETE FROM user_team_memberships WHERE user_id=?', (self.no_team['id'],))
        listed = op.list_opportunities(self.store, {}, self.no_team)
        self.assertFalse(any(item['permissions']['edit'] for item in listed['items']))
        with connect() as db:
            db.execute('UPDATE users SET is_active=0 WHERE id=?', (self.no_team['id'],))
        with self.assertRaises(tenders.ValidationError) as caught:
            op.list_opportunities(self.store, {}, self.no_team)
        self.assertEqual(caught.exception.status, 403)


if __name__ == '__main__':
    unittest.main()
