"""Deployment checks must not certify an unrelated shell Python."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


selector = load_tool('select_python')
runtime = load_tool('check_runtime')


class RuntimeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conest-python-selection-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def python(self, relative='venv/bin/python'):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(sys.executable)
        return path

    def select(self, environment=None, strict=True):
        return selector.select_interpreter(
            self.root, {} if environment is None else environment,
            sys.executable, require_configured=strict)

    def test_missing_explicit_interpreter_never_falls_back(self):
        self.python()
        with self.assertRaisesRegex(selector.InterpreterSelectionError, 'no fallback'):
            self.select({'CONEST_PYTHON': '/definitely/missing/python'})

    def test_missing_passenger_interpreter_never_falls_back(self):
        self.python()
        (self.root / '.htaccess').write_text('PassengerPython /definitely/missing/python\n')
        with self.assertRaisesRegex(selector.InterpreterSelectionError, 'PassengerPython'):
            self.select()

    def test_strict_mode_rejects_a_local_venv_and_shell_guess(self):
        self.python()
        with self.assertRaisesRegex(selector.InterpreterSelectionError, 'SSH shell Python'):
            self.select({'VIRTUAL_ENV': str(self.root / 'venv')})

    def test_passenger_quoted_path_preserves_virtualenv_symlink(self):
        interpreter = self.python('virtual env/bin/python')
        (self.root / '.htaccess').write_text(
            'PassengerPython "{}" # managed by host\n'.format(interpreter))
        path, source, configured = self.select()
        self.assertEqual(path, interpreter)
        self.assertNotEqual(path, interpreter.resolve())
        self.assertIn('PassengerPython', source)
        self.assertTrue(configured)

    def test_wsgi_reexec_supersedes_passenger_bootstrap_without_execution(self):
        interpreter = self.python()
        marker = self.root / 'must-not-be-created'
        (self.root / '.htaccess').write_text('PassengerPython /old/bootstrap/python\n')
        (self.root / 'passenger_wsgi.py').write_text(
            'import os, sys\nINTERP = {!r}\n'
            'open({!r}, "w").write("wrong")\n'
            'if sys.executable != INTERP:\n'
            '    os.execl(INTERP, INTERP, *sys.argv)\n'
            .format(str(interpreter), str(marker)))
        path, source, configured = self.select()
        self.assertEqual(path, interpreter)
        self.assertIn('interpreter override', source)
        self.assertTrue(configured)
        self.assertFalse(marker.exists())

    def test_unused_interp_name_does_not_override_passenger(self):
        interpreter = self.python()
        (self.root / '.htaccess').write_text('PassengerPython {}\n'.format(interpreter))
        (self.root / 'passenger_wsgi.py').write_text('INTERP = "/unused/python"\n')
        self.assertEqual(self.select()[0], interpreter)

    def test_exec_in_unused_function_does_not_override_passenger(self):
        interpreter = self.python()
        (self.root / '.htaccess').write_text('PassengerPython {}\n'.format(interpreter))
        (self.root / 'passenger_wsgi.py').write_text(
            'import os, sys\nINTERP = "/unused/python"\n'
            'def future_upgrade():\n'
            '    os.execl(INTERP, INTERP, *sys.argv)\n')
        self.assertEqual(self.select()[0], interpreter)

    def test_exec_in_false_condition_is_not_treated_as_active_override(self):
        interpreter = self.python()
        (self.root / '.htaccess').write_text('PassengerPython {}\n'.format(interpreter))
        (self.root / 'passenger_wsgi.py').write_text(
            'import os, sys\nINTERP = {!r}\n'
            'if False:\n    os.execl(INTERP, INTERP, *sys.argv)\n'
            .format(str(interpreter)))
        with self.assertRaisesRegex(selector.InterpreterSelectionError, 'conditional'):
            self.select()

    def test_exec_alias_is_recognized_in_a_canonical_guard(self):
        interpreter = self.python()
        (self.root / 'passenger_wsgi.py').write_text(
            'from os import execl as restart\nimport sys\nINTERP = {!r}\n'
            'if sys.executable != INTERP:\n'
            '    restart(INTERP, INTERP, *sys.argv)\n'.format(str(interpreter)))
        self.assertEqual(self.select()[0], interpreter)

    def test_conditional_interp_reassignment_requires_explicit_selection(self):
        interpreter = self.python()
        (self.root / 'passenger_wsgi.py').write_text(
            'import os, sys\nINTERP = {!r}\n'
            'if os.environ.get("OLD_ENV"):\n    INTERP = "/older/python"\n'
            'if sys.executable != INTERP:\n'
            '    os.execl(INTERP, INTERP, *sys.argv)\n'.format(str(interpreter)))
        with self.assertRaisesRegex(selector.InterpreterSelectionError, 'dynamically'):
            self.select()

    def test_class_body_exec_requires_explicit_selection(self):
        interpreter = self.python()
        (self.root / 'passenger_wsgi.py').write_text(
            'import os, sys\nINTERP = {!r}\n'
            'class Bootstrap:\n    os.execl(INTERP, INTERP, *sys.argv)\n'
            .format(str(interpreter)))
        with self.assertRaisesRegex(selector.InterpreterSelectionError, 'conditional or dynamic'):
            self.select()

    def test_dynamic_reexec_requires_explicit_selection(self):
        interpreter = self.python()
        (self.root / 'passenger_wsgi.py').write_text(
            'import os\nINTERP = os.environ["PYTHON"]\n'
            'os.execl(INTERP, INTERP)\n')
        with self.assertRaisesRegex(selector.InterpreterSelectionError, 'dynamically'):
            self.select()
        self.assertEqual(self.select({'CONEST_PYTHON': str(interpreter)})[0], interpreter)

    def test_conflicting_passenger_paths_are_not_silently_guessed(self):
        interpreter = self.python()
        (self.root / '.htaccess').write_text(
            'PassengerPython {}\nPassengerPython /another/python\n'.format(interpreter))
        with self.assertRaisesRegex(selector.InterpreterSelectionError, 'Multiple'):
            self.select()

    def test_existing_local_helper_fallback_is_available_but_unconfirmed(self):
        interpreter = self.python()
        path, source, configured = self.select(strict=False)
        self.assertEqual(path, interpreter)
        self.assertEqual(source, 'local venv')
        self.assertFalse(configured)

    def test_installer_stops_before_pip_when_preflight_fails(self):
        tools = self.root / 'tools'
        tools.mkdir()
        for filename in ('select_python.py', 'install_runtime.sh'):
            shutil.copyfile(ROOT / 'tools' / filename, tools / filename)
        calls = self.root / 'calls.txt'
        interpreter = self.root / 'selected-python'
        interpreter.write_text(
            '#!/bin/sh\n'
            'printf "%s\\n" "$*" >> ' + shlex.quote(str(calls)) + '\n'
            'exit 23\n')
        interpreter.chmod(0o700)
        environment = {**os.environ, 'CONEST_PYTHON': str(interpreter)}
        process = subprocess.run(['sh', str(tools / 'install_runtime.sh')],
                                 env=environment, text=True, capture_output=True)
        self.assertEqual(process.returncode, 23, process.stderr)
        self.assertEqual(calls.read_text().splitlines(),
                         ['tools/check_runtime.py --preflight'])
        self.assertNotIn('Installing application dependencies', process.stdout)


class RuntimePreflightTests(unittest.TestCase):
    def test_old_python_is_rejected_before_dependency_imports(self):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['check_runtime.py', '--preflight']), \
                patch.object(sys, 'version_info', (3, 9, 25)), \
                patch.object(sys, 'version', '3.9.25 (test)'), \
                patch.object(runtime.importlib, 'import_module') as imports, \
                contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(SystemExit, 'selected interpreter is 3.9.25'):
                runtime.main()
        imports.assert_not_called()
        self.assertIn('Version: 3.9.25', output.getvalue())

    def test_preflight_needs_sqlite_but_not_packages_or_timezone_data(self):
        with patch.object(sys, 'argv', ['check_runtime.py', '--preflight']), \
                patch('conest_app.runtime_health.check_sqlite_runtime') as sqlite_check, \
                patch('conest_app.runtime_health.check_timezones',
                      side_effect=RuntimeError('tzdata missing')) as zones, \
                patch.object(runtime.importlib, 'import_module',
                             side_effect=ImportError('not installed')) as imports, \
                contextlib.redirect_stdout(io.StringIO()):
            runtime.main()
        sqlite_check.assert_called_once_with()
        imports.assert_not_called()
        zones.assert_not_called()

    def test_preflight_rejects_an_inadequate_linked_sqlite(self):
        with patch.object(sys, 'argv', ['check_runtime.py', '--preflight']), \
                patch('conest_app.runtime_health.check_sqlite_runtime',
                      side_effect=RuntimeError('SQLite JSON support missing')), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, 'SQLite JSON support missing'):
                runtime.main()


if __name__ == '__main__':
    unittest.main()
