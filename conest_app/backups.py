"""Consistent, authenticated encrypted backups and compatible in-place restore."""
from contextlib import closing, contextmanager
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .database import connect, database_path, write_lock
from .data_protection import (
    decrypt_file, encrypt_file, key_file_path, private_directory, private_file,
    protect_database_settings,
)


def folder():
    return private_directory(database_path().parent / 'backups')


def _snapshots(directory):
    if not Path(directory).is_dir():
        return []
    return sorted(
        (p for p in Path(directory).iterdir()
         if p.name.endswith(('.db', '.db.enc')) and p.is_file() and not p.is_symlink()),
        key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True,
    )


def prune_backups(directory=None):
    """Keep one completed snapshot, including older plaintext-format backups."""
    with write_lock:
        for old in _snapshots(Path(directory) if directory is not None else folder())[1:]:
            old.unlink(missing_ok=True)
            old.with_suffix('.json').unlink(missing_ok=True)


def _validate_reason(reason):
    if reason not in ('manual', 'daily', 'before-import', 'before-restore'):
        raise ValueError('Invalid backup reason')


def _write_metadata(target, metadata):
    pending = target.with_name(target.name + '.metadata.tmp')
    try:
        descriptor = os.open(str(pending), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(metadata, handle)
        os.replace(pending, target.with_suffix('.json'))
    finally:
        pending.unlink(missing_ok=True)


def _create_snapshot(source, directory, *, reason, actor, database):
    """Copy committed SQLite state, verify it, then publish ciphertext atomically."""
    _validate_reason(reason)
    directory = private_directory(directory)
    prefix = 'tenders-' if database == 'tenders' else ''
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    name = f'{prefix}{stamp}-{reason}-{uuid4().hex[:8]}.db.enc'
    target = directory / name
    pending = directory / ('.' + name + '.pending')
    published = False
    try:
        # SQLite needs a seekable file for its online backup API. Keep this
        # short-lived plaintext copy owner-only, inside a private directory.
        with tempfile.TemporaryDirectory(prefix='.snapshot-', dir=directory) as temporary:
            plain = Path(temporary) / 'snapshot.db'
            plain.touch(mode=0o600)
            with closing(sqlite3.connect(plain)) as destination:
                source.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Backup integrity check failed')
            encryption = encrypt_file(plain, pending, purpose='backup:' + database)
        metadata = {
            'reason': reason, 'created_by': actor,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'database': database, **encryption,
        }
        _write_metadata(target, metadata)
        os.replace(pending, target)
        published = True
    finally:
        pending.unlink(missing_ok=True)
        if not published:
            target.with_suffix('.json').unlink(missing_ok=True)
    prune_backups(directory)
    return {'name': name, 'bytes': target.stat().st_size, 'reason': reason,
            'database': database, 'encrypted': True}


def create_backup(reason='manual', actor=None):
    _validate_reason(reason)
    with write_lock, connect() as source:
        return _create_snapshot(source, folder(), reason=reason, actor=actor, database='catalog')


def tender_path():
    return Path(os.environ.get('CONEST_TENDERS_DB_PATH') or database_path().parent / 'tec_tenders.db').resolve()


def create_tender_backup(reason='manual', actor=None):
    _validate_reason(reason)
    source_path = tender_path()
    if not source_path.is_file():
        return None
    with closing(sqlite3.connect(f'{source_path.as_uri()}?mode=ro', uri=True, timeout=30)) as source:
        return _create_snapshot(source, source_path.parent / 'tender_backups',
                                reason=reason, actor=actor, database='tenders')


def _backup_set(reason, actor=None):
    result = [create_backup(reason, actor)]
    tender = create_tender_backup(reason, actor)
    if tender:
        result.append(tender)
    return result


def create_backup_set(reason='manual', actor=None):
    from .auto_upgrade import _process_lock
    with write_lock, _process_lock(folder() / '.scheduled.lock'):
        return _backup_set(reason, actor)


def daily_backup(now=None):
    """Once per server-local day, due at 00:10; catch up after an outage."""
    from .auto_upgrade import _process_lock
    now = now or datetime.now().astimezone()
    if (now.hour, now.minute) < (0, 10):
        return []
    with write_lock, _process_lock(folder() / '.scheduled.lock'):
        marker = folder() / '.daily-complete.json'
        previous = json.loads(marker.read_text()) if marker.exists() else {}
        day = now.date().isoformat()
        if previous.get('day') == day and (not tender_path().is_file() or 'tenders' in previous.get('databases', [])):
            return []
        result = _backup_set('daily')
        pending = marker.with_suffix('.tmp')
        pending.write_text(json.dumps({'day': day, 'databases': [r['database'] for r in result]}))
        private_file(pending)
        os.replace(pending, marker)
        return result


def register_runtime():
    """Record paths for cron, never the encryption key or any other secret."""
    target = Path(__file__).resolve().parents[1] / 'tmp' / 'backup-runtime.json'
    key_path = key_file_path()
    configuration = {'catalog': str(database_path().resolve()), 'tenders': str(tender_path())}
    # An environment-only key must separately be configured in the cron job.
    # A key-file path is safe to pass to cron, unlike the key's contents.
    if key_path is not None:
        configuration['encryption_key_file'] = str(key_path)
    else:
        configuration['encryption_key_environment_required'] = True
    content = json.dumps(configuration, sort_keys=True)
    if target.exists() and target.read_text() == content:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_name(target.name + '.' + uuid4().hex + '.tmp')
    try:
        with pending.open('x') as handle:
            private_file(pending)
            handle.write(content)
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)


