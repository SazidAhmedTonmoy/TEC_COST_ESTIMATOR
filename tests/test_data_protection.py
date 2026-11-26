"""Security invariants for saved secrets, authenticated backups and recovery."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from conest_app import auto_upgrade, backups, data_protection as protection
from conest_app.database import connect, get_settings, initialize, update_settings
from encrypted_backup_fixture import open_backup


class DataProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / 'catalog.db'
        self.key = base64.urlsafe_b64encode(os.urandom(32)).decode('ascii')
        self.environment = patch.dict(os.environ, {
            'CONEST_DB_PATH': str(self.database),
            'CONEST_TENDERS_DB_PATH': str(self.root / 'tenders.db'),
            'CONEST_ENCRYPTION_KEY': self.key,
            'CONEST_ENCRYPTION_KEY_FILE': '',
            'CONEST_LIGHT_PRICES_DB': str(self.root / 'unused.db'),
        })
        self.environment.start()

    def tearDown(self):
        auto_upgrade._ready.pop(str(self.database), None)
        self.environment.stop()
        self.temporary.cleanup()


    def test_existing_plaintext_key_migrates_and_old_wal_frames_are_checkpointed(self):
        initialize()
        secret = 'legacy-synthetic-secret-must-disappear'
        with connect() as connection:
            connection.execute("INSERT INTO settings(key,value,updated_at) VALUES('gemini_api_key',?,'')", (secret,))
        auto_upgrade._ready.pop(str(self.database), None)
        with connect() as connection:
            self.assertNotIn('gemini_api_key', get_settings(connection))
        self.assertNotIn(secret.encode(), self.database.read_bytes())
        wal = self.database.with_name(self.database.name + '-wal')
        if wal.exists():
            self.assertNotIn(secret.encode(), wal.read_bytes())

    def test_new_backups_are_ciphertext_and_restore_with_original_key(self):
        initialize()
        with connect() as connection:
            update_settings(connection, {'currency': 'AUD'})
        snapshot = backups.create_backup()
        path = backups.backup_path(snapshot['name'])
        self.assertTrue(path.name.endswith('.db.enc'))
        self.assertTrue(path.read_bytes().startswith(protection.FILE_MAGIC))
        self.assertNotIn(b'SQLite format 3', path.read_bytes())
        with closing(sqlite3.connect(path)) as external:
            with self.assertRaises(sqlite3.DatabaseError):
                external.execute('SELECT name FROM sqlite_master').fetchall()
        with connect() as connection:
            update_settings(connection, {'currency': 'USD'})
        backups.restore_backup(snapshot['name'])
        with connect() as connection:
            self.assertEqual(get_settings(connection)['currency'], 'AUD')
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(len(backups.list_backups()), 1)
        self.assertTrue(all(item['encrypted'] for item in backups.list_backups()))
        self.assertFalse(list(backups.folder().glob('.snapshot-*')))
        self.assertFalse(list(backups.folder().glob('.restore-*')))

    def test_tender_backup_preserves_rows_and_rejects_catalog_purpose(self):
        path = self.root / 'tenders.db'
        with closing(sqlite3.connect(path)) as connection:
            connection.execute('CREATE TABLE proof(value TEXT)')
            connection.execute('INSERT INTO proof VALUES (?)', ('synthetic builder contact',))
            connection.commit()
        item = backups.create_tender_backup()
        encrypted = backups.backup_path(item['name'])
        with open_backup(encrypted, purpose='backup:tenders') as snapshot:
            self.assertEqual(snapshot.execute('SELECT value FROM proof').fetchone()[0], 'synthetic builder contact')
        with self.assertRaises(protection.ProtectionError):
            protection.verify_encrypted_file(encrypted, purpose='backup:catalog')

    def test_modified_backup_never_publishes_plaintext_or_restores_database(self):
        initialize()
        item = backups.create_backup()
        path = backups.backup_path(item['name'])
        altered = bytearray(path.read_bytes())
        altered[-1] ^= 1
        path.write_bytes(altered)
        destination = self.root / 'unauthenticated.db'
        with self.assertRaises(protection.ProtectionError):
            protection.decrypt_file(path, destination, purpose='backup:catalog')
        self.assertFalse(destination.exists())
        self.assertFalse(list(self.root.glob('.authenticated-restore-*')))
        with connect() as connection:
            before = list(connection.execute('SELECT key,value FROM settings'))
        with self.assertRaises(protection.ProtectionError):
            backups.restore_backup(item['name'])
        with connect() as connection:
            self.assertEqual([tuple(row) for row in before], [tuple(row) for row in connection.execute('SELECT key,value FROM settings')])

    def test_wrong_or_missing_key_cannot_replace_previous_backup(self):
        initialize()
        item = backups.create_backup()
        previous = backups.backup_path(item['name']).read_bytes()
        with patch.dict(os.environ, {'CONEST_ENCRYPTION_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode()}):
            with self.assertRaises(protection.ProtectionError):
                backups.create_backup()
            with self.assertRaises(protection.ProtectionError):
                backups.restore_backup(item['name'])
        self.assertEqual(backups.backup_path(item['name']).read_bytes(), previous)
        self.assertEqual([entry['name'] for entry in backups.list_backups()], [item['name']])

    def test_atomic_publish_failure_keeps_previous_backup_and_no_orphan_metadata(self):
        initialize()
        previous = backups.create_backup()
        replace = os.replace
        calls = 0
        def fail_final_publish(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('Synthetic publication failure')
            return replace(source, destination)
        with patch('conest_app.backups.os.replace', side_effect=fail_final_publish):
            with self.assertRaises(OSError):
                backups.create_backup()
        self.assertEqual([entry['name'] for entry in backups.list_backups()], [previous['name']])
        self.assertEqual(len(list(backups.folder().glob('*.db.json'))), 1)
        self.assertFalse(list(backups.folder().glob('*.pending')))

    def test_legacy_plaintext_backup_restore_removes_retired_secret(self):
        initialize()
        legacy = backups.folder() / 'legacy.db'
        with connect() as source, closing(sqlite3.connect(legacy)) as destination:
            source.backup(destination)
            destination.execute("INSERT INTO settings(key,value,updated_at) VALUES('gemini_api_key',?,'')", ('legacy-test-secret',))
            destination.commit()
        backups.restore_backup(legacy.name)
        with connect() as connection:

            self.assertIsNone(connection.execute("SELECT value FROM settings WHERE key='gemini_api_key'").fetchone())

    def test_default_key_provisioning_is_private_atomic_and_missing_key_fails_closed(self):
        home = self.root / 'service-home'
        home.mkdir()
        with patch.dict(os.environ, {'CONEST_ENCRYPTION_KEY': ''}), patch.object(Path, 'home', return_value=home):
            with ThreadPoolExecutor(max_workers=8) as executor:
                keys = list(executor.map(lambda _: protection.load_key(create=True), range(16)))
            self.assertEqual(len(set(keys)), 1)
            path = protection.key_file_path()
            self.assertNotIn(protection.ROOT, path.parents)
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            path.unlink()
            with self.assertRaises(protection.ProtectionError):
                protection.load_key(create=True)
            self.assertFalse(path.exists())

    def test_invalid_keys_markers_and_webroot_key_paths_fail_closed(self):
        for value in ('not-base64', base64.urlsafe_b64encode(b'too short').decode()):
            with self.subTest(value=value), patch.dict(os.environ, {'CONEST_ENCRYPTION_KEY': value}):
                with self.assertRaises(protection.ProtectionError):
                    protection.load_key(create=True)
        with patch.dict(os.environ, {'CONEST_ENCRYPTION_KEY': '', 'CONEST_ENCRYPTION_KEY_FILE': str(protection.ROOT / 'bad.key')}):
            with self.assertRaises(protection.ProtectionError):
                protection.key_file_path()
        for value in ([], None, {}, {'version': 1, 'key_id': 'invalid'}):
            protection._marker_path().write_text(json.dumps(value))
            with self.subTest(marker=value), self.assertRaises(protection.ProtectionError):
                protection.load_key(create=True)

    def test_database_fingerprint_survives_loss_of_sidecar_marker(self):
        initialize()
        protection._marker_path().unlink()
        with patch.dict(os.environ, {'CONEST_ENCRYPTION_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode()}):
            with self.assertRaises(protection.ProtectionError):
                protection.load_key(create=True)
        self.assertFalse(protection._marker_path().exists())
        self.assertEqual(protection.key_identifier(protection.load_key(create=True)),
                         protection._read_marker(protection._marker_path()))

    def test_streaming_file_round_trip_refuses_overwrite_and_cross_purpose(self):
        source = self.root / 'large.db'
        contents = os.urandom(protection.CHUNK_SIZE * 2 + 47)
        source.write_bytes(contents)
        encrypted = self.root / 'large.db.enc'
        restored = self.root / 'restored.db'
        protection.encrypt_file(source, encrypted, purpose='backup:catalog')
        protection.decrypt_file(encrypted, restored, purpose='backup:catalog')
        self.assertEqual(restored.read_bytes(), contents)
        with self.assertRaises(FileExistsError):
            protection.decrypt_file(encrypted, restored, purpose='backup:catalog')
        self.assertEqual(restored.read_bytes(), contents)
        with self.assertRaises(protection.ProtectionError):
            protection.decrypt_file(encrypted, self.root / 'wrong.db', purpose='backup:tenders')



if __name__ == '__main__':
    unittest.main()
