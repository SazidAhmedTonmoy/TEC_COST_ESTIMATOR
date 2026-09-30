"""Code-managed upgrades for CLI, Passenger and direct database users.

Every public connect() calls ensure_database(). A process cache makes ordinary
requests cheap; an OS file lock serializes migrations between server workers.
No shipped database is copied over the live database.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

CURRENT_SCHEMA = 29
MIGRATION_KEY = 'v3.1-catalog-rating'
_local = threading.local()
_ready = {}
log = logging.getLogger(__name__)


class UpgradeError(RuntimeError):
    """An upgrade failed; requests must not run against a partial schema."""


def _identity(path):
    try:
        stat = path.stat()
        return stat.st_dev, stat.st_ino
    except FileNotFoundError:
        return None


def is_upgrading(path):
    return str(Path(path).resolve()) in getattr(_local, 'paths', set())


@contextmanager
def _process_lock(path, timeout=120):
    # Never unlink an advisory-lock file: other workers may hold its inode.
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'r+b') as handle:
        if os.name == 'nt':
            import msvcrt
            if handle.seek(0, 2) == 0:
                handle.write(b'0'); handle.flush()
            def acquire():
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        deadline = time.monotonic() + timeout
        while True:
            try:
                acquire(); break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise UpgradeError('Another worker is upgrading the database. Please retry shortly.')
                time.sleep(.1)
        try:
            yield
        finally:
            release()


def _status(path, expected_version=CURRENT_SCHEMA, migration_key=MIGRATION_KEY):
    if not path.is_file() or path.stat().st_size == 0:
        return False, None
    from .database import _raw_connect
    with _raw_connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'schema_version' not in tables:
            return False, None
        row = conn.execute('SELECT version FROM schema_version LIMIT 1').fetchone()
        version = int(row[0]) if row else 0
        if version > CURRENT_SCHEMA:
            raise UpgradeError('This database belongs to newer application code. Deploy the matching newer code; do not downgrade the database.')
        if version != expected_version or 'app_migrations' not in tables:
            return False, version
        required = {
            'users': {'contact_number', 'avatar_version', 'has_avatar'},
            'quotes': {'canonical_hash', 'file_sha256'},
            'project_lines': {'reference_name'},
            'groups': {'nickname', 'revision'},
        }
        present = {'user_avatars', 'lighting_import_receipts', 'lighting_photos', 'account_deletions'} <= tables
        if expected_version >= 25:
            required['project_user_access'] = {'project_id', 'user_id', 'granted_by', 'granted_at'}
        if expected_version >= 26:required['projects'] = {'labor_hours_markup'}
        if expected_version >= 27:required['projects'].update({'review_deadline', 'review_cycle'})
        if expected_version >= 28:required['project_lines'].update({'exclude_material_markup','exclude_hours_markup','exclude_final_markup'})
        if expected_version >= 29:required['catalog_items']={'importance_rating'}
        present = present and all(table in tables and fields <= {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
                                  for table, fields in required.items())
        # app_migrations uses a release-specific first-column name; positional
        # lookup avoids changing historical schemas just for bookkeeping.
        first = next(iter(conn.execute('PRAGMA table_info(app_migrations)')))[1]
        marker = conn.execute(f'SELECT 1 FROM app_migrations WHERE "{first}"=?', (migration_key,)).fetchone()
        return bool(present and marker), version


def _safety_backup(path, previous):
    """One protected pre-upgrade snapshot, separate from daily retention."""
    if not path.exists() or not path.stat().st_size:
        return None
    from .database import _raw_connect
    folder = path.parent / 'upgrade_backups'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = folder / f'{path.stem}-before-schema-{CURRENT_SCHEMA}.db'
    # Preserve the first snapshot even after a failed/interrupted migration.
    if target.exists():
        with _raw_connect(target) as saved:
            if saved.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise UpgradeError('The pre-upgrade safety backup failed its integrity check. Ask your administrator to review server storage.')
        return target
    pending = target.with_suffix('.pending')
    try:
        with _raw_connect(path) as source, _raw_connect(pending) as dest:
            deadline = time.monotonic() + 120
            def progress(status, remaining, total):
                if time.monotonic() > deadline:
                    raise UpgradeError('The safety backup timed out. Stop other database writers and restart the application.')
            source.backup(dest, pages=512, progress=progress)
            if dest.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise UpgradeError('The safety backup could not be verified; no upgrade was started.')
        os.chmod(pending, 0o600)
        os.replace(pending, target)
        target.with_suffix('.json').write_text(json.dumps({'from_schema': previous, 'to_schema': CURRENT_SCHEMA,
            'database': str(path), 'created_at': time.time()}), encoding='utf-8')
        # One completed protected snapshot per database; do not prune the old
        # snapshot until a replacement has safely been created.
        for old in folder.glob(f'{path.stem}-before-schema-*.db'):
            if old != target and not old.is_symlink():
                old.unlink(); old.with_suffix('.json').unlink(missing_ok=True)
        return target
    finally:
        pending.unlink(missing_ok=True)


def ensure_database(path=None):
    from .database import database_path, _raw_connect, _initialize_schema, write_lock
    target = (Path(path) if path is not None else database_path()).expanduser().resolve()
    key = str(target)
    if is_upgrading(target):
        return target
    identity = _identity(target)
    if identity is not None and _ready.get(key) == identity:
        return target
    with write_lock:
        if _identity(target) is not None and _ready.get(key) == _identity(target):
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        with _process_lock(target.with_name('.' + target.name + '.upgrade.lock')):
            ready, previous = _status(target)
            if not ready:
                backup = _safety_backup(target, previous)
                paths = getattr(_local, 'paths', set())
                _local.paths = paths | {key}
                try:
                    log.warning('Upgrading TEC ConEst database to schema %s (safety backup: %s)', CURRENT_SCHEMA, backup)
                    # A complete schema-24 installation needs only the new
                    # access table, not another run of historical backfills.
                    if previous == 28 and _status(target,28,'v3.1-item-markups')[0]:
                        pass
                    elif previous == 27 and _status(target,27,'v3.0-review-workflow')[0]:
                        pass
                    elif previous == 26 and _status(target,26,'v2.4-labor-hours')[0]:
                        pass  # Only the review migration below is needed.
                    elif previous == 25 and _status(target,25,'v2.3.3-project-access')[0]:
                        from .release_v24_hours import initialize_hours
                        with _raw_connect(target) as conn:initialize_hours(conn)
                    elif previous == 24 and _status(target, 24, 'v2.3.1-import-profile-auto-upgrade')[0]:
                        from .release_v233 import initialize_v233
                        with _raw_connect(target) as conn:
                            initialize_v233(conn)
                            from .release_v24_hours import initialize_hours
                            initialize_hours(conn)
                    else:
                        _initialize_schema(target)
                    from .release_v30_review import initialize_review
                    with _raw_connect(target) as conn:
                        conn.execute('BEGIN IMMEDIATE')
                        initialize_review(conn)
                        from .release_v31_item_markups import initialize_item_markups
                        initialize_item_markups(conn)
                        from .release_v31_rating import initialize_rating
                        initialize_rating(conn)
                    with _raw_connect(target) as conn:
                        if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchone():
                            raise UpgradeError('Database verification failed after the upgrade. The pre-upgrade backup was retained.')
                    if not _status(target)[0]:
                        raise UpgradeError('Database upgrade did not finish. The pre-upgrade backup was retained.')
                except Exception as exc:
                    log.exception('Automatic TEC ConEst database upgrade failed')
                    if isinstance(exc, UpgradeError):
                        raise
                    raise UpgradeError('Automatic database upgrade failed. Your administrator should check server permissions, free disk space and the server error log. The existing database has not been replaced.') from exc
                finally:
                    _local.paths = paths
            _ready[key] = _identity(target)
    return target