def _listing(path, database):
    metadata_path = path.with_suffix('.json')
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    return {
        'name': path.name if database == 'catalog' or path.name.startswith('tenders-') else 'tenders-' + path.name,
        'bytes': path.stat().st_size,
        'created_at': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        **metadata, 'database': database, 'encrypted': path.name.endswith('.db.enc'),
    }


def list_all_backups():
    result = list_backups()
    directory = tender_path().parent / 'tender_backups'
    if directory.exists():
        prune_backups(directory)
        result.extend(_listing(path, 'tenders') for path in _snapshots(directory))
    return result


def list_backups():
    prune_backups()
    return [_listing(path, 'catalog') for path in _snapshots(folder())]


def backup_path(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.db(?:\.enc)?', name):
        raise ValueError('Invalid backup name')
    directory = tender_path().parent / 'tender_backups' if name.startswith('tenders-') else folder()
    path = directory / name
    if name.startswith('tenders-') and not path.exists():
        path = directory / name.removeprefix('tenders-')
    if path.is_symlink() or path.resolve().parent != directory.resolve():
        raise ValueError('Invalid backup path')
    if not path.is_file():
        raise LookupError('Backup not found')
    return path


@contextmanager
def readable_snapshot(path, *, database='catalog', key_database=None):
    """Internal restore/verification helper; downloads always serve ciphertext."""
    path = Path(path)
    if not path.name.endswith('.enc'):
        yield path
        return
    # The protected backup directory is also used for transient restore files.
    with tempfile.TemporaryDirectory(prefix='.restore-', dir=path.parent) as temporary:
        plain = Path(temporary) / 'snapshot.db'
        decrypt_file(path, plain, purpose='backup:' + database, database=key_database)
        yield plain


def restore_backup(name):
    if name.startswith('tenders-'):
        raise ValueError('Tender snapshots can be downloaded for an administrator-managed restore.')
    path = backup_path(name)
    with write_lock:
        with closing(sqlite3.connect(':memory:')) as source, connect() as destination:
            # Authenticate and load before retention removes the selected file.
            with readable_snapshot(path) as plain:
                with closing(sqlite3.connect(f'{plain.as_uri()}?mode=ro', uri=True)) as disk:
                    disk.backup(source)
            if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or source.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Backup integrity check failed')
            if source.execute('SELECT version FROM schema_version').fetchone()[0] != destination.execute('SELECT version FROM schema_version').fetchone()[0]:
                raise ValueError('Restore requires a backup from the same application schema version')
            if not source.execute("SELECT 1 FROM users WHERE role='admin' AND is_active=1").fetchone():
                raise ValueError('Backup has no active administrator')
            # Remove retired settings and validate the backup key before restore.
            protect_database_settings(source)
            source.commit()
            safety = create_backup('before-restore')
            source.backup(destination)
            destination.execute('DELETE FROM sessions')
            destination.execute('DELETE FROM project_presence')
            destination.execute('UPDATE catalog_generation SET generation=generation+?',
                                (int(datetime.now(timezone.utc).timestamp() * 1000),))
            destination.commit()
        from .import_preview import folder as preview_folder
        for manifest in preview_folder().glob('*.json'):
            manifest.unlink(missing_ok=True)
        from .read_cache import _cache, _lock
        with _lock:
            _cache.clear()
    return {'safety_backup': safety['name'], 'message': 'Database restored. Everyone must sign in again using the restored accounts.'}
