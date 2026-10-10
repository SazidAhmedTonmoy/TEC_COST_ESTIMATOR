"""Consistent SQLite backups; restore in place so WAL readers remain safe."""
from contextlib import closing
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .database import connect, database_path, write_lock
from .accounts import AccessError


def folder():
    path=database_path().parent/'backups';path.mkdir(parents=True,exist_ok=True)
    return path


def prune_backups(directory=None):
    """Keep one completed snapshot, each with its optional metadata sidecar."""
    with write_lock:
        files=sorted((p for p in (Path(directory) if directory is not None else folder()).glob('*.db') if p.is_file() and not p.is_symlink()),key=lambda p:(p.stat().st_mtime_ns,p.name),reverse=True)
        for old in files[1:]:
            old.unlink(missing_ok=True);old.with_suffix('.json').unlink(missing_ok=True)


def create_backup(reason='manual',actor=None):
    if reason not in ('manual','daily','before-import','before-restore'):raise ValueError('Invalid backup reason')
    with write_lock:
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        name=f'{stamp}-{reason}-{uuid4().hex[:8]}.db'
        target=folder()/name;pending=target.with_suffix('.tmp')
        try:
            with connect() as source,closing(sqlite3.connect(pending)) as dest:
                source.backup(dest)
                if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup integrity check failed')
            os.replace(pending,target)
            target.with_suffix('.json').write_text(json.dumps({'reason':reason,'created_by':actor,'created_at':datetime.now(timezone.utc).isoformat()}))
        except Exception:
            pending.unlink(missing_ok=True);raise
        prune_backups()
        return {'name':name,'bytes':target.stat().st_size,'reason':reason}


def tender_path():
    return Path(os.environ.get('CONEST_TENDERS_DB_PATH') or database_path().parent/'tec_tenders.db').resolve()


def create_tender_backup(reason='manual',actor=None):
    source_path=tender_path()
    if not source_path.is_file():return None
    directory=source_path.parent/'tender_backups';directory.mkdir(parents=True,exist_ok=True)
    name='tenders-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+reason+'-'+uuid4().hex[:8]+'.db'
    target=directory/name;pending=target.with_suffix('.tmp')
    try:
        with closing(sqlite3.connect(f'{source_path.as_uri()}?mode=ro',uri=True,timeout=30)) as source,closing(sqlite3.connect(pending)) as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Tender backup integrity check failed')
        os.replace(pending,target)
        target.with_suffix('.json').write_text(json.dumps({'reason':reason,'created_by':actor,'created_at':datetime.now(timezone.utc).isoformat(),'database':'tenders'}))
        prune_backups(directory)
    finally:pending.unlink(missing_ok=True)
    return {'name':name,'bytes':target.stat().st_size,'reason':reason,'database':'tenders'}


def _backup_set(reason,actor=None):
    result=[{**create_backup(reason,actor),'database':'catalog'}]
    tender=create_tender_backup(reason,actor)
    if tender:result.append(tender)
    return result


def create_backup_set(reason='manual',actor=None):
    from .auto_upgrade import _process_lock
    with write_lock, _process_lock(folder()/'.scheduled.lock'):
        return _backup_set(reason,actor)


def daily_backup(now=None):
    """Once per server-local day, due at 00:10; catch up after an outage."""
    from .auto_upgrade import _process_lock
    now=now or datetime.now().astimezone()
    if (now.hour,now.minute)<(0,10):return []
    with write_lock, _process_lock(folder()/'.scheduled.lock'):
        marker=folder()/'.daily-complete.json'
        previous=json.loads(marker.read_text()) if marker.exists() else {}
        day=now.date().isoformat()
        if previous.get('day')==day and (not tender_path().is_file() or 'tenders' in previous.get('databases',[])):return []
        result=_backup_set('daily')
        pending=marker.with_suffix('.tmp')
        pending.write_text(json.dumps({'day':day,'databases':[r['database'] for r in result]}))
        os.replace(pending,marker)
        return result


def register_runtime():
    """Record actual WSGI database paths for the independent cron process."""
    target=Path(__file__).resolve().parents[1]/'tmp'/'backup-runtime.json'
    content=json.dumps({'catalog':str(database_path().resolve()),'tenders':str(tender_path())},sort_keys=True)
    if target.exists() and target.read_text()==content:return
    target.parent.mkdir(parents=True,exist_ok=True)
    pending=target.with_name(target.name+'.'+uuid4().hex+'.tmp')
    try:
        with pending.open('x') as f:
            os.chmod(pending,0o600);f.write(content)
        os.replace(pending,target)
    finally:pending.unlink(missing_ok=True)


def list_all_backups():
    result=[{**b,'database':'catalog'} for b in list_backups()]
    directory=tender_path().parent/'tender_backups'
    if directory.exists():
        prune_backups(directory)
        for p in directory.glob('*.db'):
            meta=json.loads(p.with_suffix('.json').read_text()) if p.with_suffix('.json').exists() else {}
            result.append({'name':p.name if p.name.startswith('tenders-') else 'tenders-'+p.name,'bytes':p.stat().st_size,'created_at':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(),**meta,'database':'tenders'})
    return result


def list_backups():
    prune_backups()
    result=[]
    for p in sorted(folder().glob('*.db'),key=lambda p:(p.stat().st_mtime_ns,p.name),reverse=True):
        meta=json.loads(p.with_suffix('.json').read_text()) if p.with_suffix('.json').exists() else {}
        result.append({'name':p.name,'bytes':p.stat().st_size,**meta})
    return result


def backup_path(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.db',name):
        raise ValueError('Invalid backup name')
    directory=tender_path().parent/'tender_backups' if name.startswith('tenders-') else folder()
    path=directory/name
    if name.startswith('tenders-') and not path.exists():path=directory/name.removeprefix('tenders-')
    if path.is_symlink() or path.resolve().parent!=directory.resolve():raise ValueError('Invalid backup path')
    if not path.is_file():raise LookupError('Backup not found')
    return path


def restore_backup(name):
    if name.startswith('tenders-'):raise ValueError('Tender snapshots can be downloaded for an administrator-managed restore.')
    path=backup_path(name)
    with write_lock:
        with closing(sqlite3.connect(':memory:')) as source,connect() as dest:
            # Read first, so retention can remove the original safely during restore.
            with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro',uri=True)) as disk:disk.backup(source)
            if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or source.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Backup integrity check failed')
            if source.execute('SELECT version FROM schema_version').fetchone()[0]!=dest.execute('SELECT version FROM schema_version').fetchone()[0]:
                raise ValueError('Restore requires a backup from the same application schema version')
            if not source.execute("SELECT 1 FROM users WHERE role='admin' AND is_active=1").fetchone():raise ValueError('Backup has no active administrator')
            safety=create_backup('before-restore')
            source.backup(dest)
            dest.execute('DELETE FROM sessions');dest.execute('DELETE FROM project_presence')
            dest.execute('UPDATE catalog_generation SET generation=generation+?',(int(datetime.now(timezone.utc).timestamp()*1000),))
            dest.commit()
        from .import_preview import folder as preview_folder
        for manifest in preview_folder().glob('*.json'):manifest.unlink(missing_ok=True)
        from .read_cache import _cache,_lock
        with _lock:_cache.clear()
    return {'safety_backup':safety['name'],'message':'Database restored. Everyone must sign in again using the restored accounts.'}
