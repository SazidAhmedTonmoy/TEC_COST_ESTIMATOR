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
        return {'name':name,'bytes':target.stat().st_size,'reason':reason}


def daily_backup():
    today=datetime.now(timezone.utc).strftime('%Y%m%d')
    with write_lock:
        if not list(folder().glob(today+'T*-daily-*.db')):create_backup('daily')


def list_backups():
    result=[]
    for p in sorted(folder().glob('*.db'),reverse=True):
        meta=json.loads(p.with_suffix('.json').read_text()) if p.with_suffix('.json').exists() else {}
        result.append({'name':p.name,'bytes':p.stat().st_size,**meta})
    return result


def backup_path(name):
    if not re.fullmatch(r'\d{8}T\d{6}Z-(manual|daily|before-import|before-restore)-[a-f0-9]{8}\.db',name):
        raise ValueError('Invalid backup name')
    path=folder()/name
    if not path.is_file():raise LookupError('Backup not found')
    return path


def restore_backup(name):
    path=backup_path(name)
    with write_lock:
        with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro',uri=True)) as source,connect() as dest:
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
