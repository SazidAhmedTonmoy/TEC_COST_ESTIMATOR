"""Transactional, repeatable import of the deployed legacy lighting database."""
import hashlib,json,os,sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from .database import write_lock

def merge_legacy_prices(target):
    target=Path(target).resolve()
    source=Path(os.environ.get('CONEST_LIGHT_PRICES_DB') or target.parent/'lighting_prices.db').resolve()
    if not source.exists() or source==target:return
    with write_lock,closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as old,closing(sqlite3.connect(target)) as new:
        old.row_factory=sqlite3.Row;new.row_factory=sqlite3.Row
        old.execute('BEGIN')
        if old.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Legacy lighting database failed integrity check; keep both files and restore a valid backup')
        if old.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Legacy lighting database contains broken relationships')
        required={'quotes','groups','lines'}
        if not required.issubset({r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}):raise ValueError('Legacy lighting database is missing quote tables')
        records={t:[dict(r) for r in old.execute('SELECT * FROM "'+t+'" ORDER BY id')] for t in ('quotes','groups','lines')}
        digest=hashlib.sha256(json.dumps(records,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        new.execute('CREATE TABLE IF NOT EXISTS lighting_migrations(source_path TEXT,source_hash TEXT,completed_at TEXT,PRIMARY KEY(source_path,source_hash))');new.commit()
        if new.execute('SELECT 1 FROM lighting_migrations WHERE source_path=? AND source_hash=?',(str(source),digest)).fetchone():return
        if records['quotes']:
            folder=target.parent/'migration_backups';folder.mkdir(exist_ok=True)
            backup=folder/('pre-v2-merge-'+datetime.now().strftime('%Y%m%dT%H%M%S%f')+'.db')
            with closing(sqlite3.connect(backup)) as dest:new.backup(dest)
        new.execute('PRAGMA foreign_keys=ON');new.execute('BEGIN IMMEDIATE')
        try:
            def insert(table,record,changes):
                data={**record,**changes};ident=data.pop('id')
                # Preserve existing price URLs on the usual first migration.
                if not new.execute('SELECT 1 FROM "'+table+'" WHERE id=?',(ident,)).fetchone():data={'id':ident,**data}
                keys=list(data)
                return new.execute('INSERT INTO "'+table+'" ('+','.join('"'+k+'"' for k in keys)+') VALUES ('+','.join('?' for _ in keys)+')',tuple(data[k] for k in keys)).lastrowid
            for q in records['quotes']:
                if new.execute('SELECT 1 FROM quotes WHERE reference=? AND quote_date IS ? AND content_hash=?',(q['reference'],q['quote_date'],q['content_hash'])).fetchone():continue
                qid=insert('quotes',q,{})
                for g in (g for g in records['groups'] if g['quote_id']==q['id']):
                    gid=insert('groups',g,{'quote_id':qid})
                    for line in (l for l in records['lines'] if l['group_id']==g['id']):insert('lines',line,{'group_id':gid})
            if new.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Merged database relationship check failed')
            new.execute('INSERT INTO lighting_migrations VALUES(?,?,?)',(str(source),digest,datetime.now().isoformat()));new.commit()
        except Exception:new.rollback();raise
