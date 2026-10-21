"""Select a configured interpreter without executing the WSGI startup file.

The shell's Python and an application's Passenger Python need not be the same.
Dependency installation therefore uses --require-configured; other existing
local helpers may still use the compatibility fallbacks, with a warning.
"""
import argparse
import ast
import os
from pathlib import Path
import shlex
import sys


class InterpreterSelectionError(RuntimeError):
    pass


_INTERPRETER_NAMES = frozenset(('INTERP', 'PYTHON', 'PYTHON_BIN'))
_EXEC_CALLS = frozenset(('execl', 'execle', 'execlp', 'execlpe',
                         'execv', 'execve', 'execvp', 'execvpe'))


def _path(value, root):
    path = Path(value).expanduser()
    # Preserve the virtualenv path, even when bin/python is a symlink to the
    # system interpreter. Resolving that symlink would discard the environment.
    return Path(os.path.abspath(str(path if path.is_absolute() else root / path)))


def _configured(path, source):
    if not path.is_file() or not os.access(path, os.X_OK):
        raise InterpreterSelectionError(
            '{} selects an unavailable or non-executable interpreter: {}. '
            'Correct the configured path; no fallback interpreter was used.'
            .format(source, path))
    return path, source, True


def _passenger_python(root):
    path = root / '.htaccess'
    if not path.is_file():
        return None
    selected = []
    for line in path.read_text(errors='replace').splitlines():
        try:
            parts = shlex.split(line, comments=True)
        except ValueError:
            if line.lstrip().lower().startswith('passengerpython'):
                raise InterpreterSelectionError(
                    'Cannot read PassengerPython in .htaccess. Correct its '
                    'quoting or set CONEST_PYTHON to the app interpreter.')
            continue
        if parts and parts[0].lower() == 'passengerpython':
            if len(parts) != 2:
                raise InterpreterSelectionError(
                    'PassengerPython in .htaccess must contain one interpreter '
                    'path. Correct it or set CONEST_PYTHON explicitly.')
            selected.append(_path(parts[1], root))
    choices = set(selected)
    if len(choices) > 1:
        raise InterpreterSelectionError(
            'Multiple PassengerPython paths exist in .htaccess. Set '
            'CONEST_PYTHON to the final interpreter used by this application.')
    return selected[0] if selected else None


