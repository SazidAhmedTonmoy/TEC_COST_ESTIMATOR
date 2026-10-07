"""TEC Tenders local web app. Python 3.10+; standard library only."""
from __future__ import annotations
import json
import os
import threading
from .database import database_path
import math
import mimetypes
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
VIEWS = {'/', '/dashboard', '/chase-up', '/search', '/projects', '/builders', '/calendar', '/reminders', '/settings'}
TEXT_FIELDS = ('project','builder','status','builderStatus','location','region','contact','email','month','due','statusUpdated','pricing','remarks')

class ValidationError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

def text(value, name, required=False, limit=20000):
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise ValidationError(f'{name} must be text.')
    value = value.strip()
    if required and not value:
        raise ValidationError(f'{name} is required.')
    if len(value) > limit:
        raise ValidationError(f'{name} is too long.')
    return value

def date_value(value, timed=False, required=False):
    value = text(value, 'Date', required, 30)
    if value:
        try:
            if timed:
                parsed = datetime.strptime(value, '%Y-%m-%dT%H:%M')
                if parsed.strftime('%Y-%m-%dT%H:%M') != value:
                    raise ValueError()
            elif date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        except ValueError:
            raise ValidationError('Choose a valid date and time.' if timed else 'Choose a valid date.')
    return value

def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')

