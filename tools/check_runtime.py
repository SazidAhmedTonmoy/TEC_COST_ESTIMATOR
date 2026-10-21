"""Fail deployment clearly when the app's actual Python lacks import support."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if sys.version_info < (3, 10):
    raise SystemExit('TEC ConEst requires Python 3.10 or newer')
print('Python:', sys.executable)
failed = []
for name in ('openpyxl', 'pdfplumber', 'PIL', 'tzdata'):
    try:
        module = importlib.import_module(name)
        print(name, getattr(module, '__version__', ''), module.__file__)
    except ImportError:
        failed.append(name)
if failed:
    raise SystemExit('Missing application dependencies: ' + ', '.join(failed) + '. Install requirements.txt with the Python interpreter shown above.')
from conest_app.runtime_health import check_sqlite_runtime, check_timezones
try:
    check_sqlite_runtime()
    check_timezones()
except RuntimeError as exc:
    raise SystemExit(str(exc)) from exc
import sqlite3
print('SQLite:', sqlite3.sqlite_version, '(JSON and UPSERT supported)')
print('Timezones: Australia/Sydney and Australia/Melbourne available')
