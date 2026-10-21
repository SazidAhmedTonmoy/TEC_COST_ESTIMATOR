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
import weakref
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
VIEWS = {'/', '/dashboard', '/chase-up', '/search', '/projects', '/builders', '/calendar', '/reminders', '/settings'}
TEXT_FIELDS = ('project','builder','status','builderStatus','location','region','contact','email','month','due','statusUpdated','pricing','remarks','quoteNo')

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

def default_submission_team(due):
    # Owner-specified historical cutoff; undated records remain unassigned.
    return ('TEC BD TEAM' if due >= '2026-07-20' else 'TEC AU TEAM') if due else ''

def submission_teams():
    from .database import connect
    with connect() as conn:
        names=[r[0] for r in conn.execute('SELECT name FROM teams ORDER BY name COLLATE NOCASE')]
    return names

def team_directory():
    from .database import connect
    with connect() as conn:
        current={r['id']:r['name'] for r in conn.execute('SELECT id,name FROM teams')}
        aliases={r['name'].casefold():r['team_id'] for r in conn.execute('SELECT name,team_id FROM tender_team_aliases')}
    aliases.update({name.casefold():identifier for identifier,name in current.items()})
    return current,aliases

def live_teams(data):
    current,aliases=team_directory()
    def resolve(item):
        identifier=item.get('submittedByTeamId',aliases.get(item.get('submittedByTeam','').casefold()))
        return {**item,'submittedByTeam':current.get(identifier,''),'submittedByTeamId':identifier}
    result={**data,'teams':list(current.values())}
    if 'submissions' in result:result['submissions']=[resolve(s) for s in result['submissions']]
    if result.get('submission'):result['submission']=resolve(result['submission'])
    if 'relatedSubmissions' in result:result['relatedSubmissions']=[resolve(s) for s in result['relatedSubmissions']]
    return result

def builder_key(value):
    import re
    return re.sub(r'[^\w]', '', project_key(value))

def project_key(value):
    import unicodedata
    return ' '.join(unicodedata.normalize('NFKC',value or '').split()).casefold()

def submission_month(due):
    return date.fromisoformat(due).strftime('%b %Y') if due else ''

def normalize_fields(item):
    item['region']=str(item.get('region') or '').strip().upper()
    item['month']=submission_month(item.get('due',''))
    if '1900' in str(item.get('statusUpdated','')):item['statusUpdated']=''
    item['pricing']=item.get('pricing') or ''
    return item

def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')

