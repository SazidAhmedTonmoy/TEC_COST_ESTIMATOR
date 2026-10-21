"""The owner-requested reset is backed up, atomic, scoped and applied once."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from conest_app import opportunities as op, opportunity_reset as reset, opportunity_retention as retention, tenders
from conest_app.auto_upgrade import UpgradeError
from conest_app.database import connect


class OpportunityResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {
            'CONEST_DB_PATH': str(root / 'catalog.db'),
            'CONEST_TENDERS_DB_PATH': str(root / 'tenders.db'),
        })
        self.environment.start()
        tenders.close_store()
        with connect() as db:
            self.actor = dict(db.execute("SELECT id,name,role,team_id FROM users WHERE role='admin' LIMIT 1").fetchone())
        # Build a pre-update database, before this release's constructor hook.
        with patch.object(reset, 'reset_once', return_value={'applied': False, 'removed': 0}):
            self.store = tenders.Store(root / 'tenders.db').keep_open()
        with self.store.connect() as db:
            retention.ensure_schema(db)

    def tearDown(self):
        self.store.close()
        tenders.close_store()
        self.environment.stop()
        self.temp.cleanup()

    @staticmethod
    def rows(db, table):
        return [tuple(r) for r in db.execute('SELECT * FROM ' + table + ' ORDER BY 1')]

    def marker(self):
        with self.store.connect() as db:
            row = db.execute('SELECT body FROM settings WHERE id=?', (reset.RESET_KEY,)).fetchone()
        return json.loads(row[0]) if row else None

    def backups(self):
        return list((self.store.path.parent / 'upgrade_backups').glob('*before-opportunity-reset-v351-*.db'))

    def populate(self):
        first = op.save(self.store, {
            'project': 'Active before reset', 'region': 'NSW', 'due': '2099-02-03',
            'builders': ['Builder before reset'], 'assignedUserIds': [self.actor['id']],
        }, self.actor)['opportunity']
        second = op.save(self.store, {
            'project': 'Deleted before reset', 'region': 'VIC',
            'builders': ['Another old builder'],
        }, self.actor)['opportunity']
        op.delete(self.store, second, self.actor)
        submission = self.store.all_data()['submissions'][0]
        with self.store.connect() as db:
            self.store.insert_reminder(db, submission['id'], '2099-02-01T09:00', 'Retain this Tender reminder')
            db.execute('INSERT INTO opportunity_events VALUES(?,?)',
                       ('opportunity:old-deadline-event', tenders.timestamp()))
            db.execute('''INSERT INTO tender_notifications
                (id,user_id,kind,target_kind,target_id,title,message,created_at,read_at,event_key)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',
                ('keep-reminder', self.actor['id'], 'reminder', 'submission', submission['id'],
                 'Tender reminder', 'Retain this notification and its read state',
                 tenders.timestamp(), tenders.timestamp(), 'reminder:unrelated'))
            db.execute('INSERT INTO settings VALUES(?,?)',
                       ('opportunities-v35-nsw-20261021', json.dumps({'added': 7})))
            self.before = {table: self.rows(db, table) for table in (
                'opportunities', 'opportunity_people', 'opportunity_events', 'opportunity_builders',
                'opportunity_activity', 'tender_activity', 'submissions', 'chases', 'reminders',
                'tender_notifications', 'opportunity_regions',
            )}
        return first, second

    def test_clear_active_and_deleted_records_with_portable_backup_and_retained_history(self):
        first, second = self.populate()
        generation = op.generation(self.store)
        result = reset.reset_once(self.store)
        self.assertEqual(result, {'applied': True, 'removed': 2})
        self.assertEqual(op.existing_keys(self.store), {})
        self.assertEqual(op.generation(self.store), generation + 1)
        with self.store.connect() as db:
            for table in self.before:
                self.assertEqual(self.rows(db, table), self.before[table], table)
            self.assertTrue(retention.is_retired(db, 'opportunity', first['id']))
            self.assertTrue(retention.is_retired(db, 'opportunity', second['id']))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunities WHERE ' +
                             retention.active_sql('opportunity', 'opportunities.id')).fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunity_builders WHERE ' +
                             retention.active_sql('builder', 'opportunity_builders.builder_key')).fetchone()[0], 0)
            notices = [tuple(row) for row in db.execute('SELECT * FROM tender_notifications WHERE ' +
                       retention.active_sql('notification', 'tender_notifications.id') + ' ORDER BY id')]
            self.assertEqual(notices, [r for r in self.before['tender_notifications'] if r[0] == 'keep-reminder'])
            audit = db.execute("SELECT actor_name,details FROM opportunity_reset_history WHERE action='Cleared opportunity register'").fetchone()
            self.assertEqual(audit['actor_name'], 'System')
            self.assertEqual(json.loads(audit['details'])['removed']['opportunities'], 2)
            self.assertEqual(json.loads(audit['details'])['previouslyVisibleOpportunities'], 1)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        saved = self.backups()
        self.assertEqual(len(saved), 1)
        self.assertEqual(self.marker()['backupFile'], saved[0].name)
        self.assertNotIn(str(self.store.path.parent), json.dumps(self.marker()))
        with closing(sqlite3.connect(f'{saved[0].as_uri()}?mode=ro', uri=True)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'delete')
            for table, old in self.before.items():
                self.assertEqual(self.rows(db, table), old, table)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunities WHERE deleted_at IS NOT NULL').fetchone()[0], 1)
            self.assertIsNone(db.execute('SELECT 1 FROM settings WHERE id=?', (reset.RESET_KEY,)).fetchone())
        self.assertFalse(Path(str(saved[0]) + '-wal').exists())
        self.assertFalse(Path(str(saved[0]) + '-shm').exists())

    def test_old_export_ids_can_be_imported_again_and_survive_constructor_restarts(self):
        old = self.populate()
        # Exercise the actual Store constructor migration, not only the helper.
        upgraded = tenders.Store(self.store.path)
        self.assertIsNotNone(self.marker())
        self.assertEqual(op.existing_keys(upgraded), {})
        result = op.import_records(upgraded, [
            {'sourceRecordId': item['id'], 'project': item['project'], 'region': item['region']}
            for item in old
        ], self.actor, 'reimport.xlsx', expected_generation=op.generation(upgraded))
        self.assertEqual(result['added'], 2)
        new_ids = set(result['items'])
        self.assertFalse(new_ids & {item['id'] for item in old})
        for _ in range(2):
            restarted = tenders.Store(self.store.path)
            self.assertEqual(set(op.existing_keys(restarted).values()), new_ids)
            self.assertEqual(reset.reset_once(restarted), {'applied': False, 'removed': 0})
        self.assertEqual(len(self.backups()), 1)

    def test_backup_failure_clears_nothing_and_does_not_commit_marker(self):
        self.populate()
        generation = op.generation(self.store)
        with patch.object(reset, '_backup', side_effect=UpgradeError('Injected backup failure')):
            with self.assertRaisesRegex(UpgradeError, 'Injected backup failure'):
                reset.reset_once(self.store)
        self.assertIsNone(self.marker())
        self.assertEqual(op.generation(self.store), generation)
        with self.store.connect() as db:
            for table, old in self.before.items():
                self.assertEqual(self.rows(db, table), old, table)
        self.assertEqual(self.backups(), [])

    def test_failure_after_backup_rolls_back_clear_and_retains_the_backup(self):
        self.populate()
        generation = op.generation(self.store)
        with self.store.connect() as db:
            db.execute('''CREATE TRIGGER fail_reset_audit BEFORE INSERT ON opportunity_reset_history
                BEGIN SELECT RAISE(ABORT, 'Injected audit failure'); END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'Injected audit failure'):
            reset.reset_once(self.store)
        self.assertIsNone(self.marker())
        self.assertEqual(op.generation(self.store), generation)
        with self.store.connect() as db:
            for table, old in self.before.items():
                self.assertEqual(self.rows(db, table), old, table)
            self.assertEqual(self.rows(db, 'opportunity_reset_entries'), [])
            self.assertEqual(self.rows(db, 'opportunity_reset_history'), [])
        self.assertEqual(len(self.backups()), 1)

    def test_backup_reader_runs_while_old_worker_write_waits_for_reset_commit(self):
        self.populate()
        original_backup = reset._backup
        attempted = threading.Event()
        future = None

        def old_worker():
            attempted.set()
            return op.save(self.store, {'project': 'Created after reset committed', 'region': 'NSW'}, self.actor)

        with ThreadPoolExecutor(max_workers=1) as pool:
            def observed_backup(store, expected_count):
                nonlocal future
                future = pool.submit(old_worker)
                self.assertTrue(attempted.wait(5))
                with self.assertRaises(FutureTimeout):
                    future.result(timeout=.1)
                return original_backup(store, expected_count)

            with patch.object(reset, '_backup', side_effect=observed_backup):
                result = reset.reset_once(self.store)
            created = future.result(timeout=10)['opportunity']
        self.assertEqual(result['removed'], 2)
        with self.store.connect() as db:
            self.assertEqual([r[0] for r in db.execute('SELECT id FROM opportunities WHERE ' +
                             retention.active_sql('opportunity', 'opportunities.id'))], [created['id']])
        with closing(sqlite3.connect(self.backups()[0])) as db:
            self.assertEqual(self.rows(db, 'opportunities'), self.before['opportunities'])

    def test_two_processes_reset_once_and_create_one_backup(self):
        self.populate()
        script = '''
import json,sys
from pathlib import Path
from conest_app.tenders import Store
from conest_app.opportunity_reset import reset_once
store=object.__new__(Store)
store.path=Path(sys.argv[1])
store._opportunities_ready=True
print('ready',flush=True)
sys.stdin.readline()
print(json.dumps(reset_once(store)),flush=True)
'''
        workers = [subprocess.Popen([sys.executable, '-c', script, str(self.store.path)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                   for _ in range(2)]
        try:
            for worker in workers:
                self.assertEqual(worker.stdout.readline().strip(), 'ready')
            for worker in workers:
                worker.stdin.write('go\n')
                worker.stdin.flush()
            results = []
            for worker in workers:
                stdout, stderr = worker.communicate(timeout=20)
                self.assertEqual(worker.returncode, 0, stderr)
                results.append(json.loads(stdout))
            self.assertEqual(sum(result['applied'] for result in results), 1)
            self.assertEqual(sum(result['removed'] for result in results), 2)
            self.assertEqual(len(self.backups()), 1)
            self.assertIsNotNone(self.marker())
            self.assertEqual(op.existing_keys(self.store), {})
        finally:
            for worker in workers:
                if worker.poll() is None:
                    worker.kill()
                worker.communicate()

    def test_empty_store_records_marker_without_warning_backup_or_fake_activity(self):
        with self.assertNoLogs(reset.log, level='WARNING'):
            result = reset.reset_once(self.store)
        self.assertEqual(result, {'applied': True, 'removed': 0})
        self.assertIsNotNone(self.marker())
        self.assertFalse(self.marker()['backupCreated'])
        self.assertEqual(self.backups(), [])
        with self.store.connect() as db:
            self.assertEqual(self.rows(db, 'opportunity_activity'), [])
            self.assertEqual(self.rows(db, 'opportunity_reset_history'), [])
        fresh = op.save(self.store, {'project': 'First new opportunity', 'region': 'NSW'}, self.actor)['opportunity']
        self.assertFalse(reset.reset_once(self.store)['applied'])
        self.assertEqual(set(op.existing_keys(self.store).values()), {fresh['id']})

    def test_reset_preserves_incoming_foreign_keys_for_every_former_delete_group(self):
        first, _ = self.populate()
        with self.store.connect() as db:
            person = db.execute('SELECT opportunity_id,kind,person_id FROM opportunity_people LIMIT 1').fetchone()
            builder = db.execute('SELECT builder_key FROM opportunity_builders LIMIT 1').fetchone()[0]
            notice = db.execute("SELECT id FROM tender_notifications WHERE target_kind='opportunity' LIMIT 1").fetchone()[0]
            event = db.execute('SELECT event_key FROM opportunity_events LIMIT 1').fetchone()[0]
            db.execute('''CREATE TABLE opportunity_builders_legacy_v354 (
                id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL REFERENCES opportunities(id) ON DELETE RESTRICT,
                name TEXT NOT NULL)''')
            db.execute('INSERT INTO opportunity_builders_legacy_v354 VALUES(?,?,?)',
                       ('archived-builder', first['id'], 'Original archived builder'))
            db.execute('''CREATE TABLE historical_opportunity_link (
                id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE)''')
            db.execute('INSERT INTO historical_opportunity_link VALUES(?,?)', ('retained-cascade-child', first['id']))
            db.execute('''CREATE TABLE historical_assignment_link (
                opportunity_id TEXT NOT NULL, kind TEXT NOT NULL, person_id INTEGER NOT NULL,
                FOREIGN KEY(opportunity_id,kind,person_id)
                    REFERENCES opportunity_people(opportunity_id,kind,person_id) ON DELETE RESTRICT)''')
            db.execute('INSERT INTO historical_assignment_link VALUES(?,?,?)', tuple(person))
            db.execute('CREATE TABLE historical_builder_link(builder_key TEXT NOT NULL REFERENCES opportunity_builders(builder_key))')
            db.execute('INSERT INTO historical_builder_link VALUES(?)', (builder,))
            db.execute('CREATE TABLE historical_event_link(event_key TEXT NOT NULL REFERENCES opportunity_events(event_key))')
            db.execute('INSERT INTO historical_event_link VALUES(?)', (event,))
            db.execute('CREATE TABLE historical_notification_link(notification_id TEXT NOT NULL REFERENCES tender_notifications(id))')
            db.execute('INSERT INTO historical_notification_link VALUES(?)', (notice,))
            linked_tables = ('opportunity_builders_legacy_v354', 'historical_opportunity_link',
                             'historical_assignment_link', 'historical_builder_link',
                             'historical_event_link', 'historical_notification_link')
            before_links = {table: self.rows(db, table) for table in linked_tables}
            # Both physical deletion and a tempting soft-delete UPDATE would
            # disturb unknown legacy behavior. The cohort reset does neither.
            for table in ('opportunities', 'opportunity_people', 'opportunity_events',
                          'opportunity_builders', 'tender_notifications'):
                for operation in ('UPDATE', 'DELETE'):
                    db.execute('CREATE TRIGGER protect_' + table + '_' + operation.lower() +
                               ' BEFORE ' + operation + ' ON ' + table +
                               " BEGIN SELECT RAISE(ABORT, 'Original rows must remain unchanged'); END")
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        result = reset.reset_once(self.store)
        self.assertEqual(result, {'applied': True, 'removed': 2})
        with self.store.connect() as db:
            for table, old in {**self.before, **before_links}.items():
                self.assertEqual(self.rows(db, table), old, table)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunity_reset_history').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunities WHERE ' +
                             retention.active_sql('opportunity', 'opportunities.id')).fetchone()[0], 0)
        self.assertFalse(reset.reset_once(self.store)['applied'])
        self.assertEqual(len(self.backups()), 1)

    def test_reset_system_summary_does_not_insert_fake_parent_or_actor_ids(self):
        self.populate()
        with self.store.connect() as db:
            db.execute('CREATE TABLE legacy_actors(id INTEGER PRIMARY KEY)')
            db.execute('INSERT INTO legacy_actors VALUES(?)', (self.actor['id'],))
            db.execute('''CREATE TABLE linked_opportunity_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
                actor_id INTEGER NOT NULL REFERENCES legacy_actors(id),
                actor_name TEXT NOT NULL, project TEXT NOT NULL, action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL)''')
            db.execute('INSERT INTO linked_opportunity_activity SELECT * FROM opportunity_activity')
            db.execute('DROP TABLE opportunity_activity')  # Only this private fixture.
            db.execute('ALTER TABLE linked_opportunity_activity RENAME TO opportunity_activity')
            db.execute('''CREATE TRIGGER no_fake_system_user BEFORE INSERT ON tender_activity
                WHEN NEW.actor_id=0 BEGIN SELECT RAISE(ABORT, 'No synthetic user ID'); END''')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        reset.reset_once(self.store)
        with self.store.connect() as db:
            self.assertEqual(self.rows(db, 'opportunity_activity'), self.before['opportunity_activity'])
            self.assertEqual(self.rows(db, 'tender_activity'), self.before['tender_activity'])
            audit = db.execute('SELECT * FROM opportunity_reset_history').fetchone()
            self.assertEqual(audit['actor_name'], 'System')
            self.assertEqual(audit['reset_key'], reset.RESET_KEY)
            self.assertEqual(json.loads(audit['details'])['removed']['opportunities'], 2)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_completed_old_marker_does_not_retire_later_records(self):
        first, _ = self.populate()
        old_marker = json.dumps({'release': '3.5.1', 'completedAt': '2026-10-20T12:00:00Z',
                                 'removed': {'opportunities': 10}})
        with self.store.connect() as db:
            db.execute('INSERT INTO settings(id,body) VALUES(?,?)', (reset.RESET_KEY, old_marker))
        self.assertEqual(reset.reset_once(self.store), {'applied': False, 'removed': 0})
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT body FROM settings WHERE id=?', (reset.RESET_KEY,)).fetchone()[0], old_marker)
            self.assertEqual(self.rows(db, 'opportunity_reset_entries'), [])
            self.assertEqual(self.rows(db, 'opportunity_reset_history'), [])
            self.assertFalse(retention.is_retired(db, 'opportunity', first['id']))
        self.assertEqual(self.backups(), [])

    def test_reused_builder_is_reactivated_without_changing_historical_rows(self):
        self.populate()
        reset.reset_once(self.store)
        key = tenders.builder_key('Builder before reset')
        with self.store.connect() as db:
            self.assertTrue(retention.is_retired(db, 'builder', key))
            old_builder_rows = self.rows(db, 'opportunity_builders')
            retired_at = db.execute("SELECT retired_at FROM opportunity_reset_entries WHERE kind='builder' AND record_key=?", (key,)).fetchone()[0]
        moment = tenders.timestamp()
        with self.store.connect() as db:
            retention.reactivate_builder(db, key, moment)
            self.assertFalse(retention.is_retired(db, 'builder', key))
            entry = db.execute("SELECT retired_at,restored_at FROM opportunity_reset_entries WHERE kind='builder' AND record_key=?", (key,)).fetchone()
            self.assertEqual(tuple(entry), (retired_at, moment))
            self.assertEqual(self.rows(db, 'opportunity_builders'), old_builder_rows)
        self.assertFalse(reset.reset_once(self.store)['applied'])
        with self.store.connect() as db:
            self.assertFalse(retention.is_retired(db, 'builder', key))


if __name__ == '__main__':
    unittest.main()
