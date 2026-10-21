"""Exercise concurrent WAL users and deterministic shared-store ownership."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import gc
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import weakref

from conest_app import backups, opportunities, tenders
from conest_app.database import connect


class TenderLifetimeTests(unittest.TestCase):
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
            self.actor = dict(db.execute("SELECT id,name,role FROM users WHERE role='admin' LIMIT 1").fetchone())

    def tearDown(self):
        tenders.close_store()
        self.environment.stop()
        self.temp.cleanup()

    def test_keeper_close_and_replacement_release_the_connection(self):
        store = tenders.get_store()
        keeper = store._database_keeper
        self.assertIsNotNone(keeper)
        self.assertFalse(keeper.in_transaction)
        store.close()
        store.close()  # Closing twice is harmless.
        with self.assertRaises(sqlite3.ProgrammingError):
            keeper.execute('SELECT 1')
        store.keep_open()
        keeper = store._database_keeper
        reference = weakref.ref(store)
        tenders._store = None
        del store
        gc.collect()
        self.assertIsNone(reference())
        with self.assertRaises(sqlite3.ProgrammingError):
            keeper.execute('SELECT 1')

    def test_concurrent_reads_writes_backups_and_checkpoint_preserve_wal(self):
        store = tenders.get_store()
        items = [opportunities.save(store, {
            'project': f'Concurrent WAL project {number}', 'region': 'NSW', 'due': '2099-03-04',
            'builders': ['Concurrent builder'],
        }, self.actor)['opportunity'] for number in range(2)]
        wal = Path(str(store.path) + '-wal')
        original_inode = wal.stat().st_ino

        def writer(item):
            for number in range(25):
                item = opportunities.save(store, {**item, 'remarks': f'Committed update {number}'}, self.actor)['opportunity']
            return item

        def reader():
            for number in range(45):
                detail = opportunities.detail(store, items[number % 2]['id'], self.actor)
                self.assertEqual(detail['opportunity']['status'], 'pending')
                with store.connect() as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunities').fetchone()[0], 56)
            return True

        def inbox():
            for _ in range(25):
                notices = opportunities.notifications(store, {'pageSize': 100}, self.actor)
                opportunities.mark_read(store, {'ids': [n['id'] for n in notices['items']]}, self.actor)
            return True

        def backup_and_checkpoint():
            for _ in range(10):
                result = backups.create_tender_backup('manual', self.actor['id'])
                snapshot = store.path.parent / 'tender_backups' / result['name']
                with closing(sqlite3.connect(snapshot)) as db:
                    self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                with store.connect() as db:
                    db.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchall()
            return True

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(writer, item) for item in items]
            futures.extend([pool.submit(reader), pool.submit(reader), pool.submit(inbox), pool.submit(backup_and_checkpoint)])
            completed = [future.result(timeout=45) for future in futures]
        self.assertEqual([item['revision'] for item in completed[:2]], [25, 25])
        self.assertEqual(wal.stat().st_ino, original_inode, 'The attached WAL must not be unlinked/replaced between requests.')
        with store.connect() as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall()[0][0], 'ok')
            for item in items:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM opportunity_activity WHERE opportunity_id=? AND action='Updated opportunity'", (item['id'],)).fetchone()[0], 25)
        path = store.path
        tenders.close_store()
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM opportunities').fetchone()[0], 56)

    def test_repeated_shared_store_shutdown_and_restart_preserve_data(self):
        store = tenders.get_store()
        item = opportunities.save(store, {'project': 'Restart lifecycle', 'region': 'VIC'}, self.actor)['opportunity']
        for number in range(5):
            tenders.close_store()
            store = tenders.get_store()
            current = opportunities.detail(store, item['id'], self.actor)['opportunity']
            item = opportunities.save(store, {**current, 'remarks': f'Restart {number}'}, self.actor)['opportunity']
            with store.connect() as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(item['revision'], 5)


if __name__ == '__main__':
    unittest.main()
