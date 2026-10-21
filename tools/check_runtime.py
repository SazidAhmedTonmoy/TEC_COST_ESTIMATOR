"""Check a selected Python before installation and validate its dependencies."""
import argparse
import importlib
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true',
                        help='Check Python and SQLite before installing packages.')
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    print('Python:', sys.executable)
    print('Version:', sys.version.split()[0])
    if sys.version_info < (3, 10):
        raise SystemExit(
            'TEC ConEst requires Python 3.10 or newer; the selected interpreter '
            'is {}. Configure the application to use Python 3.11 or another '
            'supported version in cPanel/Passenger, then install requirements '
            'with that same interpreter. Installing packages into a different '
            'shell Python will not change the website runtime.'
            .format(sys.version.split()[0]))
    from conest_app.runtime_health import check_sqlite_runtime, check_timezones
    try:
        check_sqlite_runtime()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    import sqlite3
    print('SQLite:', sqlite3.sqlite_version, '(JSON and UPSERT supported)')
    if args.preflight:
        return
    failed = []
    for name in ('openpyxl', 'pdfplumber', 'PIL', 'tzdata'):
        try:
            module = importlib.import_module(name)
            print(name, getattr(module, '__version__', ''), module.__file__)
        except ImportError:
            failed.append(name)
    if failed:
        raise SystemExit('Missing application dependencies: ' + ', '.join(failed) +
                         '. Install requirements.txt with the Python interpreter '
                         'shown above.')
    try:
        check_timezones()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print('Timezones: Australia/Sydney and Australia/Melbourne available')


if __name__ == '__main__':
    main()