class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('CONEST_TENDERS_DB_PATH') or database_path().parent / 'tec_tenders.db').resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache = None
        self._cache_lock = threading.Lock()
        self._keeper_lock = threading.Lock()
        self._database_keeper = None
        self._keeper_finalizer = None
        legacy = self.path.with_suffix('.sqlite3')
        if not self.path.exists() and legacy.is_file():
            with closing(sqlite3.connect(f'{legacy.as_uri()}?mode=ro',uri=True)) as source, closing(sqlite3.connect(self.path)) as target:
                source.backup(target)
        self.seed = json.loads((ROOT / 'tenders_seed' / 'seed.json').read_text(encoding='utf-8'))
        if self.path.is_file():
            with closing(sqlite3.connect(self.path)) as old:
                has_settings=old.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'").fetchone()
                migrated=has_settings and old.execute("SELECT 1 FROM settings WHERE id='attribution-v33'").fetchone()
                backup=self.path.with_suffix('.pre-v33.db')
                if has_settings and not migrated and not backup.exists():
                    with closing(sqlite3.connect(backup)) as target:
                        old.backup(target)
                if has_settings and not old.execute("SELECT 1 FROM settings WHERE id='submission-teams-v34'").fetchone():
                    backup34=self.path.with_suffix('.pre-v34.db')
                    if not backup34.exists():
                        with closing(sqlite3.connect(backup34)) as target:old.backup(target)
                if has_settings and not old.execute("SELECT 1 FROM settings WHERE id='normalized-fields-v34b'").fetchone():
                    backup_fields=self.path.with_suffix('.pre-v34b.db')
                    if not backup_fields.exists():
                        with closing(sqlite3.connect(backup_fields)) as target:old.backup(target)
        self.initialize()
        from .opportunities import initialize as initialize_opportunities
        from .opportunity_import import initialize_seed as initialize_opportunity_seed
        initialize_opportunities(self)
        initialize_opportunity_seed(self)

    def keep_open(self):
        """Keep the shared server database's WAL attached between requests.

        This idle connection is never used for request work and holds no read or
        write transaction. The cached Store owns it for the worker lifetime,
        matching the catalogue keeper. Short-lived Store(path) callers may use
        this explicitly, then call close() before removing their directory.
        """
        with self._keeper_lock:
            if self._database_keeper is None:
                keeper = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
                try:
                    keeper.execute('SELECT value FROM tender_generation').fetchone()
                except Exception:
                    keeper.close()
                    raise
                self._database_keeper = keeper
                # A discarded cached Store (including test replacement) closes
                # promptly; weakref also supplies an interpreter-exit fallback.
                self._keeper_finalizer = weakref.finalize(self, keeper.close)
        return self

    def close(self):
        """Release the idle keeper; existing request connections stay independent."""
        with self._keeper_lock:
            finalizer = self._keeper_finalizer
            self._keeper_finalizer = None
            self._database_keeper = None
            if finalizer is not None:
                finalizer()

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
            fresh=not db.execute("SELECT 1 FROM settings WHERE id='import-v1'").fetchone()
            if fresh:
                db.executemany('INSERT OR IGNORE INTO submissions VALUES(?,?,0)', [(s['id'], json.dumps({**s,'submittedByTeam':s.get('submittedByTeam',default_submission_team(s.get('due','')))}, ensure_ascii=False)) for s in self.seed['submissions']])
                db.executemany('INSERT OR IGNORE INTO chases VALUES(?,?,?)', [(c['id'], c['submissionId'], json.dumps(c, ensure_ascii=False)) for c in self.seed['chases']])
                db.execute("INSERT INTO settings VALUES('import-v1','true')")

            self.migrate_attribution(db)
            if not db.execute("SELECT 1 FROM settings WHERE id='submission-teams-v34'").fetchone():
                for row in db.execute('SELECT id,body FROM submissions').fetchall():
                    item=json.loads(row['body'])
                    if 'submittedByTeam' not in item:
                        item['submittedByTeam']=default_submission_team(item.get('due',''))
                        db.execute('UPDATE submissions SET body=?,revision=revision+1 WHERE id=?',(json.dumps(item,ensure_ascii=False),row['id']))
                db.execute("INSERT INTO settings VALUES('submission-teams-v34','true')")

            # Idempotent correction; existing history and manually entered records stay intact.
            for row in db.execute('SELECT id,body FROM submissions').fetchall():
                item = json.loads(row['body'])
                if str(item.get('pricing', '')).strip() in ('4', '4.0'):
                    item['pricing'] = 'High'
                    db.execute('UPDATE submissions SET body=?,revision=revision+1 WHERE id=?',
                               (json.dumps(item,ensure_ascii=False), row['id']))

            if not db.execute("SELECT 1 FROM settings WHERE id='normalized-fields-v34b'").fetchone():
                self.normalize_records(db,fresh,shared=True)
                db.execute("INSERT INTO settings VALUES('normalized-fields-v34b','true')")

    def link_contributors(self):
        from .database import connect
        with connect() as conn:
            users={row['username'].casefold():dict(row) for row in conn.execute("SELECT id,name,username FROM users WHERE username COLLATE NOCASE IN ('Tonmoy','Yunus')")}
        if users.get('tonmoy'):
            with self.connect() as db:
                credit=db.execute("SELECT 1 FROM settings WHERE id='confirmed-imports-v33c'").fetchone()
            if not credit:
                with self.connect(write=True) as db:
                    last_id=db.execute('SELECT COALESCE(MAX(id),0) FROM tender_activity WHERE actor_id=?',(users['tonmoy']['id'],)).fetchone()[0]
                    db.execute("INSERT OR IGNORE INTO settings VALUES('confirmed-imports-v33c',?)",(json.dumps({'actorId':users['tonmoy']['id'],'uploads':2,'throughActivityId':last_id}),))
        self.historical_yunus=users.get('yunus')
        if not users:return
        with self.connect() as db:
            if db.execute("SELECT 1 FROM settings WHERE id='contributor-accounts-v33b'").fetchone():return
        with self.connect(write=True) as db:
            for table,flag,account,idkey,namekey in [('submissions','legacyImported','tonmoy','importedBy','importedByName'),('chases','legacyChase','yunus','authorId','author')]:
                person=users.get(account)
                if not person:continue
                for row in db.execute('SELECT id,body FROM '+table).fetchall():
                    item=json.loads(row['body'])
                    if item.get(flag):
                        item.update({idkey:person['id'],namekey:person['name']})
                        db.execute('UPDATE '+table+' SET body=? WHERE id=?',(json.dumps(item,ensure_ascii=False),row['id']))
            if len(users)==2:db.execute("INSERT OR IGNORE INTO settings VALUES('contributor-accounts-v33b','true')")

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
            item.update(latest=latest['note'],statusUpdated=latest['date'],revision=old['revision']+1)
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

    def save_submission(self, b, _db=None):
        from contextlib import nullcontext
        fields = {k: text(b.get(k), k, k in ('project','builder')) for k in TEXT_FIELDS}
        if fields['pricing'] in ('4', '4.0'):
            fields['pricing'] = 'High'
        if fields['status'] not in ('Open','Won','Lost','Close','Hold'):
            raise ValidationError('Choose a valid TEC status.')
        fields['due'] = date_value(fields['due'])
        normalize_fields(fields)
        value = b.get('value')
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value < 0):
            raise ValidationError('Tender value must be zero or greater.')
        team=text(b.get('submittedByTeam'),'Submitted by team',limit=200) if 'submittedByTeam' in b else None
        identifier = text(b.get('id'), 'Submission ID', limit=100) or str(uuid.uuid4())
        with (self.connect(write=True) if _db is None else nullcontext(_db)) as db:
            existing=[json.loads(row[0]) for row in db.execute('SELECT body FROM submissions')]
            canonical=next((s['builder'] for s in existing if builder_key(s.get('builder'))==builder_key(fields['builder'])),None)
            if canonical:fields['builder']=canonical
            duplicate=next((s for s in existing if s['id']!=identifier and project_key(s.get('project'))==project_key(fields['project']) and builder_key(s.get('builder'))==builder_key(fields['builder'])),None)
            if duplicate:raise ValidationError('This project already has a submission for '+fields['builder']+'. Edit the existing tender instead.',409)
            if b.get('id'):
                old = self.find(db, 'submissions', identifier)
                if type(b.get('revision')) is not int or b['revision'] != old['revision']:
                    raise ValidationError('This tender changed in another window. Refresh and reopen it before saving.', 409)
                item = json.loads(old['body'])
                revision = old['revision'] + 1
            else:
                item, revision = {'latest':'','chaseNumber':''}, 0
            if 'quoteNo' not in b:fields['quoteNo']=item.get('quoteNo','')
            if team and team not in submission_teams():
                if team==item.get('submittedByTeam'):team=''
                else:raise ValidationError('Choose an existing submission team.')
            if not b.get('id'):
                peers=[json.loads(r[0]) for r in db.execute('SELECT body FROM submissions') if project_key(json.loads(r[0]).get('project'))==project_key(fields['project'])]
                if peers:
                    for key in ('region','due'):
                        if not fields[key]:fields[key]=next((p.get(key,'') for p in peers if p.get(key)), '')
                    fields['month']=submission_month(fields['due'])
            history=[json.loads(r[0]) for r in db.execute('SELECT body FROM chases WHERE submission_id=?',(identifier,))]
            fields['statusUpdated']=max((c.get('date','') for c in history),default='')
            item.update(fields, id=identifier, value=value, revision=revision)
            if team is not None:
                item['submittedByTeam']=team
                if team:
                    _,aliases=team_directory()
                    item['submittedByTeamId']=aliases.get(team.casefold())
                else:item['submittedByTeamId']=None
            else:
                item.setdefault('submittedByTeam',default_submission_team(fields['due']))
                if 'submittedByTeamId' not in item:
                    _,aliases=team_directory()
                    item['submittedByTeamId']=aliases.get(item['submittedByTeam'].casefold())
            if not b.get('id'):
                item.update(createdBy=b.get('_actor_id'),createdByName=b.get('author',''),createdAt=timestamp(),origin='Website')
            else:
                item.update(updatedBy=b.get('_actor_id'),updatedByName=b.get('author',''),updatedAt=timestamp())
            self.activity(db,b.get('_actor_id'),b.get('author'),'Updated tender' if b.get('id') else 'Created tender',item)
            if b.get('id'):
                db.execute('UPDATE submissions SET body=?,revision=? WHERE id=?', (json.dumps(item,ensure_ascii=False),revision,identifier))
            else:
                db.execute('INSERT INTO submissions VALUES(?,?,?)', (identifier,json.dumps(item,ensure_ascii=False),revision))
            self.sync_project(db,item,b.get('_actor_id'),b.get('author',''))
        return {'ok':True,'id':identifier}

    def save_submissions(self, b):
        builders=b.get('builders')
        if not isinstance(builders,list) or not 1<=len(builders)<=100:raise ValidationError('Choose between 1 and 100 builders.')
        if b.get('id'):raise ValidationError('Multiple builders are only supported for a new tender.')
        names=[text(v,'Builder',True,1000) for v in builders]
        if len({builder_key(v) for v in names})!=len(names):raise ValidationError('Choose each builder only once.')
        with self.connect(write=True) as db:
            results=[self.save_submission({**b,'builder':name},_db=db) for name in names]
        return {'ok':True,'id':results[0]['id'],'ids':[x['id'] for x in results]}

    def sync_project(self, db, source, actor_id=None, actor_name=''):
        fields={k:source.get(k,'') for k in ('region','due','month','value','submittedByTeam','quoteNo')}
        if 'submittedByTeamId' in source:fields['submittedByTeamId']=source['submittedByTeamId']
        for row in db.execute('SELECT id,body FROM submissions WHERE id!=?',(source['id'],)).fetchall():
            item=json.loads(row['body'])
            if project_key(item.get('project'))!=project_key(source['project']):continue
            if all(item.get(k,'')==v for k,v in fields.items()):continue
            item.update(fields,updatedBy=actor_id,updatedByName=actor_name,updatedAt=timestamp())
            db.execute('UPDATE submissions SET body=?,revision=revision+1 WHERE id=?',(json.dumps(item,ensure_ascii=False),row['id']))
            self.activity(db,actor_id,actor_name,'Updated project fields',item,{'sourceSubmission':source['id'],'fields':fields})

    def normalize_records(self, db, fresh=False, shared=False):
        history={}
        for row in db.execute('SELECT submission_id,body FROM chases'):
            chase=json.loads(row['body']);dt=chase.get('date','')
            if dt and not dt.startswith('1900'):history[row['submission_id']]=max(history.get(row['submission_id'],''),dt)
        rows=db.execute('SELECT id,body FROM submissions').fetchall()
        grouped={}
        if shared:
            from collections import Counter
            for row in rows:
                item=json.loads(row['body']);grouped.setdefault(project_key(item.get('project')),[]).append(item)
            for key,items in grouped.items():
                regions=Counter(str(i.get('region') or '').strip().upper() for i in items if str(i.get('region') or '').strip())
                grouped[key]={'due':max((i.get('due') or '' for i in items),default=''),'region':sorted(regions,key=lambda v:(-regions[v],v))[0] if regions else ''}
        for row in rows:
            before=json.loads(row['body']);item=dict(before)
            if shared:item.update(grouped[project_key(item.get('project'))])
            normalize_fields(item)
            item['statusUpdated']=history.get(row['id'],'')
            if item!=before:
                db.execute('UPDATE submissions SET body=?,revision=revision+? WHERE id=?',(json.dumps(item,ensure_ascii=False),0 if fresh else 1,row['id']))

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
            history=[json.loads(r[0]) for r in db.execute('SELECT body FROM chases WHERE submission_id=?',(sid,))]
            latest=max(history,key=lambda h:(h.get('date',''),h.get('createdAt','')))
            item.update(latest=latest['note'], statusUpdated=latest['date'], revision=old['revision']+1)
            db.execute('UPDATE submissions SET body=?,revision=revision+1 WHERE id=?',(json.dumps(item,ensure_ascii=False),sid))
            self.activity(db,b.get('_actor_id'),author,'Recorded chase-up',item,{'chaseId':c['id']})
            # Follow-ups are created only through the explicit reminder endpoint.
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
        with self.connect() as db, closing(sqlite3.connect(destination)) as target:
            db.backup(target)


    def delta(self, sid):
        with self.connect() as db:
            db.execute('BEGIN')
            row=db.execute('SELECT * FROM submissions WHERE id=?',(sid,)).fetchone()
            item=json.loads(row['body']) if row else None
            if item:item['revision']=row['revision']
            return {'submissionId':sid,'submission':item,
                    'relatedSubmissions':[{**json.loads(r['body']),'revision':r['revision']} for r in db.execute('SELECT * FROM submissions WHERE id!=?',(sid,)) if item and project_key(json.loads(r['body']).get('project'))==project_key(item.get('project'))],
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
        if _store is None:
            candidate=Store()
            try:
                candidate.keep_open()
                candidate.link_contributors()
            except Exception:
                candidate.close()
                raise
            _store=candidate
        return _store


def close_store():
    """Close the process-shared Store during an orderly server shutdown."""
    global _store
    with _store_lock:
        previous=_store
        _store=None
        if previous is not None:
            previous.close()

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
        with closing(sqlite3.connect(f'{target.resolve().as_uri()}?mode=ro',uri=True)) as source,closing(sqlite3.connect(pending)) as dest:
            source.backup(dest)
        os.replace(pending,output)
        for old in folder.glob('*.db'):
            if old!=output:old.unlink()