def _startup_python(root):
    """Recognize the usual literal INTERP + os.execl WSGI bootstrap pattern.

    Only an unconditional module-level exec or the documented module-level
    ``if sys.executable != INTERP`` guard establishes a static override. A call
    inside an unused function or an arbitrary conditional does not establish
    which interpreter will serve the application.
"""
    path = root / 'passenger_wsgi.py'
    if not path.is_file():
        return None
    try:
        tree = ast.parse(path.read_text(errors='replace'))
    except SyntaxError as exc:
        raise InterpreterSelectionError(
            'Cannot inspect passenger_wsgi.py. Correct its syntax or set '
            'CONEST_PYTHON to the final app interpreter.') from exc
    os_names, sys_names, exec_names = {'os'}, {'sys'}, set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == 'os':
                    os_names.add(alias.asname or alias.name)
                if alias.name == 'sys':
                    sys_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == 'os':
            for alias in node.names:
                if alias.name in _EXEC_CALLS:
                    exec_names.add(alias.asname or alias.name)

    def is_exec(node):
        if not isinstance(node, ast.Call) or not node.args:
            return False
        function = node.func
        return ((isinstance(function, ast.Name) and function.id in exec_names) or
                (isinstance(function, ast.Attribute) and
                 isinstance(function.value, ast.Name) and
                 function.value.id in os_names and function.attr in _EXEC_CALLS))

    def exec_calls(node):
        # Function bodies do not run merely because they are defined. Class
        # bodies do run, so an exec there must be rejected as an unknown pattern.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return []
        calls = [node] if is_exec(node) else []
        for child in ast.iter_child_nodes(node):
            calls.extend(exec_calls(child))
        return calls

    def scoped_nodes(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Lambda)):
            return
        yield node
        for child in ast.iter_child_nodes(node):
            yield from scoped_nodes(child)

    def is_current_python(node):
        return (isinstance(node, ast.Attribute) and node.attr == 'executable' and
                isinstance(node.value, ast.Name) and node.value.id in sys_names)

    def guarded_call(node):
        if (not isinstance(node, ast.If) or node.orelse or len(node.body) != 1 or
                not isinstance(node.body[0], ast.Expr) or
                not is_exec(node.body[0].value)):
            return None
        test = node.test
        if (not isinstance(test, ast.Compare) or len(test.ops) != 1 or
                not isinstance(test.ops[0], ast.NotEq)):
            return None
        call = node.body[0].value
        left, right = test.left, test.comparators[0]
        same_target = lambda value: ast.dump(value) == ast.dump(call.args[0])
        if ((is_current_python(left) and same_target(right)) or
                (is_current_python(right) and same_target(left))):
            return call
        return None

    assignments, overrides = {}, []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in _INTERPRETER_NAMES:
                    assignments.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in _INTERPRETER_NAMES:
                assignments.setdefault(node.target.id, []).append(node.value)
        # A conditional reassignment makes a previously literal target unknown.
        # Do not choose the old literal while ignoring code that can replace it.
        for child in scoped_nodes(node):
            if child is node and isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = []
            if isinstance(child, ast.Assign):
                targets = child.targets
            elif isinstance(child, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
                targets = [child.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in _INTERPRETER_NAMES:
                    assignments.setdefault(target.id, []).append(None)
        calls = exec_calls(node)
        if not calls:
            continue
        call = node.value if isinstance(node, ast.Expr) and is_exec(node.value) else guarded_call(node)
        if len(calls) != 1 or call is None:
            raise InterpreterSelectionError(
                'passenger_wsgi.py uses a conditional or dynamic interpreter '
                'override that cannot be determined statically. Set '
                'CONEST_PYTHON to the exact final app interpreter.')
        argument = call.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            overrides.append(_path(argument.value, root))
            continue
        if isinstance(argument, ast.Name) and argument.id in _INTERPRETER_NAMES:
            values = assignments.get(argument.id, [])
            if (len(values) == 1 and isinstance(values[0], ast.Constant) and
                    isinstance(values[0].value, str)):
                overrides.append(_path(values[0].value, root))
                continue
        raise InterpreterSelectionError(
            'passenger_wsgi.py selects its interpreter dynamically. Set '
            'CONEST_PYTHON to the exact final interpreter from the hosting '
            'configuration; the startup file was not executed.')
    if len(set(overrides)) > 1:
        raise InterpreterSelectionError(
            'passenger_wsgi.py contains multiple interpreter overrides. Set '
            'CONEST_PYTHON to the exact final app interpreter.')
    return overrides[0] if overrides else None


def select_interpreter(root, environment=None, executable=None,
                       require_configured=False):
    environment = os.environ if environment is None else environment
    executable = sys.executable if executable is None else executable
    root = Path(root).absolute()
    override = environment.get('CONEST_PYTHON', '').strip()
    if override:
        return _configured(_path(override, root), 'CONEST_PYTHON')
    # WSGI re-exec intentionally changes the initial PassengerPython. Do not
    # misdiagnose that supported bootstrap pattern as conflicting settings.
    startup = _startup_python(root)
    if startup:
        return _configured(startup, 'passenger_wsgi.py interpreter override')
    passenger = _passenger_python(root)
    if passenger:
        return _configured(passenger, '.htaccess PassengerPython')
    if require_configured:
        raise InterpreterSelectionError(
            'Cannot determine the configured Passenger interpreter. The SSH '
            'shell Python is not proof of the website runtime. Select Python '
            '3.11 or another supported version in the hosting settings, then '
            'set CONEST_PYTHON to that application interpreter when running '
            'this installer. CONEST_PYTHON selects command-line tooling only; '
            'it does not change Passenger configuration.')
    candidates = []
    if environment.get('VIRTUAL_ENV'):
        candidates.append((Path(environment['VIRTUAL_ENV']) / 'bin/python',
                           'active shell virtualenv'))
    candidates.extend(((root / 'venv/bin/python', 'local venv'),
                       (root / '.venv/bin/python', 'local .venv'),
                       (executable, 'current command-line Python')))
    for candidate, source in candidates:
        path = _path(candidate, root)
        if path.is_file() and os.access(path, os.X_OK):
            return path, source, False
    raise InterpreterSelectionError('No usable Python interpreter was found.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-configured', action='store_true',
                        help='Reject shell-only guesses for production installs.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        path, source, configured = select_interpreter(
            root, require_configured=args.require_configured)
    except InterpreterSelectionError as exc:
        parser.exit(1, str(exc) + '\n')
    print('Selected interpreter from {}: {}'.format(source, path), file=sys.stderr)
    if not configured:
        print('Warning: this fallback does not establish which Python '
              'Passenger runs.', file=sys.stderr)
    else:
        print('Confirm the restarted website with /api/health?check=tenders; '
              'command-line selection does not change Passenger.', file=sys.stderr)
    print(path)


if __name__ == '__main__':
    main()
