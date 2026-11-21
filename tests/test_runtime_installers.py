"""Preserve host bootstrap settings while installing current security/runtime."""
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from tools import install_security_rules as apache
from tools import install_wsgi_runtime as wsgi


class RuntimeInstallerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / 'conest_app').mkdir()
        (self.root / 'conest_app' / 'wsgi_runtime.py').write_text('application = object()\n')
        self.target = self.root / 'passenger_wsgi.py'

    def test_host_bootstrap_is_preserved_and_current_application_wins(self):
        original = b"HOST_CONFIGURATION = 'preserved'\ndef application(environ, start_response):\n    return [b'old']\n"
        self.target.write_bytes(original)
        self.assertTrue(wsgi.install(self.root))
        installed = self.target.read_bytes()
        self.assertTrue(installed.startswith(original))
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        runtime = ModuleType('conest_app.wsgi_runtime'); runtime.application = object()
        namespace = {}
        with patch.dict(sys.modules, {'conest_app.wsgi_runtime': runtime}):
            exec(compile(installed, str(self.target), 'exec'), namespace)
        self.assertEqual(namespace['HOST_CONFIGURATION'], 'preserved')
        self.assertIs(namespace['application'], runtime.application)
        self.assertFalse(wsgi.install(self.root))
        self.assertEqual(self.target.read_bytes(), installed)

    def test_existing_managed_delegation_moves_after_host_overrides(self):
        original = b"HOST_CONFIGURATION = 'preserved'\n"
        previous = wsgi.merge_runtime(original) + b'application = None\n'
        self.target.write_bytes(previous)
        self.assertTrue(wsgi.install(self.root))
        result = self.target.read_bytes()
        self.assertTrue(result.startswith(original + b'application = None\n'))
        self.assertEqual(result.count(wsgi.BEGIN), 1)
        self.assertGreater(result.index(wsgi.DELEGATION), result.index(b'application = None'))
        self.assertFalse(wsgi.install(self.root))

    def test_invalid_host_syntax_is_left_untouched_without_echoing_source(self):
        original = b"HOST_CONFIGURATION = 'private-value-do-not-echo\n"
        self.target.write_bytes(original)
        with self.assertRaises(ValueError) as caught:
            wsgi.install(self.root)
        self.assertNotIn('private-value', str(caught.exception))
        self.assertEqual(self.target.read_bytes(), original)

    def test_missing_runtime_does_not_change_host_file(self):
        original = b'application = None\n'; self.target.write_bytes(original)
        (self.root / 'conest_app' / 'wsgi_runtime.py').unlink()
        with self.assertRaises(ValueError): wsgi.install(self.root)
        self.assertEqual(self.target.read_bytes(), original)

    def test_new_install_gets_root_path_and_current_runtime(self):
        self.assertTrue(wsgi.install(self.root))
        result = self.target.read_bytes()
        self.assertIn(b'sys.path.insert', result)
        self.assertIn(wsgi.DELEGATION, result)
        self.assertFalse(wsgi.install(self.root))

    def test_apache_protection_precedes_static_file_bypass_and_moves_old_block(self):
        original = b'PassengerAppRoot /srv/tec-flow\r\nRewriteCond %{REQUEST_FILENAME} -f\r\nRewriteRule ^ - [L]\r\n'
        rules = b'RewriteEngine On\nRewriteRule ^data/ - [F,L]\n'
        first = apache.merge_rules(original, rules)
        self.assertTrue(first.startswith(apache.BEGIN))
        self.assertTrue(first.endswith(original))
        self.assertLess(first.index(b'RewriteRule ^data/'), first.index(b'RewriteRule ^ - [L]'))
        self.assertEqual(apache.merge_rules(first, rules), first)
        old_append = original + apache.BEGIN + b'\nold rules\n' + apache.END + b'\n'
        self.assertEqual(apache.merge_rules(old_append, rules), first)


if __name__ == '__main__':
    unittest.main()
