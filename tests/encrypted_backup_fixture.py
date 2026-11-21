"""Read a verified snapshot for tests without changing its encrypted artifact."""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
import tempfile

from conest_app.data_protection import decrypt_file


@contextmanager
def open_backup(path, *, purpose='backup:catalog', database=None):
    path = Path(path)
    if not path.name.endswith('.enc'):
        with closing(sqlite3.connect(path)) as connection:
            yield connection
        return
    with tempfile.TemporaryDirectory(prefix='tec-backup-test-') as temporary:
        plain = Path(temporary) / 'snapshot.db'
        decrypt_file(path, plain, purpose=purpose, database=database)
        with closing(sqlite3.connect(plain)) as connection:
            yield connection
