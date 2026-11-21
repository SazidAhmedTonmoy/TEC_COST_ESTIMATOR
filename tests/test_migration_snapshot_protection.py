"""Migration recovery copies preserve data without plaintext backup files."""
import base64
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from conest_app.data_protection import FILE_MAGIC, ProtectionError, load_key
from conest_app.tenders import _legacy_upgrade_snapshot
from encrypted_backup_fixture import open_backup


class MigrationSnapshotProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env = patch.dict(os.environ, {
            'CONEST_DB_PATH': str(self.root / 'catalog.db'),
            'CONEST_ENCRYPTION_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode(),
            'CONEST_ENCRYPTION_KEY_FILE': '',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.source = sqlite3.connect(self.root / 'tenders.db')
        self.addCleanup(self.source.close)
        self.source.execute('CREATE TABLE submissions(id TEXT PRIMARY KEY, project TEXT, amount REAL)')
        self.source.execute('INSERT INTO submissions VALUES(?,?,?)', ('one', 'Private fixture project', 8123.45))
        self.source.commit()

    def test_each_legacy_tender_snapshot_is_encrypted_and_restorable(self):
        for version in ('v33', 'v34', 'v34b'):
            with self.subTest(version=version):
                plain = self.root / ('tenders.pre-' + version + '.db')
                _legacy_upgrade_snapshot(self.source, plain)
                encrypted = plain.with_name(plain.name + '.enc')
                self.assertFalse(plain.exists())
                content = encrypted.read_bytes()
                self.assertTrue(content.startswith(FILE_MAGIC))
                self.assertNotIn(b'Private fixture project', content)
                if os.name != 'nt':
                    self.assertEqual(encrypted.stat().st_mode & 0o777, 0o600)
                with open_backup(encrypted, purpose='backup:tenders') as saved:
                    self.assertEqual(saved.execute('SELECT * FROM submissions').fetchall(),
                                     [('one', 'Private fixture project', 8123.45)])
                    self.assertEqual(saved.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                before = encrypted.read_bytes()
                _legacy_upgrade_snapshot(self.source, plain)
                self.assertEqual(encrypted.read_bytes(), before)
        self.assertFalse(list(self.root.glob('*.pending')))

    def test_wrong_key_prevents_new_recovery_copy_and_cleans_temporary_plaintext(self):
        load_key(create=True)
        target = self.root / 'tenders.pre-v34.db'
        with patch.dict(os.environ, {'CONEST_ENCRYPTION_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode()}):
            with self.assertRaises(ProtectionError):
                _legacy_upgrade_snapshot(self.source, target)
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name(target.name + '.enc').exists())
        self.assertFalse(list(self.root.glob('*.pending')))
        self.assertEqual(self.source.execute('SELECT COUNT(*) FROM submissions').fetchone()[0], 1)

    def test_historical_plaintext_recovery_copy_is_never_replaced(self):
        target = self.root / 'tenders.pre-v33.db'
        with closing(sqlite3.connect(target)) as saved:
            self.source.backup(saved)
        original = target.read_bytes()
        _legacy_upgrade_snapshot(self.source, target)
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse(target.with_name(target.name + '.enc').exists())


if __name__ == '__main__':
    unittest.main()
