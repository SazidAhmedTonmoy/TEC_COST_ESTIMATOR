"""Observed-constraint compatibility and runtime checks on private fixtures."""
from contextlib import closing
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from conest_app import opportunities as op, opportunity_compatibility as compatibility, tenders
from conest_app.auto_upgrade import UpgradeError
from conest_app.database import connect


ACTIVITY_COLUMNS = 'id,opportunity_id,actor_id,actor_name,project,action,details,created_at'


class OpportunityCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('CREATE TABLE opportunities(id TEXT PRIMARY KEY,body TEXT NOT NULL)')
        self.db.execute("INSERT INTO opportunities VALUES('old','{}')")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def present(self):
        return {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def apply(self):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            return compatibility.migrate(self.db, compatibility.migration_plan(self.db, self.present()))

    def make_activity(self, foreign_keys=False, extra=''):
        opportunity_ref = ' REFERENCES opportunities(id)' if foreign_keys else ''
        actor_ref = ' REFERENCES legacy_actors(id)' if foreign_keys else ''
        if foreign_keys:
            self.db.execute('CREATE TABLE legacy_actors(id INTEGER PRIMARY KEY)')
            self.db.execute('INSERT INTO legacy_actors VALUES(7)')
        self.db.execute('''CREATE TABLE opportunity_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL''' + opportunity_ref + ''',
            actor_id INTEGER NOT NULL''' + actor_ref + ''', actor_name TEXT NOT NULL,
            project TEXT NOT NULL, action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL''' + extra + ')')

    def make_people(self, outgoing=False, extra=''):
        if outgoing:
            self.db.execute('CREATE TABLE legacy_people(id INTEGER PRIMARY KEY)')
        person_ref = ' REFERENCES legacy_people(id)' if outgoing else ''
        self.db.execute('''CREATE TABLE opportunity_people (
            opportunity_id TEXT NOT NULL REFERENCES OPPORTUNITIES(id),
            kind TEXT NOT NULL, person_id INTEGER NOT NULL''' + person_ref + extra + ''',
            PRIMARY KEY(opportunity_id,kind,person_id))''')

    def test_source_layouts_and_compatible_optional_metadata_are_unchanged(self):
        self.make_activity(extra=", retained_note TEXT, origin TEXT NOT NULL DEFAULT 'current'")
        self.make_people(extra=", retained_note TEXT, origin TEXT NOT NULL DEFAULT 'current'")
        before = [tuple(row) for row in self.db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')]
        self.assertEqual(compatibility.migration_plan(self.db, self.present()), [])
        self.assertEqual(compatibility.migrate(self.db, []), {})
        self.assertEqual([tuple(row) for row in self.db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')], before)

    def test_each_actual_incompatibility_is_planned(self):
        self.make_activity(extra=', registered_by TEXT NOT NULL')
        self.make_people(outgoing=True)
        self.assertEqual(compatibility.migration_plan(self.db, self.present()),
                         ['opportunity_activity', 'opportunity_people'])
        self.db.execute('DROP TABLE opportunity_activity')
        self.make_activity(extra=', registered_by TEXT NOT NULL DEFAULT (NULL)')
        self.db.execute('DROP TABLE opportunity_people')
        self.make_people(extra=', registered_by TEXT NOT NULL')
        self.assertEqual(compatibility.migration_plan(self.db, self.present()),
                         ['opportunity_activity', 'opportunity_people'])
        self.db.execute('DROP TABLE opportunity_activity')
        self.make_activity(foreign_keys=True)
        self.db.execute('DROP TABLE opportunity_people')
        self.make_people()
        self.assertEqual(compatibility.migration_plan(self.db, self.present()), ['opportunity_activity'])

    def test_activity_archive_preserves_ids_metadata_dependencies_and_sequence(self):
        self.make_activity(foreign_keys=True, extra=', registered_by TEXT NOT NULL')
        original = (41, 'old', 7, 'Original person', 'Original project', 'Created opportunity',
                    '{"exact":"metadata"}', '2026-10-01T00:00:00+00:00', 'Legacy importer')
        self.db.execute('INSERT INTO opportunity_activity VALUES(?,?,?,?,?,?,?,?,?)', original)
        self.db.execute('UPDATE sqlite_sequence SET seq=100 WHERE name=\'opportunity_activity\'')
        self.db.execute('CREATE TABLE historical_activity_link(id INTEGER PRIMARY KEY, event_id INTEGER REFERENCES OPPORTUNITY_ACTIVITY(id))')
        self.db.execute('INSERT INTO historical_activity_link VALUES(3,41)')
        self.db.execute('CREATE VIEW historical_activity_view AS SELECT * FROM opportunity_activity')
        self.db.execute('CREATE TABLE historical_activity_trigger_log(event_id INTEGER)')
        self.db.execute('''CREATE TRIGGER legacy_activity_insert AFTER INSERT ON opportunity_activity
            BEGIN INSERT INTO historical_activity_trigger_log VALUES(NEW.id); END''')
        self.db.execute('CREATE INDEX opportunity_activity_actor ON opportunity_activity(actor_id,created_at)')
        self.db.execute('CREATE TABLE opportunity_activity_legacy_v355(note TEXT)')
        self.db.execute("INSERT INTO opportunity_activity_legacy_v355 VALUES('Retain older archive')")
        self.db.commit()
        archives = self.apply()
        archive = archives['opportunity_activity']
        self.assertEqual(archive, 'opportunity_activity_legacy_v355_2')
        self.assertEqual(tuple(self.db.execute('SELECT * FROM ' + archive).fetchone()), original)
        self.assertEqual(tuple(self.db.execute('SELECT * FROM historical_activity_view').fetchone()), original)
        self.assertEqual(tuple(self.db.execute('SELECT ' + ACTIVITY_COLUMNS + ' FROM opportunity_activity').fetchone()), original[:8])
        self.assertEqual(self.db.execute('PRAGMA foreign_key_list(historical_activity_link)').fetchone()['table'], archive)
        for name in ('legacy_activity_insert', 'opportunity_activity_actor'):
            self.assertEqual(self.db.execute('SELECT tbl_name FROM sqlite_master WHERE name=?', (name,)).fetchone()[0], archive)
        self.assertEqual(self.db.execute('SELECT note FROM opportunity_activity_legacy_v355').fetchone()[0], 'Retain older archive')
        cursor = self.db.execute('''INSERT INTO opportunity_activity
            (opportunity_id,actor_id,actor_name,project,action,details,created_at)
            VALUES('',0,'System','Register','Imported opportunities Excel','{}','2026-10-21')''')
        self.assertEqual(cursor.lastrowid, 101)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM historical_activity_trigger_log').fetchone()[0], 0)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(compatibility.migration_plan(self.db, self.present()), [])

    def test_incoming_assignment_references_stay_with_the_original_rows(self):
        self.make_people()
        self.db.execute("INSERT INTO opportunity_people VALUES('old','assignedUserIds',7)")
        self.db.execute('''CREATE TABLE historical_assignment (
            id INTEGER PRIMARY KEY, opportunity_id TEXT, kind TEXT, person_id INTEGER,
            FOREIGN KEY(opportunity_id,kind,person_id)
                REFERENCES OPPORTUNITY_PEOPLE(opportunity_id,kind,person_id) ON DELETE CASCADE)''')
        self.db.execute("INSERT INTO historical_assignment VALUES(8,'old','assignedUserIds',7)")
        self.db.commit()
        self.assertEqual(compatibility.migration_plan(self.db, self.present()), ['opportunity_people'])
        archive = self.apply()['opportunity_people']
        self.db.execute("DELETE FROM opportunity_people WHERE opportunity_id='old'")
        self.db.execute("INSERT INTO opportunity_people VALUES('old','assignedUserIds',99)")
        self.assertEqual(tuple(self.db.execute('SELECT * FROM historical_assignment').fetchone()),
                         (8, 'old', 'assignedUserIds', 7))
        self.assertEqual(tuple(self.db.execute('SELECT * FROM ' + archive).fetchone()),
                         ('old', 'assignedUserIds', 7))
        self.assertEqual(self.db.execute('PRAGMA foreign_key_list(historical_assignment)').fetchone()['table'], archive)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_list(opportunity_people)').fetchone()['table'], 'opportunities')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(compatibility.migration_plan(self.db, self.present()), [])

    def test_failed_copy_rolls_back_both_archives_and_all_original_data(self):
        self.make_activity(foreign_keys=True)
        self.db.execute('INSERT INTO opportunity_activity VALUES(1,\'old\',7,\'Original\',\'Project\',\'Created\',\'{}\',\'2026-10-21\')')
        self.db.execute('''CREATE TABLE opportunity_people (
            legacy_id INTEGER PRIMARY KEY, opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
            kind TEXT NOT NULL, person_id INTEGER NOT NULL, required_note TEXT NOT NULL)''')
        self.db.executemany('INSERT INTO opportunity_people VALUES(?,?,?,?,?)', [
            (1, 'old', 'assignedUserIds', 7, 'First historical assignment'),
            (2, 'old', 'assignedUserIds', 7, 'Second historical assignment'),
        ])
        self.db.commit()
        before_schema = [tuple(row) for row in self.db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')]
        before = {table: [tuple(row) for row in self.db.execute('SELECT * FROM ' + table)]
                  for table in ('opportunity_activity', 'opportunity_people')}
        with self.assertRaises(sqlite3.IntegrityError):
            self.apply()
        self.assertEqual([tuple(row) for row in self.db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')], before_schema)
        for table, rows in before.items():
            self.assertEqual([tuple(row) for row in self.db.execute('SELECT * FROM ' + table)], rows)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_migration_refuses_to_run_outside_a_transaction(self):
        self.make_activity(foreign_keys=True)
        self.db.commit()
        with self.assertRaisesRegex(UpgradeError, 'active write transaction'):
            compatibility.migrate(self.db, ['opportunity_activity'])
        self.assertNotIn('opportunity_activity_legacy_v355', self.present())


class OpportunityCompatibilityRuntimeTests(unittest.TestCase):
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
            self.admin = dict(db.execute("SELECT id,name,role,team_id FROM users WHERE role='admin' LIMIT 1").fetchone())
        self.store = tenders.Store(root / 'tenders.db').keep_open()

    def tearDown(self):
        self.store.close()
        tenders.close_store()
        self.environment.stop()
        self.temp.cleanup()

    def migrate(self):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            present = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            return compatibility.migrate(db, compatibility.migration_plan(db, present))

    def test_import_region_change_and_system_expiry_work_after_audit_fk_migration(self):
        old = op.save(self.store, {'project': 'Historical project', 'region': 'NSW'}, self.admin)['opportunity']
        with self.store.connect() as db:
            history = [tuple(row) for row in db.execute('SELECT ' + ACTIVITY_COLUMNS + ' FROM opportunity_activity')]
            db.execute('DROP TABLE opportunity_activity')
            db.execute('CREATE TABLE legacy_audit_people(id INTEGER PRIMARY KEY)')
            db.execute('INSERT INTO legacy_audit_people VALUES(?)', (self.admin['id'],))
            db.execute('''CREATE TABLE opportunity_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
                actor_id INTEGER NOT NULL REFERENCES legacy_audit_people(id),
                actor_name TEXT NOT NULL, project TEXT NOT NULL, action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL)''')
            db.executemany('INSERT INTO opportunity_activity VALUES(?,?,?,?,?,?,?,?)', history)
        # Demonstrate the actual incompatible runtime write before upgrading.
        with self.assertRaises(sqlite3.IntegrityError):
            op.regions(self.store, self.admin, {'code': 'VIC', 'origin': 'Melbourne office'})
        archives = self.migrate()
        self.assertEqual(set(archives), {'opportunity_activity'})
        op.regions(self.store, self.admin, {'code': 'VIC', 'origin': 'Melbourne office'})
        imported = op.import_records(self.store, [{'project': 'After schema upgrade', 'region': 'VIC'}],
                                     self.admin, 'new-projects.xlsx', expected_generation=op.generation(self.store))
        self.assertEqual(imported['added'], 1)
        with patch.object(op, '_today', return_value=date(2026, 10, 21)):
            upcoming = op.save(self.store, {'project': 'Deadline test', 'region': 'NSW', 'due': '2026-10-22'}, self.admin)['opportunity']
        op.process_due(self.store, force=True, now=datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc))
        with self.store.connect() as db:
            self.assertEqual(op._find(db, upcoming['id'])['status'], 'expired')
            self.assertEqual(db.execute("SELECT actor_id FROM opportunity_activity WHERE opportunity_id=? AND action='Expired opportunity'", (upcoming['id'],)).fetchone()[0], 0)
            self.assertEqual([tuple(row) for row in db.execute('SELECT ' + ACTIVITY_COLUMNS + ' FROM ' + archives['opportunity_activity'])], history)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tender_activity WHERE action='Imported opportunities Excel'").fetchone()[0], 1)
        self.assertEqual(op.detail(self.store, old['id'], self.admin)['activity'][0]['id'], history[0][0])

    def test_assignment_edits_preserve_referenced_history(self):
        item = op.save(self.store, {'project': 'Assigned historical project', 'region': 'NSW',
                       'assignedUserIds': [self.admin['id']]}, self.admin)['opportunity']
        with self.store.connect() as db:
            db.execute('''CREATE TABLE historical_assignment (
                id INTEGER PRIMARY KEY, opportunity_id TEXT, kind TEXT, person_id INTEGER,
                FOREIGN KEY(opportunity_id,kind,person_id)
                    REFERENCES opportunity_people(opportunity_id,kind,person_id) ON DELETE RESTRICT)''')
            db.execute('INSERT INTO historical_assignment VALUES(1,?,?,?)',
                       (item['id'], 'assignedUserIds', self.admin['id']))
            before = tuple(db.execute('SELECT * FROM historical_assignment').fetchone())
        archives = self.migrate()
        self.assertEqual(set(archives), {'opportunity_people'})
        edited = op.save(self.store, {**item, 'remarks': 'Editing leaves historical references intact'}, self.admin)['opportunity']
        reassigned = op.update_authority(self.store, {**edited, 'assignedUserIds': []}, self.admin, 'assign')['opportunity']
        self.assertEqual(reassigned['assignedUserIds'], [])
        with self.store.connect() as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM historical_assignment').fetchone()), before)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ' + archives['opportunity_people']).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunity_people WHERE opportunity_id=?', (item['id'],)).fetchone()[0], 0)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
