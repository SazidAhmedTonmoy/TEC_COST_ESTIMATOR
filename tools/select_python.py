"""Locate the production interpreter without executing a WSGI startup file."""
import ast
import os
from pathlib import Path
import shlex
import sys

root = Path(__file__).resolve().parents[1]
candidates = []
override = os.environ.get('CONEST_PYTHON', '').strip()
if override:
    candidates.append(override)
htaccess = root / '.htaccess'
if htaccess.is_file():
    for line in htaccess.read_text(errors='replace').splitlines():
        try:
            parts = shlex.split(line, comments=True)
        except ValueError:
            continue
        if len(parts) == 2 and parts[0].lower() == 'passengerpython':
            candidates.append(parts[1])
startup = root / 'passenger_wsgi.py'
if startup.is_file():
    try:
        tree = ast.parse(startup.read_text(errors='replace'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('INTERP', 'PYTHON', 'PYTHON_BIN') for t in node.targets):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    candidates.append(node.value.value)
    except SyntaxError:
        pass
if os.environ.get('VIRTUAL_ENV'):
    candidates.append(str(Path(os.environ['VIRTUAL_ENV']) / 'bin/python'))
candidates += [str(root / 'venv/bin/python'), str(root / '.venv/bin/python'), sys.executable]
for candidate in candidates:
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = root / path
    if path.is_file() and os.access(path, os.X_OK):
        print(path.absolute())
        break
else:
    raise SystemExit('No usable Python interpreter found for the application')
