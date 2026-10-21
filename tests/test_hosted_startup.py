"""Run the real Passenger adapter with isolated databases and startup failures."""
import atexit
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from zoneinfo import ZoneInfoNotFoundError

import passenger_wsgi as wsgi
from conest_app import __version__, accounts, tenders
from conest_app.database import connect
from conest_app import runtime_health


class HostedStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {
            'CONEST_DB_PATH': str(root / 'catalog.db'),
            'CONEST_TENDERS_DB_PATH': str(root / 'tenders.db'),
        })
        self.environment.start()
        tenders.close_store()
        self.previous_initialized = wsgi._initialized
        self.previous_keeper = wsgi._database_keeper
        wsgi._initialized = False
        wsgi._database_keeper = None
        self.quiet = patch.object(wsgi.conest.ConEstHandler, 'log_message', lambda *_args: None)
        self.quiet.start()
        with connect() as db:
            identifier = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()[0]
            db.execute('UPDATE users SET must_change_password=0 WHERE id=?', (identifier,))
            self.token = accounts.start_session(db, identifier)

    def tearDown(self):
        tenders.close_store()
        if wsgi._database_keeper is not None:
            atexit.unregister(wsgi._database_keeper.close)
            wsgi._database_keeper.close()
        wsgi._database_keeper = self.previous_keeper
        wsgi._initialized = self.previous_initialized
        self.quiet.stop()
        self.environment.stop()
        self.temp.cleanup()

    def request(self, target, signed_in=False, method='GET'):
        url = urlsplit(target)
        environ = {
            'REQUEST_METHOD': method, 'PATH_INFO': url.path,
            'QUERY_STRING': url.query, 'wsgi.input': io.BytesIO(),
            'HTTP_HOST': 'localhost', 'REMOTE_ADDR': '127.0.0.1',
        }
        if signed_in:
            environ['HTTP_COOKIE'] = 'conest_session=' + self.token
        response = {}

        def start(status, headers):
            response['status'] = int(status.split()[0])
            response['headers'] = dict(headers)

        raw = b''.join(wsgi.application(environ, start))
        response['raw'] = raw
        response['data'] = json.loads(raw) if raw else None
        return response

    def assert_safe_failure(self, response, code):
        self.assertEqual(response['status'], 503)
        data = response['data']
        self.assertFalse(data['success'])
        self.assertEqual(data['error_code'], code)
        self.assertRegex(data['error_reference'], r'^[a-f0-9]{12}$')
        self.assertIn(data['error_reference'], data['error'])
        self.assertNotIn('/private/', data['error'])
        self.assertNotIn('SECRET', data['error'])
        self.assertEqual(response['headers']['Cache-Control'], 'no-store')
        self.assertEqual(int(response['headers']['Content-Length']), len(response['raw']))

    def test_passenger_initialization_failure_returns_safe_json_and_retries(self):
        with patch.object(wsgi, '_ensure_initialized', side_effect=PermissionError('/private/SECRET/database.db')):
            with self.assertLogs(runtime_health.log, level='ERROR') as logged:
                response = self.request('/api/tenders/bootstrap', signed_in=True)
        self.assert_safe_failure(response, 'SESSION_STARTUP_FAILED')
        self.assertIn('/private/SECRET/database.db', '\n'.join(logged.output))
        self.assertEqual(self.request('/api/tenders/bootstrap', signed_in=True)['status'], 200)

    def test_passenger_import_failure_and_head_have_valid_responses(self):
        failure = ModuleNotFoundError('SECRET production import missing')
        with patch.object(wsgi, '_startup_import_error', failure):
            with self.assertLogs(runtime_health.log, level='ERROR'):
                response = self.request('/api/auth/session')
                head = self.request('/api/auth/session', method='HEAD')
        self.assert_safe_failure(response, 'SESSION_STARTUP_FAILED')
        self.assertEqual(head['status'], 503)
        self.assertEqual(head['raw'], b'')
        self.assertGreater(int(head['headers']['Content-Length']), 0)

    def test_tender_failure_keeps_session_and_authentication_rules(self):
        with patch.object(tenders, 'get_store', side_effect=PermissionError('/private/SECRET/tenders.db')):
            with self.assertLogs(runtime_health.log, level='ERROR'):
                failed = self.request('/api/tenders/bootstrap', signed_in=True)
            self.assert_safe_failure(failed, 'TENDERS_STARTUP_FAILED')
            self.assertEqual(self.request('/api/tenders/bootstrap')['status'], 401)
            self.assertEqual(self.request('/api/auth/session', signed_in=True)['status'], 200)
        recovered = self.request('/api/tenders/bootstrap', signed_in=True)
        self.assertEqual(recovered['status'], 200)
        self.assertTrue(recovered['data']['data']['submissions'])
        self.assertEqual(recovered['headers']['X-ConEst-Adapter'], __version__)

    def test_readiness_checks_tenders_when_catalog_alone_is_healthy(self):
        with patch.object(tenders, 'get_store', side_effect=PermissionError('/private/SECRET/tenders.db')):
            self.assertEqual(self.request('/api/health')['status'], 200)
            with self.assertLogs(runtime_health.log, level='ERROR'):
                deep = self.request('/api/health?check=tenders')
        self.assert_safe_failure(deep, 'TENDERS_STARTUP_FAILED')

    def test_readiness_is_private_and_does_not_change_generation(self):
        store = tenders.get_store()
        with store.connect() as db:
            before = db.execute('SELECT value FROM opportunity_generation').fetchone()[0]
        response = self.request('/api/health?check=tenders')
        self.assertEqual(response['status'], 200, response['data'])
        self.assertEqual(response['data']['checks'], {
            'tenders': 'ok', 'opportunities': 'ok', 'timezones': 'ok', 'sqlite': 'ok',
        })
        self.assertNotIn(str(store.path), response['raw'].decode())
        self.assertNotIn('submissions', response['data'])
        with store.connect() as db:
            self.assertEqual(db.execute('SELECT value FROM opportunity_generation').fetchone()[0], before)
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')

    def test_missing_timezone_or_sqlite_support_is_not_a_false_healthy_check(self):
        for target, failure in [
            ('ZoneInfo', ZoneInfoNotFoundError('SECRET unavailable timezone path')),
            ('check_sqlite_runtime', RuntimeError('SECRET missing SQLite JSON')),
        ]:
            with self.subTest(target=target), patch.object(runtime_health, target, side_effect=failure):
                with self.assertLogs(runtime_health.log, level='ERROR'):
                    response = self.request('/api/health?check=tenders')
                self.assert_safe_failure(response, 'TENDERS_STARTUP_FAILED')


if __name__ == '__main__':
    unittest.main()
