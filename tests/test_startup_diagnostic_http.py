"""Authorize saved startup diagnostics through the real hosted HTTP adapter.

Every account, session and diagnostic lives in a temporary directory. The
Tender store and opportunity reset are blocked so this recovery route cannot
silently rely on the startup operation it is meant to diagnose.
"""
import atexit
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import passenger_wsgi as wsgi
from conest_app import accounts, opportunity_reset, runtime_health, tenders
from conest_app import startup_diagnostics as diagnostics
from conest_app.database import connect


ENDPOINT = '/api/admin/startup-diagnostics'
REFERENCE = '1234abcdef56'
PRIVATE_CAUSE = 'Permission denied: /private/diagnostic-test/tenders.db'


class StartupDiagnosticHTTPTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.tender_path = self.root / 'must-not-open-tenders.db'
        self.stack.enter_context(patch.dict(os.environ, {
            'CONEST_DB_PATH': str(self.root / 'catalog.db'),
            'CONEST_TENDERS_DB_PATH': str(self.tender_path),
        }))
        self.stack.enter_context(patch.object(diagnostics, '_candidate_directories',
            return_value=[self.root / 'private-diagnostics' / 'test-app']))
        self.stack.enter_context(patch.object(wsgi, '_initialized', False))
        self.stack.enter_context(patch.object(wsgi, '_database_keeper', None))
        self.stack.enter_context(patch.object(wsgi.conest, 'IMPORT_DIR', self.root / 'imports'))
        self.stack.enter_context(patch.object(wsgi.conest, 'EXPORT_DIR', self.root / 'exports'))
        self.stack.enter_context(patch.object(wsgi.conest.ConEstHandler, 'log_message', lambda *_: None))
        self.addCleanup(self._close_test_keeper)
        self.tender_open = self.stack.enter_context(patch.object(tenders, 'get_store',
            side_effect=AssertionError('Diagnostics must not open the Tender database')))
        self.reset = self.stack.enter_context(patch.object(opportunity_reset, 'reset_once',
            side_effect=AssertionError('Diagnostics must not run the opportunity reset')))
        with connect() as db:
            self.admin_id = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()[0]
            self.user_id = db.execute("SELECT id FROM users WHERE role='user' LIMIT 1").fetchone()[0]
            db.execute('UPDATE users SET must_change_password=0 WHERE id IN (?,?)',
                       (self.admin_id, self.user_id))
            self.admin_token = accounts.start_session(db, self.admin_id)
            self.user_token = accounts.start_session(db, self.user_id)

    def _close_test_keeper(self):
        if wsgi._database_keeper is not None:
            atexit.unregister(wsgi._database_keeper.close)
            wsgi._database_keeper.close()

    def request(self, target=ENDPOINT, *, token=None, method='GET', headers=None):
        url = urlsplit(target)
        environ = {
            'REQUEST_METHOD': method, 'PATH_INFO': url.path,
            'QUERY_STRING': url.query, 'wsgi.input': io.BytesIO(),
            'HTTP_HOST': 'localhost', 'REMOTE_ADDR': '127.0.0.1',
        }
        if token:
            environ['HTTP_COOKIE'] = 'conest_session=' + token
        if method not in ('GET', 'HEAD'):
            environ['HTTP_X_CONEST_REQUEST'] = '1'
            environ['HTTP_X_CSRF_TOKEN'] = accounts.csrf_token(token or '')
        for name, value in (headers or {}).items():
            environ['HTTP_' + name.upper().replace('-', '_')] = value
        response = {}

        def start(status, response_headers):
            response['status'] = int(status.split()[0])
            response['headers'] = dict(response_headers)

        previous_tender_calls = self.tender_open.call_count
        raw = b''.join(wsgi.application(environ, start))
        response['raw'] = raw
        response['data'] = json.loads(raw) if raw else None
        if url.path == ENDPOINT:
            self.assertEqual(self.tender_open.call_count, previous_tender_calls,
                             'The diagnostics route opened the Tender store')
            self.reset.assert_not_called()
            self.assertFalse(self.tender_path.exists())
        return response

    def assert_private_response(self, response):
        self.assertEqual(response['headers']['Cache-Control'], 'no-store')
        self.assertEqual(response['headers']['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['headers']['Referrer-Policy'], 'no-referrer')
        self.assertNotIn('ETag', response['headers'])
        self.assertNotIn('Last-Modified', response['headers'])
        self.assertNotIn('Access-Control-Allow-Origin', response['headers'])
        for credential in (self.admin_token, self.user_token,
                           accounts.csrf_token(self.admin_token)):
            self.assertNotIn(credential.encode(), response['raw'])

    def record(self):
        return {
            'reference': REFERENCE,
            'code': 'TENDERS_STARTUP_FAILED',
            'created_at': '2026-10-21T04:00:00Z',
            'exception_type': 'builtins.PermissionError',
            'exception_message': PRIVATE_CAUSE,
            'traceback': 'Traceback (most recent call last):\nPermissionError: ' + PRIVATE_CAUSE,
            'truncated': False,
            'runtime': {'python_executable': '/private/test-app/venv/bin/python'},
        }

    def test_anonymous_and_unknown_sessions_cannot_read_diagnostics(self):
        for token in (None, 'not-a-valid-session'):
            with self.subTest(token_present=bool(token)), patch.object(
                diagnostics, 'read_failure', return_value=self.record()
            ) as reader:
                response = self.request(token=token)
                self.assertEqual(response['status'], 401)
                self.assertFalse(response['data']['success'])
                self.assertNotIn('diagnostic', response['data'])
                self.assertNotIn(PRIVATE_CAUSE.encode(), response['raw'])
                self.assert_private_response(response)
                reader.assert_not_called()

    def test_ordinary_user_is_rejected_before_reference_or_storage_access(self):
        for target in (ENDPOINT, ENDPOINT + '?reference=' + REFERENCE,
                       ENDPOINT + '?reference=../../private'):
            with self.subTest(target=target), patch.object(
                diagnostics, 'read_failure', return_value=self.record()
            ) as reader:
                response = self.request(target, token=self.user_token)
                self.assertEqual(response['status'], 403)
                self.assertNotIn('diagnostic', response['data'])
                self.assertNotIn(PRIVATE_CAUSE.encode(), response['raw'])
                self.assert_private_response(response)
                reader.assert_not_called()

    def test_account_state_is_rechecked_before_diagnostic_access(self):
        for updates, expected in (
            ({'must_change_password': 1, 'is_active': 1, 'role': 'admin'}, 403),
            ({'must_change_password': 0, 'is_active': 0, 'role': 'admin'}, 401),
            ({'must_change_password': 0, 'is_active': 1, 'role': 'user'}, 403),
        ):
            with self.subTest(updates=updates):
                with connect() as db:
                    db.execute('UPDATE users SET must_change_password=?,is_active=?,role=? WHERE id=?',
                               (updates['must_change_password'], updates['is_active'],
                                updates['role'], self.admin_id))
                with patch.object(diagnostics, 'read_failure', return_value=self.record()) as reader:
                    response = self.request(token=self.admin_token)
                    self.assertEqual(response['status'], expected)
                    self.assert_private_response(response)
                    self.assertNotIn('diagnostic', response['data'])
                    reader.assert_not_called()

    def test_admin_can_read_latest_or_exact_record_without_tender_startup(self):
        record = self.record()
        for target, expected in ((ENDPOINT, None),
                                 (ENDPOINT + '?reference=' + REFERENCE, REFERENCE)):
            with self.subTest(reference=expected), patch.object(
                diagnostics, 'read_failure', return_value=record
            ) as reader:
                response = self.request(target, token=self.admin_token,
                                        headers={'Accept-Encoding': 'gzip'})
                self.assertEqual(response['status'], 200)
                self.assertEqual(response['data'], {'success': True, 'diagnostic': record})
                self.assert_private_response(response)
                self.assertNotIn('Content-Encoding', response['headers'])
                self.assertEqual(int(response['headers']['Content-Length']), len(response['raw']))
                reader.assert_called_once_with(expected)

    def test_blank_duplicate_path_and_noncanonical_references_are_bad_requests(self):
        invalid = (
            'reference=', 'reference', 'reference=ABCDEF123456',
            'reference=1234abcdef5', 'reference=1234abcdef567',
            'reference=zzzzzzzzzzzz', 'reference=..%2F..%2Fprivate',
            'reference=%2Fetc%2Fpasswd', 'reference=1234abcdef56%00',
            'reference=1234abcdef56%0A', 'reference=1234abcdef56&reference=',
            'reference=1234abcdef56&reference=1234abcdef56',
        )
        with patch.object(diagnostics, 'read_failure', return_value=self.record()) as reader:
            for query in invalid:
                with self.subTest(query=query):
                    response = self.request(ENDPOINT + '?' + query, token=self.admin_token)
                    self.assertEqual(response['status'], 400)
                    self.assertNotIn('diagnostic', response['data'])
                    self.assert_private_response(response)
            reader.assert_not_called()

    def test_missing_record_returns_private_not_found_response(self):
        with patch.object(diagnostics, 'read_failure', return_value=None) as reader:
            response = self.request(ENDPOINT + '?reference=' + REFERENCE, token=self.admin_token)
        self.assertEqual(response['status'], 404)
        self.assertFalse(response['data']['success'])
        self.assertEqual(response['data']['error_code'], 'STARTUP_DIAGNOSTIC_NOT_FOUND')
        self.assertNotIn('diagnostic', response['data'])
        self.assert_private_response(response)
        reader.assert_called_once_with(REFERENCE)

    def test_mutation_methods_never_read_diagnostics(self):
        with patch.object(diagnostics, 'read_failure', return_value=self.record()) as reader:
            for method in ('POST', 'PATCH', 'PUT', 'DELETE'):
                with self.subTest(method=method):
                    response = self.request(token=self.admin_token, method=method)
                    self.assertIn(response['status'], (403, 404))
                    self.assertNotIn('diagnostic', response['data'])
                    self.assert_private_response(response)
            reader.assert_not_called()

    def test_head_preserves_authorization_and_never_returns_diagnostic_body(self):
        with patch.object(diagnostics, 'read_failure', return_value=self.record()) as reader:
            denied = self.request(method='HEAD')
            self.assertEqual(denied['status'], 401)
            self.assertEqual(denied['raw'], b'')
            self.assert_private_response(denied)
            reader.assert_not_called()
            allowed = self.request(token=self.admin_token, method='HEAD')
            self.assertEqual(allowed['status'], 200)
            self.assertEqual(allowed['raw'], b'')
            self.assertGreater(int(allowed['headers']['Content-Length']), 0)
            self.assert_private_response(allowed)
            reader.assert_called_once_with(None)

    def test_saved_tender_failure_is_available_only_to_admin_and_session_survives(self):
        self.tender_open.side_effect = PermissionError(PRIVATE_CAUSE)
        with self.assertLogs(runtime_health.log, level='ERROR'):
            failed = self.request('/api/tenders/bootstrap', token=self.admin_token)
        self.assertEqual(failed['status'], 503)
        self.assertEqual(failed['data']['error_code'], 'TENDERS_STARTUP_FAILED')
        self.assertRegex(failed['data']['error_reference'], r'^[a-f0-9]{12}$')
        self.assertTrue(failed['data']['diagnostics_available'])
        self.assertNotIn(PRIVATE_CAUSE.encode(), failed['raw'])
        self.assertNotIn(b'Traceback', failed['raw'])
        self.assertNotIn(b'PermissionError', failed['raw'])
        self.assertNotIn(b'python_executable', failed['raw'])
        self.assert_private_response(failed)
        self.tender_open.assert_called_once()

        target = ENDPOINT + '?reference=' + failed['data']['error_reference']
        for token, expected in ((None, 401), (self.user_token, 403)):
            response = self.request(target, token=token)
            self.assertEqual(response['status'], expected)
            self.assertNotIn(PRIVATE_CAUSE.encode(), response['raw'])
            self.assertNotIn(b'Traceback', response['raw'])
            self.assert_private_response(response)

        response = self.request(target, token=self.admin_token)
        self.assertEqual(response['status'], 200, response['data'])
        saved = response['data']['diagnostic']
        self.assertEqual(saved['reference'], failed['data']['error_reference'])
        self.assertEqual(saved['code'], 'TENDERS_STARTUP_FAILED')
        self.assertEqual(saved['exception_type'], 'builtins.PermissionError')
        self.assertIn(PRIVATE_CAUSE, saved['exception_message'])
        self.assertIn('PermissionError', saved['traceback'])
        self.assertIn('Traceback', saved['traceback'])
        self.assertIn('python_executable', saved['runtime'])
        self.assert_private_response(response)
        latest = self.request(token=self.admin_token)
        self.assertEqual(latest['data']['diagnostic']['reference'], saved['reference'])

        session = self.request('/api/auth/session', token=self.admin_token)
        self.assertEqual(session['status'], 200)
        self.assertEqual(session['data']['user']['id'], self.admin_id)
        self.assertEqual(session['data']['csrf_token'], accounts.csrf_token(self.admin_token))
        self.assertTrue(session['headers']['Set-Cookie'].startswith(
            'conest_session=' + self.admin_token + ';'))
        self.tender_open.assert_called_once()
        self.reset.assert_not_called()
        self.assertFalse(self.tender_path.exists())


if __name__ == '__main__':
    unittest.main()
