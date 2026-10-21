"""The hosted creator_id failure, preserved history, and current-parent writes."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from conest_app import opportunities as op, opportunity_compatibility as compatibility
from conest_app import opportunity_schema as schema, opportunity_reset as reset, tenders
from conest_app.auto_upgrade import UpgradeError
from conest_app.database import connect


PARENT_DDL = '''CREATE TABLE opportunities (
    id TEXT PRIMARY KEY, body TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL,
    region TEXT NOT NULL, due TEXT NOT NULL DEFAULT '', project_key TEXT NOT NULL,
    created_by INTEGER, deleted_at TEXT, updated_at TEXT NOT NULL,
    creator_id INTEGER NOT NULL, legacy_metadata BLOB,
    UNIQUE(region,project_key))'''


def item(identifier='original', **changes):
    return {
        'id': identifier, 'revision': 2, 'project': 'Historical NSW opportunity',
        'status': 'pending', 'region': 'NSW', 'due': '2099-11-30',
        'createdBy': 7, 'createdByName': 'Original creator',
        'createdAt': '2026-10-01T00:00:00+00:00',
        'updatedAt': '2026-10-20T00:00:00+00:00',
        'builders': ['Historical Builder'], 'location': 'Silverwater',
        'workingScope': 'Retained original electrical scope',
        'assignedTeamIds': [], 'assignedUserIds': [],
        'editorTeamIds': [], 'editorUserIds': [],
        'customOriginalValue': {'source': 'untouched legacy JSON'},
        **changes,
    }


def put_parent(db, record):
    body = json.dumps(record, ensure_ascii=False, indent=1)
    db.execute('INSERT INTO opportunities VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (
        record['id'], body, record['revision'], record['status'], record['region'],
        record['due'], tenders.project_key(record['project']), record.get('createdBy'),
        record.get('deletedAt'), record['updatedAt'], record.get('createdBy', 7),
        sqlite3.Binary(b'\x00\xffOriginal metadata'),
    ))


def snapshot(db):
    tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {
        'schema': [tuple(row) for row in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name')],
        'rows': {table: [tuple(row) for row in db.execute('SELECT * FROM "' + table.replace('"', '""') + '"')]
                 for table in tables},
    }


class ParentSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {
            'CONEST_DB_PATH': str(root / 'catalog.db'),
            'CONEST_TENDERS_DB_PATH': str(root / 'tenders.db'),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.store = tenders.Store.__new__(tenders.Store)
        self.store.path = root / 'tenders.db'

    def initialize(self):
        schema.initialize(self.store, op.DEFAULT_REGIONS)

    def backups(self):
        return list((self.store.path.parent / 'upgrade_backups').glob('*before-opportunity-schema-*.db'))

    def present(self, db):
        return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def test_exact_creator_id_failure_is_repaired_without_losing_original_columns(self):
        with self.store.connect() as db:
            db.execute(PARENT_DDL)
            put_parent(db, item())
            db.execute('CREATE TABLE historical_parent_link(id INTEGER PRIMARY KEY, opportunity_id TEXT REFERENCES opportunities(id) ON DELETE CASCADE)')
            db.execute("INSERT INTO historical_parent_link VALUES(81,'original')")
            db.execute('CREATE VIEW historical_parent_view AS SELECT * FROM opportunities')
            db.execute('CREATE TABLE historical_trigger_log(note TEXT)')
            db.execute('''CREATE TRIGGER parent_update AFTER UPDATE ON opportunities
                BEGIN INSERT INTO historical_trigger_log VALUES('Original updated'); END''')
            db.execute('CREATE INDEX opportunity_status_due ON opportunities(deleted_at,status,due)')
            db.execute('CREATE TABLE opportunities_legacy_v356(note TEXT)')
            db.execute("INSERT INTO opportunities_legacy_v356 VALUES('Keep earlier archive')")
            original = tuple(db.execute('SELECT * FROM opportunities').fetchone())
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'NOT NULL constraint failed: opportunities.creator_id'):
            with self.store.connect() as db:
                db.execute('''INSERT INTO opportunities
                    (id,body,status,region,project_key,created_by,updated_at)
                    VALUES('new','{}','pending','NSW','new',19,'2026-10-21')''')
        self.initialize()
        archive = 'opportunities_legacy_v356_2'
        with self.store.connect() as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM ' + archive).fetchone()), original)
            self.assertEqual(tuple(db.execute('SELECT * FROM historical_parent_view').fetchone()), original)
            self.assertEqual(tuple(db.execute('SELECT * FROM opportunities').fetchone()), original[:10])
            self.assertEqual(db.execute('SELECT note FROM opportunities_legacy_v356').fetchone()[0], 'Keep earlier archive')
            self.assertEqual(db.execute('PRAGMA foreign_key_list(historical_parent_link)').fetchone()['table'], archive)
            for name in ('opportunity_status_due', 'parent_update'):
                self.assertEqual(db.execute('SELECT tbl_name FROM sqlite_master WHERE name=?', (name,)).fetchone()[0], archive)
            self.assertTrue(db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND tbl_name='opportunities' AND name LIKE 'opportunity_status_due%' ").fetchone())
            db.execute('''INSERT INTO opportunities
                (id,body,status,region,project_key,created_by,updated_at)
                VALUES('new','{}','pending','NSW','historical nsw opportunity',19,'2026-10-21')''')
            db.execute("UPDATE opportunities SET revision=revision+1 WHERE id='original'")
            self.assertEqual(db.execute('SELECT COUNT(*) FROM historical_trigger_log').fetchone()[0], 0)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(compatibility.migration_plan(db, self.present(db)), [])
        self.assertEqual(len(self.backups()), 1)
        with closing(sqlite3.connect(self.backups()[0])) as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM opportunities').fetchone()), original)
        self.assertEqual(self.backups()[0].stat().st_mode & 0o777, 0o600)
        with patch.object(schema, '_backup', side_effect=AssertionError('Repeated parent migration')):
            self.initialize()

    def test_minimal_parent_recovers_missing_columns_without_updating_archived_rows(self):
        records = [item('json-author'), item('sql-author', project='Legacy SQL creator')]
        records[1].pop('createdBy')
        with self.store.connect() as db:
            db.execute('CREATE TABLE opportunities(id TEXT PRIMARY KEY,body TEXT NOT NULL,creator_id INTEGER NOT NULL,legacy_note TEXT)')
            for record in records:
                db.execute('INSERT INTO opportunities VALUES(?,?,?,?)',
                           (record['id'], json.dumps(record, indent=2), 29, 'Exact legacy note'))
            db.execute('CREATE TABLE parent_update_log(note TEXT)')
            db.execute('''CREATE TRIGGER historical_update AFTER UPDATE ON opportunities
                BEGIN UPDATE opportunities SET legacy_note='Must not happen' WHERE id=NEW.id;
                INSERT INTO parent_update_log VALUES('Must not happen'); END''')
            original = [tuple(row) for row in db.execute('SELECT * FROM opportunities ORDER BY id')]
        self.initialize()
        with self.store.connect() as db:
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM opportunities_legacy_v356 ORDER BY id')], original)
            self.assertEqual([row['name'] for row in db.execute('PRAGMA table_info(opportunities_legacy_v356)')],
                             ['id', 'body', 'creator_id', 'legacy_note'])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM parent_update_log').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT created_by FROM opportunities WHERE id='json-author'").fetchone()[0], 7)
            self.assertEqual(db.execute("SELECT created_by FROM opportunities WHERE id='sql-author'").fetchone()[0], 29)
            for record in records:
                row = db.execute('SELECT * FROM opportunities WHERE id=?', (record['id'],)).fetchone()
                self.assertEqual(row['body'], json.dumps(record, indent=2))
                self.assertEqual(row['revision'], record['revision'])
                self.assertEqual(row['project_key'], tenders.project_key(record['project']))
                self.assertEqual(row['due'], record['due'])
                self.assertIsNone(row['deleted_at'])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_existing_current_creator_value_wins_over_legacy_and_json_authors(self):
        with self.store.connect() as db:
            db.execute(PARENT_DDL)
            put_parent(db, item())
            db.execute('UPDATE opportunities SET created_by=19,creator_id=29')
        self.initialize()
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT created_by FROM opportunities').fetchone()[0], 19)
            self.assertEqual(db.execute('SELECT creator_id FROM opportunities_legacy_v356').fetchone()[0], 29)
            self.assertEqual(json.loads(db.execute('SELECT body FROM opportunities').fetchone()[0])['createdBy'], 7)

    def test_compatible_optional_parent_metadata_does_not_trigger_a_rebuild(self):
        with self.store.connect() as db:
            db.execute('''CREATE TABLE opportunities (
                id TEXT PRIMARY KEY, body TEXT NOT NULL, optional_creator INTEGER,
                metadata TEXT NOT NULL DEFAULT 'CHECK(not a constraint)')''')
            self.assertEqual(compatibility.migration_plan(db, self.present(db)), [])
        self.initialize()
        with self.store.connect() as db:
            self.assertIn('optional_creator', {row['name'] for row in db.execute('PRAGMA table_info(opportunities)')})
            self.assertNotIn('opportunities_legacy_v356', self.present(db))

    def test_actual_parent_check_unique_foreign_key_and_nullable_constraints_are_planned(self):
        definitions = [
            'id TEXT PRIMARY KEY,body TEXT NOT NULL,status TEXT CHECK(status IN (\'pending\',\'approved\'))',
            'id TEXT PRIMARY KEY,body TEXT NOT NULL,region TEXT,project_key TEXT,UNIQUE(region,project_key)',
            'id TEXT PRIMARY KEY,body TEXT NOT NULL,created_by INTEGER REFERENCES historical_users(id)',
            'id TEXT PRIMARY KEY,body TEXT NOT NULL,deleted_at TEXT NOT NULL',
            'id TEXT PRIMARY KEY,body TEXT NOT NULL,creator_id INTEGER NOT NULL DEFAULT(NULL)',
        ]
        for definition in definitions:
            with self.subTest(definition=definition):
                with self.store.connect() as db:
                    db.execute('DROP TABLE IF EXISTS opportunities')
                    db.execute('CREATE TABLE opportunities(' + definition + ')')
                    self.assertEqual(compatibility.migration_plan(db, self.present(db)), ['opportunities'])

    def test_current_dependency_closure_is_rebound_and_unknown_history_stays_archived(self):
        with self.store.connect() as db:
            db.execute(PARENT_DDL)
            put_parent(db, item())
            db.execute('''CREATE TABLE opportunity_people (
                opportunity_id TEXT NOT NULL REFERENCES opportunities(id),kind TEXT NOT NULL,person_id INTEGER NOT NULL,
                PRIMARY KEY(opportunity_id,kind,person_id))''')
            db.execute("INSERT INTO opportunity_people VALUES('original','assignedUserIds',7)")
            db.execute('''CREATE TABLE opportunity_events (
                event_key TEXT PRIMARY KEY,created_at TEXT NOT NULL,legacy_project TEXT,legacy_kind TEXT,legacy_person INTEGER,
                FOREIGN KEY(legacy_project,legacy_kind,legacy_person) REFERENCES opportunity_people(opportunity_id,kind,person_id))''')
            db.execute("INSERT INTO opportunity_events VALUES('legacy-event','2026-10-21','original','assignedUserIds',7)")
            db.execute('''CREATE TABLE tender_notifications (
                id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,kind TEXT NOT NULL,target_kind TEXT NOT NULL,
                target_id TEXT NOT NULL,title TEXT NOT NULL,message TEXT NOT NULL,due TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,read_at TEXT,event_key TEXT NOT NULL REFERENCES opportunity_events(event_key),
                UNIQUE(user_id,event_key))''')
            db.execute("INSERT INTO tender_notifications VALUES('old-notice',7,'assigned','opportunity','original','Old','Keep message','','2026-10-21',NULL,'legacy-event')")
            db.execute('CREATE TABLE historical_notification_links(notice_id TEXT REFERENCES tender_notifications(id) ON DELETE CASCADE)')
            db.execute("INSERT INTO historical_notification_links VALUES('old-notice')")
            db.execute('CREATE TABLE historical_event_links(event_key TEXT REFERENCES opportunity_events(event_key))')
            db.execute("INSERT INTO historical_event_links VALUES('legacy-event')")
            before = {table: [tuple(row) for row in db.execute('SELECT * FROM ' + table)]
                      for table in ('opportunities', 'opportunity_people', 'opportunity_events', 'tender_notifications')}
        self.initialize()
        with self.store.connect() as db:
            for table, rows in before.items():
                self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM ' + table + '_legacy_v356')], rows)
            self.assertEqual(db.execute('PRAGMA foreign_key_list(opportunity_people)').fetchone()['table'], 'opportunities')
            self.assertEqual(db.execute('PRAGMA foreign_key_list(opportunity_people_legacy_v356)').fetchone()['table'], 'opportunities_legacy_v356')
            self.assertEqual(db.execute('PRAGMA foreign_key_list(historical_notification_links)').fetchone()['table'], 'tender_notifications_legacy_v356')
            self.assertEqual(db.execute('PRAGMA foreign_key_list(historical_event_links)').fetchone()['table'], 'opportunity_events_legacy_v356')
            for table in ('opportunity_events', 'tender_notifications'):
                self.assertEqual(db.execute('PRAGMA foreign_key_list(' + table + ')').fetchall(), [])
            db.execute("INSERT INTO opportunities(id,body,status,region,project_key,updated_at) VALUES('new','{}','pending','NSW','new','2026-10-21')")
            db.execute("INSERT INTO opportunity_people VALUES('new','assignedUserIds',99)")
            db.execute("DELETE FROM opportunity_people WHERE opportunity_id='original'")
            db.execute("DELETE FROM tender_notifications WHERE id='old-notice'")
            self.assertEqual(db.execute('SELECT notice_id FROM historical_notification_links').fetchone()[0], 'old-notice')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(compatibility.migration_plan(db, self.present(db)), [])

    def test_backup_failure_leaves_the_entire_legacy_database_unchanged(self):
        with self.store.connect() as db:
            db.execute(PARENT_DDL)
            put_parent(db, item())
            before = snapshot(db)
        with patch.object(schema, '_backup', side_effect=OSError('Private backup could not be created')):
            with self.assertRaisesRegex(OSError, 'Private backup'):
                self.initialize()
        with self.store.connect() as db:
            self.assertEqual(snapshot(db), before)

    def test_late_index_failure_rolls_back_parent_children_and_metadata(self):
        with self.store.connect() as db:
            db.execute(PARENT_DDL)
            put_parent(db, item())
            db.execute('''CREATE TABLE opportunity_people (
                opportunity_id TEXT REFERENCES opportunities(id),kind TEXT,person_id INTEGER,
                PRIMARY KEY(opportunity_id,kind,person_id))''')
            db.execute("INSERT INTO opportunity_people VALUES('original','assignedUserIds',7)")
            before = snapshot(db)
        with patch.object(schema, '_INDEXES', (*schema._INDEXES, 'CREATE INDEX injected_failure ON opportunities(no_such_column)')):
            with self.assertRaisesRegex(sqlite3.OperationalError, 'no such column'):
                self.initialize()
        with self.store.connect() as db:
            self.assertEqual(snapshot(db), before)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(len(self.backups()), 1)
        with closing(sqlite3.connect(self.backups()[0])) as db:
            db.row_factory = sqlite3.Row
            self.assertEqual(snapshot(db), before)
        self.initialize()

    def test_invalid_missing_column_recovery_rolls_back_without_fabricating_an_author(self):
        with self.store.connect() as db:
            db.execute('CREATE TABLE opportunities(id TEXT PRIMARY KEY,body TEXT NOT NULL,creator_id TEXT NOT NULL)')
            record = item()
            record.pop('createdBy')
            db.execute('INSERT INTO opportunities VALUES(?,?,?)', ('original', json.dumps(record), 'Unresolved old user'))
            before = snapshot(db)
        with self.assertRaisesRegex(UpgradeError, 'createdBy must be an integer or null'):
            self.initialize()
        with self.store.connect() as db:
            self.assertEqual(snapshot(db), before)
        self.assertEqual(len(self.backups()), 1)

    def test_duplicate_legacy_assignment_copy_fails_atomically(self):
        with self.store.connect() as db:
            db.execute(PARENT_DDL)
            put_parent(db, item())
            db.execute('''CREATE TABLE opportunity_people (
                historical_id INTEGER PRIMARY KEY,opportunity_id TEXT REFERENCES opportunities(id),kind TEXT,person_id INTEGER)''')
            db.executemany("INSERT INTO opportunity_people VALUES(?,'original','assignedUserIds',7)", [(1,), (2,)])
            before = snapshot(db)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'UNIQUE constraint failed'):
            self.initialize()
        with self.store.connect() as db:
            self.assertEqual(snapshot(db), before)

    def test_manual_incomplete_parent_plan_is_refused_instead_of_leaving_current_children_on_archive(self):
        with self.store.connect() as db:
            db.execute(PARENT_DDL)
            put_parent(db, item())
            db.execute('''CREATE TABLE opportunity_people (
                opportunity_id TEXT REFERENCES opportunities(id),kind TEXT,person_id INTEGER,
                PRIMARY KEY(opportunity_id,kind,person_id))''')
            before = snapshot(db)
        with self.assertRaisesRegex(UpgradeError, 'still references an archived parent'):
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                compatibility.migrate(db, ['opportunities'])
        with self.store.connect() as db:
            self.assertEqual(snapshot(db), before)

    def test_parent_upgrade_coexists_with_name_only_builder_migration(self):
        with self.store.connect() as db:
            db.execute(PARENT_DDL)
            put_parent(db, item())
            db.execute('CREATE TABLE opportunity_builders(id TEXT PRIMARY KEY,name TEXT NOT NULL,original_contact TEXT NOT NULL)')
            db.execute("INSERT INTO opportunity_builders VALUES('legacy-builder','Historical Builder','Keep historical contact')")
            db.execute('''CREATE TABLE opportunity_people (
                opportunity_id TEXT NOT NULL REFERENCES opportunities(id),kind TEXT NOT NULL,person_id INTEGER NOT NULL,
                builder_id TEXT REFERENCES opportunity_builders(id),PRIMARY KEY(opportunity_id,kind,person_id))''')
            db.execute("INSERT INTO opportunity_people VALUES('original','assignedUserIds',7,'legacy-builder')")
            db.execute('''CREATE TABLE opportunity_events (
                event_key TEXT PRIMARY KEY,created_at TEXT NOT NULL,builder_id TEXT REFERENCES opportunity_builders(id))''')
            db.execute("INSERT INTO opportunity_events VALUES('legacy-event','2026-10-21','legacy-builder')")
            db.execute('CREATE TABLE historical_builder_links(builder_id TEXT REFERENCES opportunity_builders(id) ON DELETE CASCADE)')
            db.execute("INSERT INTO historical_builder_links VALUES('legacy-builder')")
            original = tuple(db.execute('SELECT * FROM opportunity_builders').fetchone())
        self.initialize()
        with self.store.connect() as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM opportunity_builders_legacy_v354').fetchone()), original)
            self.assertEqual(tuple(db.execute('SELECT * FROM opportunity_builders').fetchone()), ('historicalbuilder', 'Historical Builder'))
            self.assertEqual(db.execute('PRAGMA foreign_key_list(historical_builder_links)').fetchone()['table'], 'opportunity_builders_legacy_v354')
            self.assertEqual({row['table'] for row in db.execute('PRAGMA foreign_key_list(opportunity_people_legacy_v356)')},
                             {'opportunities_legacy_v356', 'opportunity_builders_legacy_v354'})
            self.assertEqual(db.execute('PRAGMA foreign_key_list(opportunity_people)').fetchone()['table'], 'opportunities')
            self.assertEqual(db.execute('PRAGMA foreign_key_list(opportunity_events)').fetchall(), [])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(len(self.backups()), 1)
        with patch.object(schema, '_backup', side_effect=AssertionError('Repeated joint migration')):
            self.initialize()

    def test_preexisting_foreign_key_violations_remain_identifiable_on_archives(self):
        # Build an already-invalid historical fixture on a new SQLite database
        # using SQLite's connection default, then enforce FKs for all upgrades.
        # The migration must preserve and report this input, never hide it.
        with closing(sqlite3.connect(self.store.path)) as db:
            db.execute('CREATE TABLE historical_users(id INTEGER PRIMARY KEY)')
            db.execute(PARENT_DDL.replace('creator_id INTEGER NOT NULL', 'creator_id INTEGER NOT NULL REFERENCES historical_users(id)'))
            put_parent(db, item())
            db.execute('CREATE TABLE historical_missing_project(opportunity_id TEXT REFERENCES opportunities(id))')
            db.execute("INSERT INTO historical_missing_project VALUES('unknown-original-project')")
            db.commit()
        with self.store.connect() as db:
            self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            before = {tuple(row) for row in db.execute('PRAGMA foreign_key_check')}
            self.assertEqual(len(before), 2)
        self.initialize()
        with self.store.connect() as db:
            expected = {('opportunities_legacy_v356' if table == 'opportunities' else table, row_id,
                         'opportunities_legacy_v356' if parent == 'opportunities' else parent, key_id)
                        for table, row_id, parent, key_id in before}
            self.assertEqual({tuple(row) for row in db.execute('PRAGMA foreign_key_check')}, expected)
            self.assertEqual(db.execute('PRAGMA foreign_key_list(opportunities)').fetchall(), [])
            self.assertEqual(db.execute('SELECT creator_id FROM opportunities_legacy_v356').fetchone()[0], 7)


class ParentMigrationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        environment = patch.dict(os.environ, {
            'CONEST_DB_PATH': str(root / 'catalog.db'),
            'CONEST_TENDERS_DB_PATH': str(root / 'tenders.db'),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.path = root / 'tenders.db'
        with connect() as db:
            self.admin = dict(db.execute("SELECT id,name,role,team_id FROM users WHERE role='admin' LIMIT 1").fetchone())
            stamp = tenders.timestamp()
            self.team = db.execute('INSERT INTO teams(name,created_at,updated_at) VALUES(?,?,?)',
                                   ('Legacy migration team', stamp, stamp)).lastrowid
            member_id = db.execute('''INSERT INTO users
                (username,name,password_hash,role,team_id,is_active,must_change_password,created_at,updated_at)
                VALUES('parent-migration-member','Assigned member','not-a-login-hash','user',?,1,0,?,?)''',
                (self.team, stamp, stamp)).lastrowid
            self.member = {'id': member_id, 'name': 'Assigned member', 'role': 'user', 'team_id': self.team}
        self.old = item('retired-original', createdBy=self.admin['id'], createdByName=self.admin['name'],
                        assignedTeamIds=[self.team], assignedUserIds=[self.member['id']])
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute(PARENT_DDL)
            put_parent(db, self.old)
            db.execute('''CREATE TABLE opportunity_people (
                opportunity_id TEXT NOT NULL REFERENCES opportunities(id),kind TEXT NOT NULL,person_id INTEGER NOT NULL,
                original_scope TEXT NOT NULL DEFAULT 'Retain assignment metadata',
                PRIMARY KEY(opportunity_id,kind,person_id))''')
            db.executemany('INSERT INTO opportunity_people(opportunity_id,kind,person_id) VALUES(?,?,?)', [
                (self.old['id'], 'assignedTeamIds', self.team), (self.old['id'], 'assignedUserIds', self.member['id']),
            ])
            db.execute('''CREATE TABLE historical_assignment_links (
                opportunity_id TEXT,kind TEXT,person_id INTEGER,
                FOREIGN KEY(opportunity_id,kind,person_id) REFERENCES opportunity_people(opportunity_id,kind,person_id) ON DELETE CASCADE)''')
            db.execute('INSERT INTO historical_assignment_links VALUES(?,?,?)', (self.old['id'], 'assignedUserIds', self.member['id']))
            db.execute('CREATE TABLE historical_parent_links(opportunity_id TEXT REFERENCES opportunities(id) ON DELETE CASCADE, note TEXT)')
            db.execute('INSERT INTO historical_parent_links VALUES(?,?)', (self.old['id'], 'Keep historical link'))
            db.execute('CREATE TABLE legacy_audit_people(id INTEGER PRIMARY KEY)')
            db.execute('INSERT INTO legacy_audit_people VALUES(?)', (self.admin['id'],))
            db.execute('''CREATE TABLE opportunity_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
                actor_id INTEGER NOT NULL REFERENCES legacy_audit_people(id),actor_name TEXT NOT NULL,project TEXT NOT NULL,
                action TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL,original_metadata TEXT NOT NULL)''')
            db.execute('INSERT INTO opportunity_activity VALUES(41,?,?,?,?,?,?,?,?)',
                       (self.old['id'], self.admin['id'], self.admin['name'], self.old['project'], 'Created opportunity',
                        '{"source":"legacy"}', self.old['createdAt'], 'Keep all old audit metadata'))
            db.execute("UPDATE sqlite_sequence SET seq=100 WHERE name='opportunity_activity'")
            db.commit()
        # Reproduce the prior initializer retaining this JSON-backed parent.
        # This is a private fixture, not a bypass used by production code.
        with patch.object(compatibility, 'migration_plan', return_value=[]):
            self.store = tenders.Store(self.path).keep_open()
        self.addCleanup(self.store.close)
        with self.store.connect() as db:
            self.marker = tuple(db.execute('SELECT * FROM settings WHERE id=?', (reset.RESET_KEY,)).fetchone())
            self.membership = [tuple(row) for row in db.execute('SELECT * FROM opportunity_reset_entries ORDER BY kind,record_key')]
            self.reset_history = [tuple(row) for row in db.execute('SELECT * FROM opportunity_reset_history')]
            self.later = item('imported-after-reset', project='Later VIC import', region='VIC', createdBy=self.admin['id'])
            put_parent(db, self.later)
            self.original = snapshot(db)

    def test_create_assign_approve_import_notifications_contributions_and_restart_after_completed_reset(self):
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'NOT NULL constraint failed: opportunities.creator_id'):
            op.save(self.store, {'project': 'Before repair', 'region': 'NSW'}, self.admin)
        repaired = tenders.Store(self.path).keep_open()
        self.addCleanup(repaired.close)
        visible = op.list_opportunities(repaired, {}, self.admin)
        self.assertEqual({record['id'] for record in visible['items']}, {self.later['id']})
        created = op.save(repaired, {
            'project': 'Created after parent repair', 'region': 'NSW', 'due': '2099-12-01',
            'builders': ['New Builder One', 'New Builder Two'], 'workingScope': 'Current scope',
            'assignedTeamIds': [self.team], 'assignedUserIds': [self.member['id']],
        }, self.admin)['opportunity']
        self.assertEqual(created['status'], 'pending')
        approved = op.decide(repaired, {**created, 'decision': 'approved'}, self.member)['opportunity']
        self.assertEqual(approved['status'], 'approved')
        changed = op.update_authority(repaired, {**approved, 'assignedUserIds': []}, self.admin, 'assign')['opportunity']
        self.assertEqual(changed['assignedUserIds'], [])
        notices = op.notifications(repaired, {'pageSize': 100}, self.member)
        self.assertTrue(any(row.get('opportunityId') == created['id'] for row in notices['items']))
        self.assertGreater(notices['unreadCount'], 0)
        self.assertEqual(op.mark_read(repaired, {'all': True}, self.member)['unreadCount'], 0)
        imported = op.import_records(repaired, [
            {'project': self.old['project'], 'region': 'NSW', 'due': '2099-11-30'},
            {'project': 'New import after parent upgrade', 'region': 'VIC'},
        ], self.admin, 'after-parent-upgrade.xlsx', expected_generation=op.generation(repaired))
        self.assertEqual(imported['added'], 2)
        with repaired.connect() as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM settings WHERE id=?', (reset.RESET_KEY,)).fetchone()), self.marker)
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM opportunity_reset_entries ORDER BY kind,record_key')], self.membership)
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM opportunity_reset_history')], self.reset_history)
            for table in ('opportunities', 'opportunity_people', 'opportunity_activity'):
                self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM ' + table + '_legacy_v356')], self.original['rows'][table])
            for table in ('historical_assignment_links', 'historical_parent_links'):
                self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM ' + table)], self.original['rows'][table])
            self.assertEqual(db.execute('PRAGMA foreign_key_list(opportunity_people)').fetchone()['table'], 'opportunities')
            self.assertEqual(db.execute('SELECT MIN(id) FROM opportunity_activity WHERE id>41').fetchone()[0], 101)
            self.assertGreater(db.execute("SELECT COUNT(*) FROM tender_activity WHERE action LIKE '%opportunit%' AND actor_id IN (?,?)",
                                          (self.admin['id'], self.member['id'])).fetchone()[0], 0)
            self.assertTrue(db.execute("SELECT 1 FROM opportunity_activity WHERE opportunity_id='' AND action='Imported opportunities Excel'").fetchone())
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            archive_names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_legacy_v356%'")}
        expected_ids = {record['id'] for record in op.list_opportunities(repaired, {}, self.admin)['items']}
        self.assertEqual(len(expected_ids), 4)
        self.assertNotIn(self.old['id'], expected_ids)
        with patch.object(schema, '_backup', side_effect=AssertionError('Parent migration repeated on restart')):
            reopened = tenders.Store(self.path).keep_open()
        self.addCleanup(reopened.close)
        self.assertEqual({record['id'] for record in op.list_opportunities(reopened, {}, self.admin)['items']}, expected_ids)
        with reopened.connect() as db:
            self.assertEqual({row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_legacy_v356%'")}, archive_names)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
