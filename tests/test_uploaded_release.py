"""Uploaded-code verification must be independent of application startup/data."""
import ast
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import check_uploaded_release as checker


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/check_uploaded_release.py'


class UploadedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.root = self.base / 'application'
        self.root.mkdir()
        for name in checker.REQUIRED_FILES:
            self.write(name, 'release fixture\n')
        self.write('conest_app/__init__.py', '__version__ = "3.8.7"\nraise RuntimeError("must not execute")\n')
        self.write('app.py', 'raise RuntimeError("must not import the application")\n')
        self.write('conest_app/nested/runtime.py', 'VALUE = 1\n')
        self.write('assets/app.123456abcdef.js', 'console.log("estimator");\n')
        self.write('assets/.htaccess', 'Options -Indexes\n')
        self.write('tenders_web/assets/index-abcdef.js', 'console.log("tenders");\n')

    def write(self, name, text):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def manifest(self):
        return checker.create_manifest(self.root)

    def test_creates_and_verifies_without_importing_application_or_configuration(self):
        private = ['.env', '.env.production', '.htaccess', 'passenger_wsgi.py',
                   'data/catalog.db', 'assets/.env', 'assets/private.db',
                   'conest_app/__pycache__/module.pyc', 'tools/private.env']
        for name in private:
            self.write(name, 'private-test-value\n')
        output = self.base / 'release.json'
        with patch.object(checker, '_digest', wraps=checker._digest) as digest:
            manifest = checker.write_manifest(self.root, output)
            digested = {call.args[0].relative_to(self.root).as_posix() for call in digest.call_args_list}
        self.assertFalse(set(private) & digested)
        self.assertFalse(set(private) & set(manifest['files']))
        self.assertIn('assets/.htaccess', manifest['files'])
        self.assertIn('conest_app/nested/runtime.py', manifest['files'])
        self.assertEqual(json.loads(output.read_text()), manifest)
        self.assertNotIn('private-test-value', output.read_text())
        self.assertEqual(checker.verify_manifest(self.root, manifest), ('3.8.7', len(manifest['files'])))

    def test_same_size_old_version_file_is_rejected(self):
        manifest = self.manifest()
        path = self.root / 'conest_app/__init__.py'
        before = path.read_bytes()
        path.write_bytes(before.replace(b'3.8.7', b'3.8.6'))
        self.assertEqual(len(before), path.stat().st_size)
        with self.assertRaisesRegex(checker.ReleaseCheckError, 'Changed release file: conest_app/__init__.py'):
            checker.verify_manifest(self.root, manifest)

    def test_changed_built_frontend_is_rejected(self):
        manifest = self.manifest()
        self.write('tenders_web/assets/index-abcdef.js', 'console.log("old UI");\n')
        with self.assertRaisesRegex(checker.ReleaseCheckError, 'tenders_web/assets/index-abcdef.js'):
            checker.verify_manifest(self.root, manifest)

    def test_missing_required_source_build_or_manifest_entry_is_rejected(self):
        manifest = self.manifest()
        (self.root / 'tenders_web/index.html').unlink()
        with self.assertRaisesRegex(checker.ReleaseCheckError, 'missing'):
            checker.create_manifest(self.root)
        with self.assertRaisesRegex(checker.ReleaseCheckError, 'Missing release file: tenders_web/index.html'):
            checker.verify_manifest(self.root, manifest)
        del manifest['files']['app.py']
        with self.assertRaisesRegex(checker.ReleaseCheckError, 'omits required'):
            checker.verify_manifest(self.root, manifest)

    def test_version_metadata_must_match_literal_without_executing_code(self):
        manifest = self.manifest()
        manifest['release'] = '3.8.8'
        with self.assertRaisesRegex(checker.ReleaseCheckError, 'expected 3.8.8, received 3.8.7'):
            checker.verify_manifest(self.root, manifest)
        self.write('conest_app/__init__.py', '__version__ = str(3.87)\n')
        with self.assertRaisesRegex(checker.ReleaseCheckError, 'literal'):
            checker.create_manifest(self.root)

    def test_unsafe_paths_and_private_files_are_rejected_before_hash_reads(self):
        manifest = self.manifest()
        for name in ('../.env', '/etc/passwd', 'assets/../.env', 'assets//index.html',
                     'assets\\index.html', '.env', '.htaccess', 'passenger_wsgi.py',
                     'data/catalog.db', 'assets/private.db', 'assets/.env', 'tools/private.env'):
            with self.subTest(path=name):
                changed = copy.deepcopy(manifest)
                changed['files'][name] = '0' * 64
                with patch.object(checker, '_digest', side_effect=AssertionError('Must reject before reading')):
                    with self.assertRaises(checker.ReleaseCheckError):
                        checker.verify_manifest(self.root, changed)

    def test_malformed_manifest_shapes_hashes_and_extra_fields_are_rejected(self):
        manifest = self.manifest()
        invalid = [[], {**manifest, 'format': True}, {**manifest, 'release': 'private-test-value'},
                   {**manifest, 'files': []}, {**manifest, 'private_config': '.env'}]
        broken_hash = copy.deepcopy(manifest)
        broken_hash['files']['app.py'] = 'not-a-hash'
        invalid.append(broken_hash)
        for value in invalid:
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(checker.ReleaseCheckError) as caught:
                    checker.verify_manifest(self.root, value)
                self.assertNotIn('private-test-value', str(caught.exception))

    def test_symlink_to_outside_or_private_target_is_rejected_without_read(self):
        manifest = self.manifest()
        outside = self.base / 'private.js'
        outside.write_text('private-test-value')
        private = self.write('.env', 'private-test-value')
        for target in (outside, private):
            with self.subTest(target_type='outside' if target == outside else 'private'):
                link = self.root / 'assets/linked.js'
                link.symlink_to(target)
                changed = copy.deepcopy(manifest)
                changed['files']['assets/linked.js'] = '0' * 64
                with patch.object(checker, '_digest', wraps=checker._digest) as digest:
                    with self.assertRaises(checker.ReleaseCheckError):
                        checker.verify_manifest(self.root, changed)
                    self.assertNotIn(target, [call.args[0] for call in digest.call_args_list])
                with self.assertRaises(checker.ReleaseCheckError):
                    checker.create_manifest(self.root)
                link.unlink()

    def test_create_output_cannot_modify_application_or_follow_output_symlink(self):
        for output in (self.root / 'manifest.json', self.root / '.env', self.base / '.env'):
            with self.subTest(output_type=output.name):
                with self.assertRaises(checker.ReleaseCheckError):
                    checker.write_manifest(self.root, output)
                self.assertFalse(output.exists())
        private = self.base / 'private.json'
        private.write_text('private-test-value')
        output = self.base / 'manifest.json'
        output.symlink_to(private)
        with self.assertRaises(checker.ReleaseCheckError):
            checker.write_manifest(self.root, output)
        self.assertEqual(private.read_text(), 'private-test-value')

    def test_cli_create_and_stdin_verify_report_safe_release_and_count(self):
        output = self.base / 'release.json'
        result = subprocess.run([sys.executable, str(SCRIPT), 'create', '--root', str(self.root),
                                 '--output', str(output)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Created manifest for release 3.8.7', result.stdout)
        result = subprocess.run([sys.executable, str(SCRIPT), 'verify', '--root', str(self.root)],
                                input=output.read_text(), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Uploaded release 3.8.7 verified', result.stdout)
        self.assertNotIn(str(self.root), result.stdout + result.stderr)

    def test_cli_rejects_duplicate_and_non_json_without_echoing_input(self):
        for body in ('<html>private-test-value</html>', '{"format":1,"format":1}',
                     'x' * (checker.MAX_MANIFEST_BYTES + 1)):
            result = subprocess.run([sys.executable, str(SCRIPT), 'verify', '--root', str(self.root)],
                                    input=body, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertNotIn('private-test-value', result.stderr)
            self.assertNotIn('<html>', result.stderr)

    def test_script_syntax_is_compatible_with_python_39(self):
        ast.parse(SCRIPT.read_text(), feature_version=(3, 9))


if __name__ == '__main__':
    unittest.main()