class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('CONEST_TENDERS_DB_PATH') or database_path().parent / 'tec_tenders.db').resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache = None
        self._cache_lock = threading.Lock()
        legacy = self.path.with_suffix('.sqlite3')
        if not self.path.exists() and legacy.is_file():
            with sqlite3.connect(f'{legacy.as_uri()}?mode=ro',uri=True) as source, sqlite3.connect(self.path) as target:
                source.backup(target)
        self.seed = json.loads((ROOT / 'tenders_seed' / 'seed.json').read_text(encoding='utf-8'))
        if self.path.is_file():
            with sqlite3.connect(self.path) as old:
                has_settings=old.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'").fetchone()
                migrated=has_settings and old.execute("SELECT 1 FROM settings WHERE id='attribution-v33'").fetchone()
                backup=self.path.with_suffix('.pre-v33.db')
                if has_settings and not migrated and not backup.exists():
                    with sqlite3.connect(backup) as target:
                        old.backup(target)
        self.initialize()

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.execute("UPDATE tender_generation SET value=value+1")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self):
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tender_generation (value INTEGER NOT NULL);
                INSERT INTO tender_generation SELECT 0 WHERE NOT EXISTS (SELECT 1 FROM tender_generation);
                CREATE TABLE IF NOT EXISTS submissions (id TEXT PRIMARY KEY, body TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS chases (id TEXT PRIMARY KEY, submission_id TEXT NOT NULL REFERENCES submissions(id), body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reminders (id TEXT PRIMARY KEY, submission_id TEXT NOT NULL REFERENCES submissions(id), body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tender_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER NOT NULL,
                    actor_name TEXT NOT NULL, submission_id TEXT, project TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL, details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS tender_activity_actor ON tender_activity(actor_id,created_at);
                CREATE TABLE IF NOT EXISTS settings (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS chase_submission ON chases(submission_id);
                CREATE INDEX IF NOT EXISTS reminder_submission ON reminders(submission_id);
            ''')
        with self.connect(write=True) as db:
            if not db.execute("SELECT 1 FROM settings WHERE id='import-v1'").fetchone():
                db.executemany('INSERT OR IGNORE INTO submissions VALUES(?,?,0)', [(s['id'], json.dumps(s, ensure_ascii=False)) for s in self.seed['submissions']])
                db.executemany('INSERT OR IGNORE INTO chases VALUES(?,?,?)', [(c['id'], c['submissionId'], json.dumps(c, ensure_ascii=False)) for c in self.seed['chases']])
                db.execute("INSERT INTO settings VALUES('import-v1','true')")

            self.migrate_attribution(db)

            # Idempotent correction; existing history and manually entered records stay intact.
            for row in db.execute('SELECT id,body FROM submissions').fetchall():
                item = json.loads(row['body'])
                if str(item.get('pricing', '')).strip() in ('4', '4.0'):
                    item['pricing'] = 'High'
                    db.execute('UPDATE submissions SET body=?,revision=revision+1 WHERE id=?',
                               (json.dumps(item,ensure_ascii=False), row['id']))

    def migrate_attribution(self, db):
        # One-time attribution supplied by the owner; never invent historical timestamps.
        if db.execute("SELECT 1 FROM settings WHERE id='attribution-v33'").fetchone():
            return
        baseline_row=db.execute("SELECT body FROM settings WHERE id='excel-import-baselines'").fetchone()
        baseline=json.loads(baseline_row[0]) if baseline_row else {}
        imported_ids={s['id'] for s in self.seed['submissions']} | {k for k in baseline if not k.startswith(('chases:','reminders:'))}
        for row in db.execute('SELECT id,body FROM submissions').fetchall():
            item=json.loads(row['body'])
            if row['id'] in imported_ids or item.get('sourceRow'):
                item.setdefault('importedByName','Tonmoy')
                item.setdefault('legacyImported',True)
                item.setdefault('origin','Excel import')
                db.execute('UPDATE submissions SET body=? WHERE id=?',(json.dumps(item,ensure_ascii=False),row['id']))
        for row in db.execute('SELECT id,body FROM chases').fetchall():
            item=json.loads(row['body'])
            if item.get('method')=='Imported' and item.get('author') in ('Workbook','Imported','',None):
                item.update(author='Yunus',legacyChase=True)
                db.execute('UPDATE chases SET body=? WHERE id=?',(json.dumps(item,ensure_ascii=False),row['id']))
        db.execute("INSERT INTO settings VALUES('attribution-v33','true')")

    @staticmethod
    def activity(db, actor_id, actor_name, action, submission=None, details=None):
        if actor_id is None:
            return
        submission=submission or {}
        db.execute('INSERT INTO tender_activity(actor_id,actor_name,submission_id,project,action,details,created_at) VALUES(?,?,?,?,?,?,?)',
                   (actor_id,actor_name or '',submission.get('id'),submission.get('project',''),action,json.dumps(details or {}),timestamp()))

    def edit_chase(self, b):
        identifier=text(b.get('id'),'Chase ID',True,100)
        sid=text(b.get('submissionId'),'Submission ID',True,100)
        note=text(b.get('note'),'Chase-up note',True)
        chase_date=date_value(b.get('date'),required=True)
        method=text(b.get('method'),'Contact method',True,50)
        with self.connect(write=True) as db:
            row=self.find(db,'chases',identifier)
            c=json.loads(row['body'])
            if row['submission_id']!=sid:
                raise ValidationError('Chase-up belongs to a different tender.')
            if type(b.get('revision')) is not int or b['revision']!=c.get('revision',0):
                raise ValidationError('This chase-up changed in another window. Refresh and reopen it before saving.',409)
            if all(c.get(k)==v for k,v in [('note',note),('date',chase_date),('method',method)]):
                return {'ok':True}
            before={k:c.get(k) for k in ('note','date','method','updatedByName','updatedAt')}
            c.setdefault('edits',[]).append(before)
            c.update(note=note,date=chase_date,method=method,revision=c.get('revision',0)+1,
                     updatedBy=b.get('_actor_id'),updatedByName=b['author'],updatedAt=timestamp())
            db.execute('UPDATE chases SET body=? WHERE id=?',(json.dumps(c,ensure_ascii=False),identifier))
            old=self.find(db,'submissions',sid);item=json.loads(old['body'])
            history=[{k:v for k,v in json.loads(r[0]).items() if k!='edits'} for r in db.execute('SELECT body FROM chases WHERE submission_id=?',(sid,))]
            latest=max(history,key=lambda h:(h.get('date',''),h.get('createdAt','')))
            item.update(latest=latest['note'],revision=old['revision']+1)
            db.execute('UPDATE submissions SET body=?,revision=revision+1 WHERE id=?',(json.dumps(item,ensure_ascii=False),sid))
            self.activity(db,b.get('_actor_id'),b['author'],'Edited chase-up',item,{'chaseId':identifier,'before':before})
        return {'ok':True}

    @staticmethod
    def find(db, table, identifier):
        # table comes only from internal constants, never request data.
        row = db.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise ValidationError('Record not found.', 404)
        return row

    def all_data(self):
        with self._cache_lock:
            with self.connect() as db:
                generation=db.execute('SELECT value FROM tender_generation').fetchone()[0]
            if self._cache and self._cache[0]==generation:return self._cache[1]
            data=self._read_all_data()
            self._cache=(generation,data)
            return data

    def _read_all_data(self):
        with self.connect() as db:
            db.execute('BEGIN')
            submissions = []
            for row in db.execute('SELECT * FROM submissions'):
                item = json.loads(row['body'])
                item['revision'] = row['revision']
                submissions.append(item)
            pref = db.execute("SELECT body FROM settings WHERE id='preferences'").fetchone()
            return {
                'submissions': submissions,
                'chases': [{k:v for k,v in json.loads(r['body']).items() if k!='edits'} for r in db.execute('SELECT body FROM chases')],
                'reminders': [json.loads(r['body']) for r in db.execute('SELECT body FROM reminders')],
                'settings': json.loads(pref['body']) if pref else {'author':'Tonmoy','defaultDays':7},
                'report': self.seed['report'],
                'projectSummary': self.seed['projectSummary'],
            }

    def save_submission(self, b):
        fields = {k: text(b.get(k), k, k in ('project','builder')) for k in TEXT_FIELDS}
        if fields['pricing'] in ('4', '4.0'):
            fields['pricing'] = 'High'
        if fields['status'] not in ('Open','Won','Lost','Close','Hold'):
            raise ValidationError('Choose a valid TEC status.')
        fields['due'] = date_value(fields['due'])
        value = b.get('value')
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value < 0):
            raise ValidationError('Tender value must be zero or greater.')
        identifier = text(b.get('id'), 'Submission ID', limit=100) or str(uuid.uuid4())
        with self.connect(write=True) as db:
            if b.get('id'):
                old = self.find(db, 'submissions', identifier)
                if type(b.get('revision')) is not int or b['revision'] != old['revision']:
                    raise ValidationError('This tender changed in another window. Refresh and reopen it before saving.', 409)
                item = json.loads(old['body'])
                revision = old['revision'] + 1
            else:
                item, revision = {'latest':'','chaseNumber':''}, 0
            item.update(fields, id=identifier, value=value, revision=revision)
            if not b.get('id'):
                item.update(createdBy=b.get('_actor_id'),createdByName=b.get('author',''),createdAt=timestamp(),origin='Website')
            else:
                item.update(updatedBy=b.get('_actor_id'),updatedByName=b.get('author',''),updatedAt=timestamp())
            self.activity(db,b.get('_actor_id'),b.get('author'),'Updated tender' if b.get('id') else 'Created tender',item)
            if b.get('id'):
                db.execute('UPDATE submissions SET body=?,revision=? WHERE id=?', (json.dumps(item,ensure_ascii=False),revision,identifier))
            else:
                db.execute('INSERT INTO submissions VALUES(?,?,?)', (identifier,json.dumps(item,ensure_ascii=False),revision))
        return {'ok':True,'id':identifier}

    def add_chase(self, b):
        sid = text(b.get('submissionId'), 'Submission ID', True, 100)
        note = text(b.get('note'), 'Chase-up note', True)
        chase_date = date_value(b.get('date'), required=True)
        next_due = date_value(b.get('nextDue'), timed=True)
        method = text(b.get('method') or 'Email', 'Contact method', limit=50)
        author = text(b.get('author') or 'Tonmoy', 'Author', limit=100)
        reminder_note = text(b.get('reminderNote') or 'Follow up on tender progress', 'Reminder note', limit=2000)
        complete = text(b.get('completeReminder'), 'Reminder ID', limit=100)
        with self.connect(write=True) as db:
            old = self.find(db, 'submissions', sid)
            if complete:
                reminder = self.find(db, 'reminders', complete)
                if reminder['submission_id'] != sid:
                    raise ValidationError('Reminder belongs to a different tender.')
                r = json.loads(reminder['body'])
                r['done'] = True
                db.execute('UPDATE reminders SET body=? WHERE id=?',(json.dumps(r),complete))
            c = {'id':str(uuid.uuid4()),'submissionId':sid,'date':chase_date,'note':note,'method':method,'author':author,'authorId':b.get('_actor_id'),'createdAt':timestamp(),'revision':0}
            db.execute('INSERT INTO chases VALUES(?,?,?)',(c['id'],sid,json.dumps(c,ensure_ascii=False)))
            item = json.loads(old['body'])
            item.update(latest=note, statusUpdated=chase_date, revision=old['revision']+1)
            db.execute('UPDATE submissions SET body=?,revision=revision+1 WHERE id=?',(json.dumps(item,ensure_ascii=False),sid))
            self.activity(db,b.get('_actor_id'),author,'Recorded chase-up',item,{'chaseId':c['id']})
            if next_due:
                self.insert_reminder(db, sid, next_due, reminder_note)
        return {'ok':True}

    @staticmethod
    def insert_reminder(db, sid, due, note):
        r = {'id':str(uuid.uuid4()),'submissionId':sid,'due':due,'note':note,'done':False,'createdAt':timestamp()}
        db.execute('INSERT INTO reminders VALUES(?,?,?)',(r['id'],sid,json.dumps(r,ensure_ascii=False)))

    def save_reminder(self, b):
        identifier = text(b.get('id'), 'Reminder ID', limit=100)
        with self.connect(write=True) as db:
            if identifier:
                row = self.find(db, 'reminders', identifier)
                item = json.loads(row['body'])
                if 'done' in b:
                    if type(b['done']) is not bool:
                        raise ValidationError('Invalid reminder state.')
                    item['done'] = b['done']
                if b.get('due'):
                    item['due'] = date_value(b['due'], timed=True, required=True)
                db.execute('UPDATE reminders SET body=? WHERE id=?',(json.dumps(item,ensure_ascii=False),identifier))
            else:
                sid = text(b.get('submissionId'), 'Submission ID', True, 100)
                self.find(db,'submissions',sid)
                due = date_value(b.get('due'),timed=True,required=True)
                note = text(b.get('note') or 'Follow up', 'Reminder note', limit=2000)
                self.insert_reminder(db,sid,due,note)
            sid=item['submissionId'] if identifier else sid
            submission=json.loads(self.find(db,'submissions',sid)['body'])
            self.activity(db,b.get('_actor_id'),b.get('author'),'Updated reminder' if identifier else 'Scheduled follow-up',submission)
        return {'ok':True}

    def save_settings(self, b):
        author = text(b.get('author'), 'Recorded by', True, 100)
        days = b.get('defaultDays')
        if type(days) is not int or not 1 <= days <= 365:
            raise ValidationError('Follow-up interval must be 1–365 days.')
        with self.connect(write=True) as db:
            db.execute("INSERT INTO settings VALUES('preferences',?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",(json.dumps({'author':author,'defaultDays':days}),))
        return {'ok':True}

    def backup(self, destination):
        destination = Path(destination).resolve()
        if destination == self.path:
            raise ValueError('Backup destination must differ from the live database.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db, sqlite3.connect(destination) as target:
            db.backup(target)


    def delta(self, sid):
        with self.connect() as db:
            db.execute('BEGIN')
            row=db.execute('SELECT * FROM submissions WHERE id=?',(sid,)).fetchone()
            item=json.loads(row['body']) if row else None
            if item:item['revision']=row['revision']
            return {'submissionId':sid,'submission':item,
                    'chases':[{k:v for k,v in json.loads(r[0]).items() if k!='edits'} for r in db.execute('SELECT body FROM chases WHERE submission_id=?',(sid,))],
                    'reminders':[json.loads(r[0]) for r in db.execute('SELECT body FROM reminders WHERE submission_id=?',(sid,))]}

    def delete_submission(self, body, user):
        sid=text(body.get('id'),'Tender ID',True,100)
        with self.connect(write=True) as db:
            row=self.find(db,'submissions',sid)
            item=json.loads(row['body'])
            if user['role']!='admin' and item.get('createdBy')!=user['id']:
                raise ValidationError('Only an administrator or the tender creator can delete it.',403)
            if type(body.get('revision')) is not int or body['revision']!=row['revision']:
                raise ValidationError('This tender changed. Refresh before deleting.',409)
            db.execute('DELETE FROM reminders WHERE submission_id=?',(sid,))
            db.execute('DELETE FROM chases WHERE submission_id=?',(sid,))
            db.execute('DELETE FROM submissions WHERE id=?',(sid,))
        return self.delta(sid)

_store=None
_store_lock=threading.Lock()
def get_store():
    global _store
    with _store_lock:
        if _store is None:_store=Store()
        return _store

def daily_backup():
    """Snapshot an existing tender database without loading the tender app."""
    from datetime import datetime, timezone
    target=Path(os.environ.get('CONEST_TENDERS_DB_PATH') or database_path().parent/'tec_tenders.db')
    if not target.is_file():return
    folder=target.parent/'tender_backups';folder.mkdir(exist_ok=True)
    name=datetime.now(timezone.utc).strftime('%Y%m%d')+'.db'
    output=folder/name
    if output.exists():return
    pending=folder/(name+'.'+uuid.uuid4().hex+'.tmp')
    with _store_lock:
        if output.exists():return
        with sqlite3.connect(f'{target.resolve().as_uri()}?mode=ro',uri=True) as source,sqlite3.connect(pending) as dest:
            source.backup(dest)
        os.replace(pending,output)
        for old in folder.glob('*.db'):
            if old!=output:old.unlink()
