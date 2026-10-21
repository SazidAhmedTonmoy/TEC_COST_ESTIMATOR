"""Private startup capture uses isolated directories and never opens a database."""
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from conest_app import __version__, runtime_health, startup_diagnostics as diagnostics


@unittest.skipUnless(os.name == 'posix', 'Private storage requires POSIX ownership and no-follow primitives')
class StartupDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conest-diagnostic-test-')
        self.root = Path(self.temp.name)
        self.location = self.root / 'private-diagnostics' / 'test-app'
        self.candidates = patch.object(diagnostics, '_candidate_directories', return_value=[self.location])
        self.candidates.start()
        self.environment = patch.dict(os.environ, {
            'CONEST_DB_PATH': str(self.root / 'catalog.db'),
            'CONEST_TENDERS_DB_PATH': str(self.root / 'tenders.db'),
            'UNRELATED_API_SECRET': 'unrelated-environment-secret',
        })
        self.environment.start()
        self.quiet = patch.object(runtime_health.log, 'error')
        self.quiet.start()

    def tearDown(self):
        self.quiet.stop()
        self.environment.stop()
        self.candidates.stop()
        self.temp.cleanup()

    def failure(self):
        local_secret = 'local-variable-value-must-not-be-captured'
        try:
            try:
                raise ValueError('original schema cause')
            except ValueError as cause:
                raise PermissionError('/private/customer/database.db could not open') from cause
        except PermissionError as error:
            return error

    def private_directory(self, location=None):
        location = location or self.location
        location.parent.mkdir(mode=0o700, exist_ok=True)
        location.mkdir(mode=0o700, exist_ok=True)
        return location

    def test_capture_chain_runtime_and_worker_persistence_without_database_access(self):
        reference = '123456789abc'
        with patch.object(diagnostics.sqlite3, 'connect', side_effect=AssertionError('No DB access')):
            self.assertTrue(diagnostics.record_failure(self.failure(), 'TENDERS_STARTUP_FAILED', reference))
            captured = diagnostics.read_failure(reference)
        self.assertEqual(captured['exception_type'], 'builtins.PermissionError')
        self.assertEqual(captured['code'], 'TENDERS_STARTUP_FAILED')
        self.assertIn('ValueError: original schema cause', captured['traceback'])
        self.assertIn('direct cause', captured['traceback'])
        self.assertIn('/private/customer/database.db', captured['traceback'])
        self.assertRegex(captured['created_at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        runtime = captured['runtime']
        self.assertEqual(runtime['python_executable'], sys.executable)
        self.assertEqual(runtime['sqlite_version'], diagnostics.sqlite3.sqlite_version)
        self.assertEqual(runtime['release'], __version__)
        self.assertEqual(runtime['pid'], os.getpid())
        self.assertEqual(runtime['configured_db_path'], str(self.root / 'catalog.db'))
        self.assertEqual(runtime['effective_tenders_db_path'], str(self.root / 'tenders.db'))
        content = json.dumps(captured)
        self.assertNotIn('local-variable-value-must-not-be-captured', content)
        self.assertNotIn('unrelated-environment-secret', content)
        for directory in (self.location, self.location.parent):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.location / (reference + '.json')).stat().st_mode), 0o600)
        script = """import json,sys
from pathlib import Path
from conest_app import startup_diagnostics as d
d._candidate_directories=lambda:[Path(sys.argv[1])]
print(json.dumps(d.read_failure(sys.argv[2])))
"""
        other = subprocess.run([sys.executable, '-c', script, str(self.location), reference],
                               capture_output=True, text=True, timeout=20, check=True)
        self.assertEqual(json.loads(other.stdout), captured)

    def test_readonly_primary_falls_back_and_latest_searches_all_candidates(self):
        primary = self.private_directory()
        fallback = self.root / 'fallback-private' / 'test-app'
        inode = primary.stat().st_ino
        real_open = diagnostics.os.open

        def readonly_open(path, flags, *args, **kwargs):
            directory = kwargs.get('dir_fd')
            if flags & os.O_CREAT and directory is not None and os.fstat(directory).st_ino == inode:
                raise OSError(errno.EROFS, 'Read-only filesystem')
            return real_open(path, flags, *args, **kwargs)

        with patch.object(diagnostics, '_candidate_directories', return_value=[primary, fallback]):
            with patch.object(diagnostics.os, 'open', side_effect=readonly_open):
                self.assertTrue(diagnostics.record_failure(ValueError('first failure'), 'TEST', '000000000001'))
            self.assertTrue((fallback / '000000000001.json').is_file())
            self.assertFalse((primary / '000000000001.json').exists())
            self.assertEqual(diagnostics.read_failure()['reference'], '000000000001')
            self.assertTrue(diagnostics.record_failure(ValueError('new failure'), 'TEST', '000000000002'))
            self.assertEqual(diagnostics.read_failure()['reference'], '000000000002')
            self.assertEqual(diagnostics.read_failure('000000000001')['exception_message'], 'first failure')

    def test_storage_and_logging_failure_never_replace_safe_public_error(self):
        original = self.failure()
        with patch.object(diagnostics.os, 'open', side_effect=OSError(errno.ENOSPC, 'disk full')):
            self.assertFalse(diagnostics.record_failure(original, 'TEST', 'abcdef123456'))
            with patch.object(runtime_health.log, 'error', side_effect=RuntimeError('broken log handler')):
                response = runtime_health.startup_failure(original, 'TENDERS_STARTUP_FAILED')
        self.assertFalse(response['success'])
        self.assertFalse(response['diagnostics_available'])
        self.assertEqual(response['error_code'], 'TENDERS_STARTUP_FAILED')
        self.assertRegex(response['error_reference'], r'^[a-f0-9]{12}$')
        self.assertNotIn('/private/', json.dumps(response))
        self.assertNotIn('PermissionError', json.dumps(response))
        with patch.object(diagnostics, 'record_failure', side_effect=RuntimeError('capture failed')):
            self.assertFalse(runtime_health.startup_failure(original, 'SESSION_STARTUP_FAILED')['diagnostics_available'])
        success = runtime_health.startup_failure(original, 'TENDERS_STARTUP_FAILED')
        self.assertTrue(success['diagnostics_available'])
        self.assertIsNotNone(diagnostics.read_failure(success['error_reference']))
        self.assertNotIn('traceback', success)

    def test_invalid_references_do_no_filesystem_work(self):
        with patch.object(diagnostics, '_candidate_directories', side_effect=AssertionError('No paths for invalid input')):
            for reference in ('', '../123456789abc', '123456789abc.json', 'ABCDEF123456',
                              '123456789ab', '123456789abcd', '123456789abc\n', '/', 7):
                with self.subTest(reference=reference):
                    self.assertIsNone(diagnostics.read_failure(reference))
                    self.assertFalse(diagnostics.record_failure(ValueError('ignored'), 'TEST', reference))
        self.assertFalse(self.location.exists())

    def test_rejects_unsafe_permissions_wrong_owner_and_web_locations(self):
        location = self.private_directory()
        location.parent.chmod(0o755)
        self.assertFalse(diagnostics.record_failure(ValueError('unsafe'), 'TEST', '123456789abc'))
        self.assertIsNone(diagnostics.read_failure())
        self.assertEqual(stat.S_IMODE(location.parent.stat().st_mode), 0o755)
        location.parent.chmod(0o700)
        with patch.object(diagnostics.os, 'geteuid', return_value=os.geteuid() + 1):
            self.assertFalse(diagnostics.record_failure(ValueError('wrong owner'), 'TEST', '123456789abc'))
        with patch.object(diagnostics, 'APP_ROOT', self.root):
            self.assertFalse(diagnostics.record_failure(ValueError('inside app'), 'TEST', '123456789abc'))
        with patch.dict(os.environ, {'DOCUMENT_ROOT': str(self.root)}):
            self.assertFalse(diagnostics.record_failure(ValueError('inside web root'), 'TEST', '123456789abc'))
        with patch.object(diagnostics, 'APP_ROOT', self.root / 'public_html' / 'app'):
            self.assertFalse(diagnostics._outside_web_roots(self.root / 'public_html' / 'logs' / 'app'))
        self.assertEqual(list(location.iterdir()), [])

    def test_rejects_directory_record_and_lock_symlinks_without_touching_target(self):
        outside = self.root / 'outside-private'
        outside.mkdir(mode=0o700)
        self.location.parent.mkdir(mode=0o700)
        self.location.symlink_to(outside, target_is_directory=True)
        self.assertFalse(diagnostics.record_failure(ValueError('unsafe'), 'TEST', '123456789abc'))
        self.assertIsNone(diagnostics.read_failure())
        self.assertEqual(list(outside.iterdir()), [])
        self.location.unlink()
        self.location.mkdir(mode=0o700)
        target = outside / 'keep.txt'
        target.write_text('must stay unchanged')
        target.chmod(0o600)
        (self.location / '123456789abc.json').symlink_to(target)
        self.assertFalse(diagnostics.record_failure(ValueError('unsafe'), 'TEST', '123456789abc'))
        self.assertIsNone(diagnostics.read_failure('123456789abc'))
        (self.location / '.lock').unlink()
        (self.location / '.lock').symlink_to(target)
        self.assertFalse(diagnostics.record_failure(ValueError('unsafe lock'), 'TEST', '123456789abd'))
        self.assertEqual(target.read_text(), 'must stay unchanged')
        alias = self.root / 'ancestor-link'
        alias.symlink_to(outside, target_is_directory=True)
        with patch.object(diagnostics, '_candidate_directories', return_value=[alias / 'private' / 'app']):
            self.assertFalse(diagnostics.record_failure(ValueError('unsafe ancestor'), 'TEST', '123456789abe'))
        self.assertEqual(sorted(path.name for path in outside.iterdir()), ['keep.txt'])

    def test_record_bytes_count_expiry_and_corrupt_files_are_bounded(self):
        large = ValueError('long error \x00 🔎 ' * 12000 + ' final cause')
        self.assertTrue(diagnostics.record_failure(large, 'TEST', '111111111111'))
        self.assertLessEqual((self.location / '111111111111.json').stat().st_size, 64 * 1024)
        self.assertTrue(diagnostics.read_failure('111111111111')['truncated'])
        self.assertIn('final cause', diagnostics.read_failure('111111111111')['traceback'])
        old_time = time.time() - diagnostics.MAX_AGE_SECONDS - 60
        os.utime(self.location / '111111111111.json', (old_time, old_time))
        self.assertIsNone(diagnostics.read_failure('111111111111'))
        for number in range(40):
            self.assertTrue(diagnostics.record_failure(ValueError(str(number)), 'TEST', f'{number:012x}'))
        self.assertEqual(len(list(self.location.glob('*.json'))), 32)
        self.assertFalse((self.location / '111111111111.json').exists())
        self.assertEqual(diagnostics.read_failure()['reference'], f'{39:012x}')
        corrupt = self.location / 'ffffffffffff.json'
        corrupt.write_text('{malformed')
        corrupt.chmod(0o600)
        self.assertEqual(diagnostics.read_failure()['reference'], f'{39:012x}')
        corrupt.write_bytes(b'x' * (diagnostics.MAX_RECORD_BYTES + 1))
        self.assertIsNone(diagnostics.read_failure('ffffffffffff'))
        self.assertTrue(diagnostics.record_failure(ValueError('cleanup'), 'TEST', 'aaaaaaaaaaaa'))
        self.assertFalse(corrupt.exists())
        self.assertLessEqual(len(list(self.location.glob('*.json'))), 32)
        self.assertFalse(list(self.location.glob('.tmp-*')))

    def test_concurrent_processes_write_atomic_private_records_and_preserve_cap(self):
        script = """import sys
from pathlib import Path
from conest_app import startup_diagnostics as d
d._candidate_directories=lambda:[Path(sys.argv[1])]
for number in range(int(sys.argv[2]),int(sys.argv[2])+10):
    assert d.record_failure(ValueError('worker '+str(number)),'TEST',format(number,'012x'))
    record=d.read_failure()
    assert record is not None and isinstance(record['traceback'],str)
"""
        processes = [subprocess.Popen([sys.executable, '-c', script, str(self.location), str(worker * 10)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for worker in range(4)]
        try:
            for process in processes:
                output, error = process.communicate(timeout=25)
                self.assertEqual(process.returncode, 0, output + error)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        files = list(self.location.glob('*.json'))
        self.assertEqual(len(files), 32)
        for path in files:
            record = json.loads(path.read_text())
            self.assertEqual(path.stem, record['reference'])
            self.assertIsNotNone(diagnostics.read_failure(path.stem))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertFalse(list(self.location.glob('.tmp-*')))

    def test_explicit_credentials_are_redacted_but_diagnostic_paths_survive(self):
        failure = RuntimeError('/private/data/catalog.db: password="very secret value", '
                               'api_key=key-123 token=token-123 csrf_token=csrf-123; '
                               'Authorization: Bearer bearer-123; cookie="session=secret"')
        self.assertTrue(diagnostics.record_failure(failure, 'TEST', '123456789abc'))
        record = diagnostics.read_failure()
        text = json.dumps(record)
        for secret in ('very secret value', 'key-123', 'token-123', 'csrf-123', 'bearer-123', 'session=secret'):
            self.assertNotIn(secret, text)
        self.assertIn('/private/data/catalog.db', record['exception_message'])
        self.assertIn('[redacted]', record['traceback'])


if __name__ == '__main__':
    unittest.main()
