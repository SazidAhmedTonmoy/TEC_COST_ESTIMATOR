"""Make a consistent backup, including any committed WAL transactions."""
from datetime import datetime
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conest_app.database import database_path


def main():
    source = database_path()
    if not source.is_file():
        raise SystemExit('Database not found')
    folder = Path(__file__).resolve().parents[1] / 'backups'
    folder.mkdir(exist_ok=True)
    target = folder / ('conest_catalog_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.db')
    with sqlite3.connect(source) as live, sqlite3.connect(target) as backup:
        live.backup(backup)
    print('Backup created:', target)


if __name__ == '__main__':
    main()
