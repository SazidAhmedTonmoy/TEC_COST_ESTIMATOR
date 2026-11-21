"""Live directory results and builder suggestions without per-user/full-data work."""
import base64
import json
import os
import secrets
import sqlite3
import unittest
from unittest.mock import patch

from conest_app import opportunities as op


class OpportunityReadScalingTests(unittest.TestCase):
    def test_directory_batches_memberships_and_keeps_authority_live(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.row_factory = sqlite3.Row
        db.executescript('''
            CREATE TABLE teams(id INTEGER PRIMARY KEY,name TEXT);
            CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,team_id INTEGER,role TEXT,is_active INTEGER);
            CREATE TABLE user_team_memberships(user_id INTEGER,team_id INTEGER,PRIMARY KEY(user_id,team_id));
            INSERT INTO teams VALUES(1,'Team one'),(2,'Team two');
        ''')
        db.executemany("INSERT INTO users VALUES(?,?,1,'user',1)",
                       [(number, f'Person {number:03d}') for number in range(1, 101)])
        db.executemany('INSERT INTO user_team_memberships VALUES(?,1)', [(number,) for number in range(1, 101)])
        db.execute('INSERT INTO user_team_memberships VALUES(1,2)')
        queries = []
        db.set_trace_callback(queries.append)
        with patch.object(op, 'account_connection', return_value=db):
            teams, users = op.directory()
            membership_queries = [query for query in queries if 'SELECT' in query and 'user_team_memberships' in query]
            self.assertEqual(len(membership_queries), 1)
            self.assertEqual(len(users), 100)
            self.assertEqual(users[0]['teamIds'], [1, 2])
            self.assertEqual(teams[0]['name'], 'Team one')
            db.execute('DELETE FROM user_team_memberships WHERE user_id=1 AND team_id=1')
            db.execute('UPDATE users SET is_active=0 WHERE id=100')
            _, changed = op.directory()
            self.assertEqual(changed[0]['teamIds'], [2])
            self.assertEqual(len(changed), 99)

    def test_builder_suggestions_keep_all_sources_without_loading_full_tender_data(self):
        import test_opportunities as fixtures
        from conest_app.database import connect
        from conest_app.projects import create_project
        key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        with patch.dict(os.environ, {'CONEST_ENCRYPTION_KEY': key, 'CONEST_ENCRYPTION_KEY_FILE': ''}):
            fixture = fixtures.OpportunityTests()
            fixture.setUp()
            try:
                fixture.create(builders=['Directory Builder'])
                with fixture.store.connect(write=True) as db:
                    db.execute('INSERT INTO submissions(id,body,revision) VALUES(?,?,0)',
                               ('scaling-test-submission', json.dumps({'id': 'scaling-test-submission',
                                'project': 'Read scaling fixture', 'builder': 'Tender Builder', 'status': 'Open'})))
                with connect() as db:
                    create_project(db, {'name': 'Estimator suggestion fixture', 'builders': ['Estimator Builder']})
                with patch.object(fixture.store, 'all_data', side_effect=AssertionError('Full Tender data must not be loaded for builder names')):
                    result = op.list_opportunities(fixture.store, {}, fixture.admin)
                self.assertTrue({'Directory Builder', 'Tender Builder', 'Estimator Builder'} <= set(result['builders']))
            finally:
                fixture.tearDown()


if __name__ == '__main__':
    unittest.main()
