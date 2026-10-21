"""Regression fixtures for the production pre-deleted_at opportunity schema."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from conest_app import opportunities as op, opportunity_schema as schema, tenders
from conest_app.auto_upgrade import UpgradeError
from conest_app.opportunity_reset import RESET_KEY


class OpportunitySchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {
            'CONEST_DB_PATH': str(root / 'catalog.db'),
            'CONEST_TENDERS_DB_PATH': str(root / 'tenders.db'),
        })
        self.environment.start()
        self.store = self.new_store()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def new_store(self):
        # Exercise the real connection/transaction behavior without bootstrapping
        # accounts or the owner-requested reset except in the integration test.
        store = tenders.Store.__new__(tenders.Store)
        store.path = Path(self.temp.name) / 'tenders.db'
        return store

    @staticmethod
    def item(identifier='active', **changes):
        return {
            'id': identifier, 'revision': 3, 'project': 'Legacy　VIC Project',
            'region': 'VIC', 'status': 'approved', 'due': '2099-02-03',
            'createdBy': 7, 'createdByName': 'Original creator',
            'createdAt': '2026-10-01T09:00:00+00:00',
            'updatedAt': '2026-10-20T09:00:00+00:00',
            'assignedTeamIds': [4], 'assignedUserIds': [7],
            'editorTeamIds': [], 'editorUserIds': [],
            'builders': ['Original Builder'], 'distanceOrigin': 'CBD, Melbourne',
            'location': '', 'workingScope': 'Existing electrical scope',
            **changes,
        }

    def legacy(self, items=None, minimal=False):
        items = [self.item(), self.item('deleted', deletedAt='2026-10-20T10:00:00+00:00')] if items is None else items
        with self.store.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            if minimal:
                db.execute('CREATE TABLE opportunities(id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            else:
                db.execute('''CREATE TABLE opportunities (
                    id TEXT PRIMARY KEY, body TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL, region TEXT NOT NULL, due TEXT NOT NULL DEFAULT '',
                    project_key TEXT NOT NULL, created_by INTEGER,
                    updated_at TEXT NOT NULL, legacy_note TEXT NOT NULL DEFAULT '')''')
            for item in items:
                body = json.dumps(item, ensure_ascii=False, indent=1)
                if minimal:
                    db.execute('INSERT INTO opportunities(id,body) VALUES(?,?)', (item['id'], body))
                else:
                    # Existing denormalized values deliberately differ from the
                    # body in this fixture: a deleted_at-only fix must not alter them.
                    db.execute('''INSERT INTO opportunities
                        (id,body,revision,status,region,due,project_key,created_by,updated_at,legacy_note)
                        VALUES(?,?,?,?,?,?,?,?,?,?)''',
                        (item['id'], body, 9, 'pending', 'NSW', '2099-04-05',
                         'legacy sql key', 19, '2026-10-21T00:00:00+00:00', 'Retain extra field'))
            db.execute('CREATE TABLE unrelated_history(id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
            db.execute('INSERT INTO unrelated_history VALUES(1,?)', ('Retain history and contributions',))
            self.original = [tuple(row) for row in db.execute('SELECT * FROM opportunities ORDER BY id')]

    def backups(self):
        return list((self.store.path.parent / 'upgrade_backups').glob('*before-opportunity-schema-v353-*.db'))

    def columns(self):
        with self.store.connect() as db:
            return [row['name'] for row in db.execute('PRAGMA table_info(opportunities)')]

    def test_confirmed_missing_deleted_at_preserves_rows_and_hides_deleted_record(self):
        self.legacy()
        op.initialize(self.store)
        self.assertTrue(self.store._opportunities_ready)
        with self.store.connect() as db:
            current = [tuple(row) for row in db.execute('SELECT * FROM opportunities ORDER BY id')]
            self.assertEqual([row[:-1] for row in current], self.original)
            self.assertEqual(current[0][-1], None)
            self.assertEqual(current[1][-1], '2026-10-20T10:00:00+00:00')
            self.assertEqual(op._find(db, 'active')['revision'], 9)
            with self.assertRaises(tenders.ValidationError) as caught:
                op._find(db, 'deleted')
            self.assertEqual(caught.exception.status, 404)
            self.assertEqual(op._find(db, 'deleted', include_deleted=True)['deletedAt'], current[1][-1])
            self.assertEqual([row['name'] for row in db.execute('PRAGMA index_info(opportunity_status_due)')],
                             ['deleted_at', 'status', 'due'])
            self.assertEqual(db.execute('SELECT body FROM unrelated_history').fetchone()[0], 'Retain history and contributions')
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        with closing(sqlite3.connect(f'{backups[0].as_uri()}?mode=ro', uri=True)) as db:
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'delete')
            self.assertNotIn('deleted_at', [row[1] for row in db.execute('PRAGMA table_info(opportunities)')])
            self.assertEqual(db.execute('SELECT * FROM opportunities ORDER BY id').fetchall(), self.original)
            self.assertEqual(db.execute('SELECT body FROM unrelated_history').fetchone()[0], 'Retain history and contributions')
        self.assertFalse(Path(str(backups[0]) + '-wal').exists())
        self.assertFalse(Path(str(backups[0]) + '-shm').exists())

    def test_multiple_missing_columns_are_recovered_from_the_json_body(self):
        self.legacy(minimal=True)
        op.initialize(self.store)
        with self.store.connect() as db:
            row = dict(db.execute("SELECT * FROM opportunities WHERE id='active'").fetchone())
            self.assertEqual(row['body'], self.original[0][1])
            self.assertEqual(row['revision'], 3)
            self.assertEqual(row['status'], 'approved')
            self.assertEqual(row['region'], 'VIC')
            self.assertEqual(row['due'], '2099-02-03')
            self.assertEqual(row['project_key'], 'legacy vic project')
            self.assertEqual(row['created_by'], 7)
            self.assertEqual(row['updated_at'], '2026-10-20T09:00:00+00:00')
            self.assertIsNone(row['deleted_at'])
            self.assertEqual([tuple(row) for row in db.execute('''SELECT kind,person_id
                FROM opportunity_people WHERE opportunity_id='active' ORDER BY kind,person_id''')],
                [('assignedTeamIds', 4), ('assignedUserIds', 7)])
            self.assertEqual(db.execute('SELECT name FROM opportunity_builders').fetchone()[0], 'Original Builder')
            self.assertEqual(tuple(db.execute("SELECT origin,timezone FROM opportunity_regions WHERE code='VIC'").fetchone()),
                             ('CBD, Melbourne', 'Australia/Melbourne'))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunity_activity').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tender_notifications').fetchone()[0], 0)

    def test_fresh_and_current_schema_do_not_create_migration_backups(self):
        with patch.object(schema, '_backup', side_effect=AssertionError('Unnecessary backup')):
            op.initialize(self.store)
            op.initialize(self.new_store())
        self.assertEqual(self.backups(), [])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunity_generation').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT code FROM opportunity_regions ORDER BY code').fetchall()[0][0], 'NSW')

    def test_project_origin_override_does_not_replace_the_known_region_default(self):
        item = self.item(distanceOrigin='Project-specific site office, Geelong')
        self.legacy(items=[item], minimal=True)
        op.initialize(self.store)
        with self.store.connect() as db:
            row = db.execute("SELECT body FROM opportunities WHERE id='active'").fetchone()
            self.assertEqual(row['body'], self.original[0][1])
            self.assertEqual(json.loads(row['body'])['distanceOrigin'], 'Project-specific site office, Geelong')
            self.assertEqual(tuple(db.execute("SELECT origin,timezone FROM opportunity_regions WHERE code='VIC'").fetchone()),
                             ('CBD, Melbourne', 'Australia/Melbourne'))

    def test_empty_legacy_table_upgrades_without_backup_and_reopen_is_idempotent(self):
        self.legacy(items=[])
        with patch.object(schema, '_backup', side_effect=AssertionError('Empty table backup')):
            op.initialize(self.store)
            op.initialize(self.new_store())
        self.assertIn('deleted_at', self.columns())
        self.assertEqual(self.backups(), [])

    def test_backup_failure_does_not_change_schema_rows_or_ready_flag(self):
        self.legacy()
        with patch.object(schema, '_backup', side_effect=OSError('Injected storage failure')):
            with self.assertRaisesRegex(OSError, 'Injected storage failure'):
                op.initialize(self.store)
        self.assertFalse(getattr(self.store, '_opportunities_ready', False))
        self.assertNotIn('deleted_at', self.columns())
        with self.store.connect() as db:
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM opportunities ORDER BY id')], self.original)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='opportunity_regions'").fetchone())
        op.initialize(self.store)
        self.assertIn('deleted_at', self.columns())

    def test_failure_after_alter_rolls_back_schema_and_created_tables(self):
        self.legacy()
        with patch.object(schema, '_backfill', side_effect=RuntimeError('Injected failure after ALTER')):
            with self.assertRaisesRegex(RuntimeError, 'Injected failure after ALTER'):
                op.initialize(self.store)
        self.assertNotIn('deleted_at', self.columns())
        self.assertFalse(getattr(self.store, '_opportunities_ready', False))
        with self.store.connect() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='opportunity_regions'").fetchone())
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM opportunities ORDER BY id')], self.original)
        self.assertEqual(len(self.backups()), 1)
        op.initialize(self.store)
        # The successful retry upgrades once; a subsequent worker does no work.
        number = len(self.backups())
        op.initialize(self.new_store())
        self.assertEqual(len(self.backups()), number)

    def test_invalid_body_rolls_back_without_replacing_the_record(self):
        self.legacy()
        with self.store.connect() as db:
            db.execute("UPDATE opportunities SET body='not JSON' WHERE id='active'")
        with self.assertRaisesRegex(UpgradeError, 'existing opportunity cannot be upgraded'):
            op.initialize(self.store)
        self.assertNotIn('deleted_at', self.columns())
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT body FROM opportunities WHERE id='active'").fetchone()[0], 'not JSON')
        self.assertEqual(len(self.backups()), 1)

    def test_late_index_failure_rolls_back_backfill_and_lookup_tables(self):
        self.legacy()
        with patch.object(schema, '_INDEXES', schema._INDEXES + (
            'CREATE INDEX injected_failure ON opportunities(nonexistent_column)',
        )):
            with self.assertRaisesRegex(sqlite3.OperationalError, 'nonexistent_column'):
                op.initialize(self.store)
        self.assertNotIn('deleted_at', self.columns())
        with self.store.connect() as db:
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM opportunities ORDER BY id')], self.original)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='opportunity_people'").fetchone())
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='opportunity_status_due'").fetchone())
        self.assertFalse(getattr(self.store, '_opportunities_ready', False))
        self.assertEqual(len(self.backups()), 1)

    def test_existing_assignment_lookup_and_audit_are_not_rewritten(self):
        self.legacy()
        with self.store.connect() as db:
            db.execute('''CREATE TABLE opportunity_people (
                opportunity_id TEXT NOT NULL REFERENCES opportunities(id), kind TEXT NOT NULL,
                person_id INTEGER NOT NULL, PRIMARY KEY(opportunity_id,kind,person_id))''')
            db.execute("INSERT INTO opportunity_people VALUES('active','assignedTeamIds',99)")
            db.execute('''CREATE TABLE opportunity_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL,
                actor_id INTEGER NOT NULL, actor_name TEXT NOT NULL,
                project TEXT NOT NULL, action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL)''')
            db.execute('''INSERT INTO opportunity_activity
                VALUES(17,'active',7,'Original creator','Historical project','Approved opportunity','{}','2026-10-20')''')
            before = tuple(db.execute('SELECT * FROM opportunity_activity').fetchone())
        op.initialize(self.store)
        with self.store.connect() as db:
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM opportunity_people')],
                             [('active', 'assignedTeamIds', 99)])
            self.assertEqual(tuple(db.execute('SELECT * FROM opportunity_activity').fetchone()), before)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tender_notifications').fetchone()[0], 0)

    def test_unsupported_layout_is_not_rebuilt_or_dropped(self):
        with self.store.connect() as db:
            db.execute('CREATE TABLE opportunities(id TEXT PRIMARY KEY, project TEXT)')
            db.execute("INSERT INTO opportunities VALUES('old','Keep this record')")
        with self.assertRaisesRegex(UpgradeError, 'unsupported layout'):
            op.initialize(self.store)
        self.assertEqual(self.columns(), ['id', 'project'])
        with self.store.connect() as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM opportunities').fetchone()), ('old', 'Keep this record'))

    def test_concurrent_processes_upgrade_once_and_all_observe_new_column(self):
        self.legacy()
        script = '''from pathlib import Path
import sys
from conest_app import opportunities, tenders
store = tenders.Store.__new__(tenders.Store)
store.path = Path(sys.argv[1])
opportunities.initialize(store)
with store.connect() as db:
    assert db.execute("SELECT deleted_at FROM opportunities WHERE id='deleted'").fetchone()[0]
'''
        children = [subprocess.Popen([sys.executable, '-c', script, str(self.store.path)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for _ in range(3)]
        try:
            for child in children:
                output, error = child.communicate(timeout=30)
                self.assertEqual(child.returncode, 0, output + error)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
        self.assertEqual(len(self.backups()), 1)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunity_generation').fetchone()[0], 1)

    def test_store_reopen_respects_completed_reset_and_supports_new_writes(self):
        from conest_app.database import connect

        with connect() as db:
            actor = dict(db.execute("SELECT id,name,role,team_id FROM users WHERE role='admin' LIMIT 1").fetchone())
        current = tenders.Store(self.store.path)
        first = op.save(current, {'project': 'Keep imported project', 'region': 'VIC', 'due': '2099-04-05'}, actor)['opportunity']
        with current.connect() as db:
            marker = db.execute('SELECT body FROM settings WHERE id=?', (RESET_KEY,)).fetchone()[0]
            history = [tuple(row) for row in db.execute('SELECT * FROM opportunity_activity ORDER BY id')]
            # Rebuild only the private fixture as the older production table;
            # migration code itself must never use DROP/RENAME reconstruction.
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute('''CREATE TABLE old_shape (
                id TEXT PRIMARY KEY, body TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL, region TEXT NOT NULL, due TEXT NOT NULL DEFAULT '',
                project_key TEXT NOT NULL, created_by INTEGER, updated_at TEXT NOT NULL)''')
            db.execute('''INSERT INTO old_shape SELECT
                id,body,revision,status,region,due,project_key,created_by,updated_at FROM opportunities''')
            db.execute('DROP TABLE opportunities')
            db.execute('ALTER TABLE old_shape RENAME TO opportunities')
        reopened = tenders.Store(self.store.path)
        retained = op.detail(reopened, first['id'], actor)['opportunity']
        self.assertEqual(retained['project'], 'Keep imported project')
        changed = op.save(reopened, {**retained, 'workingScope': 'Upgrade retained this edit'}, actor)['opportunity']
        created = op.save(reopened, {'project': 'Created after upgrade', 'region': 'NSW'}, actor)['opportunity']
        self.assertNotEqual(changed['id'], created['id'])
        with reopened.connect() as db:
            self.assertEqual(db.execute('SELECT body FROM settings WHERE id=?', (RESET_KEY,)).fetchone()[0], marker)
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM opportunity_activity ORDER BY id')][:len(history)], history)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunities').fetchone()[0], 2)
        again = tenders.Store(self.store.path)
        self.assertEqual(set(op.existing_keys(again).values()), {first['id'], created['id']})
        self.assertEqual(len(self.backups()), 1)


if __name__ == '__main__':
    unittest.main()
