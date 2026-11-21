"""Local credential, session, CSRF, SQL input and deployment protection checks."""
import base64
from datetime import datetime, timezone
import http.client
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import zipfile

from conest_app import accounts
from conest_app.database import connect
import support_http as http_support
from tools import check_secrets, install_security_rules


class SecurityHTTPTests(unittest.TestCase):
    request = http_support.HttpPatchTests.request
    tearDown = http_support.HttpPatchTests.tearDown

    def setUp(self):
        keys = patch.dict(os.environ, {
            'CONEST_ENCRYPTION_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode(),
            'CONEST_ENCRYPTION_KEY_FILE': '',
        })
        keys.start()
        self.addCleanup(keys.stop)
        http_support.HttpPatchTests.setUp(self)

    def test_stored_key_never_returns_to_browser(self):
        sentinel = 'local-synthetic-secret-for-regression'
        status, result = self.request('PATCH', '/api/settings', {'gemini_api_key': sentinel})
        self.assertEqual(status, 200, result)
        self.assertNotIn(sentinel, json.dumps(result))
        for path in ('/api/settings', '/api/bootstrap'):
            status, result = self.request('GET', path)
            self.assertEqual(status, 200, result)
            self.assertNotIn(sentinel, json.dumps(result))
        status, result = self.request('GET', '/api/settings/saved-key')
        self.assertEqual(status, 404, result)
        self.assertNotIn('api_key', result)

    def test_sql_metacharacters_are_values_and_sort_is_allowlisted(self):
        payload = "Office'); DROP TABLE users; --"
        status, result = self.request('POST', '/api/projects', {'name': payload})
        self.assertEqual(status, 201, result)
        with connect() as db:
            self.assertEqual(db.execute('SELECT name FROM projects WHERE id=?',
                                       (result['project']['id'],)).fetchone()[0], payload)
            original_users = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        query = urlencode({'q': "' OR 1=1 --", 'sort': 'name; DROP TABLE users; --'})
        for path, expected in (('/api/catalog/search?', 400), ('/api/tenders/opportunities?', 200)):
            status, result = self.request('GET', path + query)
            self.assertEqual(status, expected, result)
        status, result = self.request('GET', '/api/catalog/search?' + urlencode({'q': "' OR 1=1 --"}))
        self.assertEqual(status, 200, result)
        with connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0], original_users)
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')

    def test_login_payload_cannot_bypass_authentication(self):
        self.cookie = ''; self.csrf = ''
        status, result = self.request('POST', '/api/auth/login', {
            'username': "' OR 1=1 --", 'password': 'not-a-valid-test-password'})
        self.assertEqual(status, 401, result)
        self.assertNotIn('csrf_token', result)
        self.assertEqual(self.request('GET', '/api/projects')[0], 401)

    def test_private_source_and_data_routes_are_not_public(self):
        self.cookie = ''; self.csrf = ''
        for path in ('/app.py', '/passenger_wsgi.py', '/.env', '/.git/config',
                     '/conest_app/initial_roster.py', '/data/conest_catalog.db',
                     '/assets/../app.py', '/assets/.htaccess'):
            with self.subTest(path=path):
                status, _ = self.request('GET', path)
                self.assertIn(status, (403, 404))
        for path in ('/api/settings', '/api/settings/saved-key', '/api/backups', '/api/tenders/data'):
            self.assertEqual(self.request('GET', path)[0], 401)

    def test_csrf_and_cross_origin_writes_are_rejected(self):
        status, _ = self.request('PATCH', '/api/settings', {'currency': 'USD'}, csrf=False)
        self.assertEqual(status, 403)
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            client.request('PATCH', '/api/settings', json.dumps({'currency': 'USD'}), {
                'Content-Type': 'application/json', 'Cookie': self.cookie,
                'X-ConEst-Request': '1', 'X-CSRF-Token': self.csrf,
                'Origin': 'https://different-origin.invalid'})
            response = client.getresponse(); response.read()
            self.assertEqual(response.status, 403)
        finally:
            client.close()
        self.assertEqual(self.request('GET', '/api/settings')[1]['settings']['currency'], 'AUD')

    def test_database_constraint_details_are_not_returned(self):
        with patch('app.update_settings', side_effect=sqlite3.IntegrityError('UNIQUE constraint failed: private_table.secret_column')):
            status, result = self.request('PATCH', '/api/settings', {'currency': 'AUD'})
        self.assertEqual(status, 400, result)
        self.assertNotIn('private_table', json.dumps(result))
        self.assertNotIn('secret_column', json.dumps(result))

    def test_unchanged_starter_credentials_are_gated_server_side(self):
        with connect() as db:
            db.execute('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?',
                       (accounts.STARTER_HASH, self.user_id))
        status, result = self.request('GET', '/api/auth/session')
        self.assertEqual(status, 200, result)
        self.assertTrue(result['user']['must_change_password'])
        for path in ('/api/projects', '/api/settings', '/api/tenders/data', '/api/tenders/opportunities'):
            self.assertEqual(self.request('GET', path)[0], 403)
        for path, data_key in (('/api/bootstrap', 'dashboard'), ('/api/tenders/bootstrap', 'data')):
            status, result = self.request('GET', path)
            self.assertEqual(status, 200, result)
            self.assertNotIn(data_key, result)
        self.assertEqual(self.request('PATCH', '/api/auth/profile', {'name': 'Setup incomplete'})[0], 400)
        with connect() as db:
            db.execute('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?',
                       (accounts.password_hash('new-synthetic-test-password'), self.user_id))
        self.assertEqual(self.request('GET', '/api/projects')[0], 200)


class SessionExpiryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        environment = patch.dict(os.environ, {
            'CONEST_DB_PATH': str(Path(self.folder.name) / 'session.db'),
            'CONEST_ENCRYPTION_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode(),
            'CONEST_ENCRYPTION_KEY_FILE': '',
        })
        environment.start(); self.addCleanup(environment.stop)
        with connect() as db:
            self.user_id = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()[0]

    def test_session_has_absolute_expiry_and_hashed_token(self):
        now = int(time.time())
        with connect() as db, patch('conest_app.accounts.time.time', return_value=now):
            token = accounts.start_session(db, self.user_id)
            row = db.execute('SELECT * FROM sessions WHERE token_hash=?', (accounts.token_digest(token),)).fetchone()
            self.assertNotEqual(row['token_hash'], token)
            self.assertEqual(row['expires_at'], now + accounts.SESSION_SECONDS)
        with connect() as db:
            with patch('conest_app.accounts.time.time', return_value=now + accounts.SESSION_SECONDS - 1):
                self.assertIsNotNone(accounts.session_user(db, token))
            with patch('conest_app.accounts.time.time', return_value=now + accounts.SESSION_SECONDS):
                self.assertIsNone(accounts.session_user(db, token))

    def test_zero_expiry_legacy_sessions_are_bounded_from_creation(self):
        now = int(time.time())
        fresh = datetime.fromtimestamp(now - 60, timezone.utc).isoformat()
        expired = datetime.fromtimestamp(now - accounts.SESSION_SECONDS, timezone.utc).isoformat()
        with connect() as db, patch('conest_app.accounts.time.time', return_value=now):
            for token, created in (('recent-legacy-test-session', fresh), ('old-legacy-test-session', expired), ('invalid-legacy-test-session', 'invalid-date')):
                db.execute('INSERT INTO sessions VALUES (?,?,0,?)', (accounts.token_digest(token), self.user_id, created))
            self.assertIsNotNone(accounts.session_user(db, 'recent-legacy-test-session'))
            self.assertIsNone(accounts.session_user(db, 'old-legacy-test-session'))
            self.assertIsNone(accounts.session_user(db, 'invalid-legacy-test-session'))
            accounts.start_session(db, self.user_id)
            self.assertIsNone(db.execute('SELECT 1 FROM sessions WHERE token_hash=?', (accounts.token_digest('old-legacy-test-session'),)).fetchone())

    def test_lifetime_configuration_is_bounded(self):
        for value in ('0', '721', 'twelve', '1.5'):
            with self.subTest(value=value), patch.dict(os.environ, {'CONEST_SESSION_HOURS': value}):
                with self.assertRaises(RuntimeError): accounts._session_seconds()
        with patch.dict(os.environ, {'CONEST_SESSION_HOURS': '2'}):
            self.assertEqual(accounts._session_seconds(), 7200)


class PackagingSecurityTests(unittest.TestCase):
    def test_apache_installer_preserves_passenger_and_is_idempotent(self):
        original = b'# Hosting configuration\nPassengerAppRoot /srv/tec-flow\nPassengerPython /srv/venv/bin/python\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'security').mkdir()
            (root / 'security' / 'apache-access.conf').write_text('Options -Indexes\nRewriteEngine On\n')
            target = root / '.htaccess'; target.write_bytes(original); target.chmod(0o640)
            self.assertTrue(install_security_rules.install(root))
            first = target.read_bytes()
            self.assertTrue(first.startswith(install_security_rules.BEGIN))
            self.assertTrue(first.endswith(original))
            self.assertEqual(target.stat().st_mode & 0o777, 0o640)
            self.assertFalse(install_security_rules.install(root))
            self.assertEqual(target.read_bytes(), first)
            self.assertEqual(first.count(install_security_rules.BEGIN), 1)

    def test_apache_installer_rejects_incomplete_markers(self):
        with self.assertRaises(ValueError):
            install_security_rules.merge_rules(install_security_rules.BEGIN, b'Options -Indexes')

    def test_secret_scanner_reports_locations_without_secret_values(self):
        fake = 'AIza' + 'Z' * 35
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'app.js').write_text('const key = "' + fake + '";\n')
            result = check_secrets.scan(root)
            self.assertEqual(len(result['findings']), 1)
            self.assertNotIn(fake, json.dumps(result))
            self.assertEqual(result['findings'][0], {'path': 'app.js', 'line': 1, 'rule': 'google-api-key'})
            archive = root / 'release.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.write(root / 'app.js', 'assets/app.js')
            result = check_secrets.scan(archive)
            self.assertEqual(result['findings'][0]['path'], 'assets/app.js')
            self.assertNotIn(fake, json.dumps(result))


if __name__ == '__main__':
    unittest.main()
