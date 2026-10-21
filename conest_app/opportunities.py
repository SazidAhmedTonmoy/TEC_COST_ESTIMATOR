"""Upcoming projects: transactional permissions, audit history and durable alerts.

Stored in the existing Tenders database, so its backup covers this workflow too.
No worker per web process: deadlines are reconciled by cron and on API reads.
"""
import json
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, urlsplit

from . import tenders
from .database import connect

STATUSES = ('awaiting', 'approved', 'rejected', 'expired', 'deleted')


def initialize(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS opportunities (
        id TEXT PRIMARY KEY, creator_id INTEGER NOT NULL, status TEXT NOT NULL,
        team_id INTEGER, region TEXT NOT NULL, deadline TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL, search_text TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS opportunity_deadlines ON opportunities(status,deadline);
      CREATE INDEX IF NOT EXISTS opportunity_teams ON opportunities(team_id,status,created_at);
      CREATE INDEX IF NOT EXISTS opportunity_created ON opportunities(created_at DESC);
      CREATE TABLE IF NOT EXISTS opportunity_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
        action TEXT NOT NULL, actor_id INTEGER, actor_name TEXT NOT NULL,
        details TEXT NOT NULL, created_at TEXT NOT NULL, effective_at TEXT NOT NULL,
        event_key TEXT UNIQUE);
      CREATE INDEX IF NOT EXISTS opportunity_history ON opportunity_events(opportunity_id,id DESC);
      CREATE TABLE IF NOT EXISTS opportunity_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL REFERENCES opportunity_events(id),
        user_id INTEGER NOT NULL, read_at TEXT, UNIQUE(event_id,user_id));
      CREATE INDEX IF NOT EXISTS opportunity_inbox ON opportunity_notifications(user_id,read_at,id DESC);
      CREATE TABLE IF NOT EXISTS opportunity_builders (key TEXT PRIMARY KEY, name TEXT NOT NULL);
    ''')


def directory(actor_id=None):
    with connect() as db:
        users = {r['id']: dict(r) for r in db.execute(
            'SELECT id,name,role,team_id,is_active FROM users')}
        teams = {r['id']: r['name'] for r in db.execute('SELECT id,name FROM teams ORDER BY name COLLATE NOCASE')}
    actor = users.get(actor_id)
    if actor_id is not None and (not actor or not actor['is_active']):
        raise tenders.ValidationError('Your account is no longer active.', 403)
    return users, teams, actor


def permissions(item, actor, teams):
    manage = actor['role'] == 'admin' or item['creator_id'] == actor['id']
    team = actor['team_id'] if actor['team_id'] in teams else None
    body = json.loads(item['body'])
    edit = manage or actor['id'] in body.get('editorUsers', []) or (team is not None and team in body.get('editorTeams', []))
    return {'canManage': manage, 'canEdit': bool(edit and item['status'] != 'deleted'),
            'canApprove': bool(team and item['status'] == 'awaiting'),
            'canReject': bool((team or manage) and item['status'] in ('awaiting', 'approved'))}


def present(item, actor, teams):
    body=json.loads(item['body'])
    body['editorTeams']=[i for i in body.get('editorTeams',[]) if i in teams]
    return {**body, 'id': item['id'], 'status': item['status'],
            'teamId': item['team_id'] if item['team_id'] in teams else None,
            'teamName': teams.get(item['team_id'], ''), 'region': item['region'],
            'deadline': item['deadline'], 'creatorId': item['creator_id'],
            'revision': item['revision'], 'createdAt': item['created_at'],
            'updatedAt': item['updated_at'], **permissions(item, actor, teams)}


def record(db, item, action, actor, details, users, *, effective=None, key=None, notify=True):
    now = tenders.timestamp()
    cur = db.execute('''INSERT OR IGNORE INTO opportunity_events
        (opportunity_id,action,actor_id,actor_name,details,created_at,effective_at,event_key)
        VALUES (?,?,?,?,?,?,?,?)''', (item['id'], action, actor['id'] if actor else None,
        actor['name'] if actor else 'System', json.dumps(details, ensure_ascii=False), now, effective or now, key))
    if not cur.rowcount or not notify:
        return
    recipients = {item['creator_id']} | {u['id'] for u in users.values()
        if u['is_active'] and item['team_id'] is not None and u['team_id'] == item['team_id']}
    body = json.loads(item['body'])
    recipients.update(body.get('editorUsers', []))
    recipients.update(u['id'] for u in users.values() if u['team_id'] in body.get('editorTeams', []))
    # Audit every change, notify relevant people, excluding the person taking action.
    db.executemany('INSERT OR IGNORE INTO opportunity_notifications(event_id,user_id) VALUES (?,?)',
        [(cur.lastrowid, uid) for uid in recipients if uid in users and users[uid]['is_active'] and (not actor or uid != actor['id'])])


def reconcile(store, today=None):
    today = today or datetime.now(ZoneInfo('Australia/Sydney')).date().isoformat()
    horizon = (datetime.fromisoformat(today).date() + timedelta(days=3)).isoformat()
    # Read first: no write-lock/generation churn when there is nothing to do.
    with store.connect() as db:
        pending = db.execute('''SELECT 1 FROM opportunities o WHERE status IN ('awaiting','approved')
            AND deadline<>'' AND deadline<=? AND (deadline<? OR NOT EXISTS
            (SELECT 1 FROM opportunity_events e WHERE e.event_key=o.id||':upcoming:'||o.deadline)) LIMIT 1''', (horizon,today)).fetchone()
    if not pending:
        return
    users, _, _ = directory()
    with store.connect(write=True, bump_generation=False) as db:
        rows = db.execute("SELECT * FROM opportunities WHERE status IN ('awaiting','approved') AND deadline<>'' AND deadline<=?", (horizon,)).fetchall()
        for item in rows:
            if item['deadline'] < today:
                db.execute("UPDATE opportunities SET status='expired',revision=revision+1,updated_at=? WHERE id=?", (tenders.timestamp(),item['id']))
                record(db,item,'Expired',None,{'previousStatus':item['status'],'deadline':item['deadline']},users,
                       effective=item['deadline']+'T23:59:59', key=f"{item['id']}:expired:{item['revision']}")
            else:
                record(db,item,'Deadline approaching',None,{'deadline':item['deadline']},users,
                       key=f"{item['id']}:upcoming:{item['deadline']}")


def require_revision(item, body):
    if type(body.get('revision')) is not int or body['revision'] != item['revision']:
        raise tenders.ValidationError('Someone changed this opportunity. Refresh it before saving your changes.',409)


def integer_ids(value, valid, label):
    if not isinstance(value,list) or len(value)>200 or any(type(v) is not int or v not in valid for v in value):
        raise tenders.ValidationError('Choose existing '+label+'.')
    return list(dict.fromkeys(value))


def save(store, payload, user):
    users, teams, actor = directory(user['id'])
    reconcile(store)
    known = {tenders.builder_key(s['builder']):s['builder'] for s in store.all_data()['submissions'] if s['builder']}
    with store.connect(write=True, bump_generation=False) as db:
        identifier = tenders.text(payload.get('id'),'Opportunity ID',limit=100)
        current = db.execute('SELECT * FROM opportunities WHERE id=?',(identifier,)).fetchone() if identifier else None
        if identifier and not current:
            raise tenders.ValidationError('Opportunity not found.',404)
        if current:
            require_revision(current,payload)
            access = permissions(current,actor,teams)
            if not access['canEdit']:
                raise tenders.ValidationError('Only the creator, an administrator or an authorised editor can edit this opportunity.',403)
        else:
            access = {'canManage':True}
        old = json.loads(current['body']) if current else {}
        team_id = payload.get('teamId') or None
        if team_id is not None and (type(team_id) is not int or team_id not in teams):
            raise tenders.ValidationError('Choose an existing team.')
        editors = integer_ids(payload.get('editorUsers',[]), {u['id'] for u in users.values() if u['is_active']}, 'people')
        editor_teams = integer_ids(payload.get('editorTeams',[]), teams, 'teams')
        current_team=current['team_id'] if current and current['team_id'] in teams else None
        if current and not access['canManage'] and (team_id != current_team or set(editors)!=set(old.get('editorUsers',[])) or set(editor_teams)!=(set(old.get('editorTeams',[])) & set(teams))):
            raise tenders.ValidationError('Only the creator or an administrator can assign teams or change access.',403)
        body = {k:tenders.text(payload.get(k), label,required=k=='project',limit=limit) for k,label,limit in
                [('project','Project name',500),('quoteNo','Quote No.',100),('scope','Working scope',20000),
                 ('category','Category',200),('budget','Budget',200),('location','Location',1000),
                 ('distance','Distance',100),('notes','Notes',20000)]}
        deadline = tenders.date_value(payload.get('deadline'))
        region = tenders.text(payload.get('region'),'Region',limit=50).upper()
        names = payload.get('builders',[])
        if not isinstance(names,list) or len(names)>100:
            raise tenders.ValidationError('Add up to 100 builders.')
        known.update({r['key']:r['name'] for r in db.execute('SELECT * FROM opportunity_builders')})
        builders = {}
        for value in names:
            name = tenders.text(value,'Builder',True,500)
            key = tenders.builder_key(name)
            if not key:raise tenders.ValidationError('Enter a builder name.')
            name = known.get(key,name)
            known[key] = name
            builders[key] = name
            db.execute('INSERT OR IGNORE INTO opportunity_builders VALUES (?,?)',(key,name))
        body.update(builders=list(builders.values()),editorUsers=editors,editorTeams=editor_teams,
                    creatorName=old.get('creatorName',actor['name']),source=old.get('source','Website'))
        now = tenders.timestamp()
        status = current['status'] if current else 'awaiting'
        if current and status == 'expired' and deadline != current['deadline']:
            if not access['canManage']:
                raise tenders.ValidationError('Only the creator or an administrator can reopen an expired opportunity.',403)
            status = 'awaiting'
        search = ' '.join([body['project'],body['quoteNo'],body['category'],body['scope'],body['notes'],body['location'],region,*body['builders']]).casefold()
        if current:
            before = {**old,'teamId':current['team_id'],'region':current['region'],'deadline':current['deadline']}
            after = {**body,'teamId':team_id,'region':region,'deadline':deadline}
            changes = {k:{'from':before.get(k),'to':v} for k,v in after.items() if before.get(k)!=v}
            if not changes:return present(current,actor,teams)
            db.execute('''UPDATE opportunities SET body=?,team_id=?,region=?,deadline=?,search_text=?,status=?,revision=revision+1,updated_at=? WHERE id=?''',
                       (json.dumps(body,ensure_ascii=False),team_id,region,deadline,search,status,now,identifier))
        else:
            identifier = uuid.uuid4().hex
            db.execute('INSERT INTO opportunities VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (identifier,actor['id'],status,team_id,region,deadline,json.dumps(body,ensure_ascii=False),search,0,now,now))
            changes = {**body,'teamId':team_id,'region':region,'deadline':deadline}
        item = db.execute('SELECT * FROM opportunities WHERE id=?',(identifier,)).fetchone()
        assigned_changed=team_id is not None and (not current or team_id != current['team_id'])
        record(db,item,'Updated' if current else 'Created',actor,changes,users,notify=not assigned_changed)
        if assigned_changed:
            record(db,item,'Team assigned',actor,{'team':teams[team_id],'previousTeam':teams.get(current['team_id'],'') if current else ''},users)
        if current and status != current['status']:
            record(db,item,'Reopened for approval',actor,{'deadline':deadline},users)
    reconcile(store)
    return detail(store,identifier,user)['opportunity']


def action(store,payload,user):
    users, teams, actor = directory(user['id'])
    reconcile(store)
    with store.connect(write=True, bump_generation=False) as db:
        item = db.execute('SELECT * FROM opportunities WHERE id=?',(tenders.text(payload.get('id'),'ID',True,100),)).fetchone()
        if not item:raise tenders.ValidationError('Opportunity not found.',404)
        require_revision(item,payload)
        access = permissions(item,actor,teams)
        choice = payload.get('action')
        reason = tenders.text(payload.get('reason'),'Reason',limit=4000)
        if choice == 'approve':
            if not access['canApprove']:raise tenders.ValidationError('An active team member must approve an awaiting opportunity.',403)
            status, label = 'approved','Approved'
        elif choice == 'reject':
            if not access['canReject']:raise tenders.ValidationError('You cannot reject this opportunity.',403)
            if not reason:raise tenders.ValidationError('Add a reason for rejecting this opportunity.')
            status, label = 'rejected','Rejected'
        elif choice == 'delete':
            if not access['canManage'] or item['status']=='deleted':raise tenders.ValidationError('Only the creator or an administrator can delete this opportunity.',403)
            status, label = 'deleted','Deleted'
        elif choice == 'reopen':
            if not access['canManage'] or item['status'] not in ('rejected','expired','deleted'):raise tenders.ValidationError('Only the creator or an administrator can reopen this opportunity.',403)
            today=datetime.now(ZoneInfo('Australia/Sydney')).date().isoformat()
            if item['status']!='deleted' and item['deadline'] and item['deadline']<today:raise tenders.ValidationError('Edit the opportunity and set a new deadline before reopening.')
            status, label = 'awaiting','Reopened for approval'
            if item['status']=='deleted':
                status='expired' if item['deadline'] and item['deadline']<today else 'awaiting'
                label='Restored'
        else:raise tenders.ValidationError('Unknown opportunity action.')
        db.execute('UPDATE opportunities SET status=?,revision=revision+1,updated_at=? WHERE id=?',(status,tenders.timestamp(),item['id']))
        record(db,item,label,actor,{'previousStatus':item['status'],'reason':reason,'team':teams.get(actor['team_id'],'')},users)
        result = db.execute('SELECT * FROM opportunities WHERE id=?',(item['id'],)).fetchone()
        return present(result,actor,teams)


def detail(store,identifier,user,before=0):
    _, teams, actor = directory(user['id'])
    reconcile(store)
    with store.connect() as db:
        item = db.execute('SELECT * FROM opportunities WHERE id=?',(identifier,)).fetchone()
        if not item:raise tenders.ValidationError('Opportunity not found.',404)
        rows = db.execute('SELECT * FROM opportunity_events WHERE opportunity_id=? AND (?=0 OR id<?) ORDER BY id DESC LIMIT 51',(identifier,before,before)).fetchall()
    events = [{**dict(r),'details':json.loads(r['details'])} for r in rows[:50]]
    return {'opportunity':present(item,actor,teams),'events':events,'nextBefore':events[-1]['id'] if len(rows)>50 else None}


def number(value,default=1):
    try:return max(1,int(value))
    except (TypeError,ValueError):return default


def listing(store,query,user):
    users, teams, actor = directory(user['id'])
    reconcile(store)
    status = query.get('status','all'); region = query.get('region','').upper(); team = query.get('team','')
    if status not in ('all',*STATUSES):raise tenders.ValidationError('Invalid status.')
    conditions, params = [], []
    if region:conditions.append('region=?');params.append(region)
    if team:
        if team=='mine':team=str(actor['team_id'] or -1)
        if team=='unassigned':
            if teams:conditions.append('(team_id IS NULL OR team_id NOT IN ('+','.join('?' for _ in teams)+'))');params.extend(teams)
        else:
            try:team_id=int(team)
            except ValueError:raise tenders.ValidationError('Choose a valid team filter.')
            conditions.append('team_id=?');params.append(team_id)
    search=tenders.text(query.get('q'),'Search',limit=500).casefold()
    if search:conditions.append("search_text LIKE ? ESCAPE '\\'");params.append('%'+search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
    where=' AND '.join(conditions) or '1=1'
    with store.connect() as db:
        counts={s:0 for s in STATUSES}
        counts.update({r['status']:r['n'] for r in db.execute(f'SELECT status,COUNT(*) n FROM opportunities WHERE {where} GROUP BY status',params)})
        active_where=where+(" AND status!='deleted'" if status=='all' else ' AND status=?')
        active_params=params+([] if status=='all' else [status])
        total=sum(counts[s] for s in STATUSES if s!='deleted') if status=='all' else counts[status]
        page=min(number(query.get('page')),max(1,(total+19)//20))
        order={'deadline':'deadline="",deadline ASC,created_at DESC','deadline-desc':'deadline="",deadline DESC,created_at DESC'}.get(query.get('sort'),'created_at DESC,id DESC')
        rows=db.execute(f'SELECT * FROM opportunities WHERE {active_where} ORDER BY {order} LIMIT 20 OFFSET ?',[*active_params,(page-1)*20]).fetchall()
        team_counts={r['team_id']:r['n'] for r in db.execute("SELECT team_id,COUNT(*) n FROM opportunities WHERE status!='deleted' GROUP BY team_id")}
        regions=sorted({'NSW','VIC','QLD','ACT','SA','WA','TAS','NT'}|{r[0] for r in db.execute("SELECT DISTINCT region FROM opportunities WHERE region<>''")})
        builders=[r[0] for r in db.execute('SELECT name FROM opportunity_builders ORDER BY name COLLATE NOCASE')]
    builders=sorted(set(builders)|{s['builder'] for s in store.all_data()['submissions'] if s['builder']},key=str.casefold)
    return {'items':[present(r,actor,teams) for r in rows],'total':total,'page':page,'counts':counts,
            'teams':[{'id':i,'name':name,'count':team_counts.get(i,0)} for i,name in teams.items()],
            'users':[{'id':u['id'],'name':u['name'],'teamId':u['team_id']} for u in users.values() if u['is_active']],
            'regions':regions,'builders':builders,'myTeamId':actor['team_id']}


def inbox(store,user):
    directory(user['id']);reconcile(store)
    with store.connect() as db:
        rows=db.execute('''SELECT n.id,n.read_at,e.opportunity_id,e.action,e.actor_name,e.created_at,
            json_extract(o.body,'$.project') project FROM opportunity_notifications n
            JOIN opportunity_events e ON e.id=n.event_id JOIN opportunities o ON o.id=e.opportunity_id
            WHERE n.user_id=? ORDER BY n.id DESC LIMIT 50''',(user['id'],)).fetchall()
        unread=db.execute('SELECT COUNT(*) FROM opportunity_notifications WHERE user_id=? AND read_at IS NULL',(user['id'],)).fetchone()[0]
    return {'items':[dict(r) for r in rows],'unread':unread}


def route(h,path,store):
    """Called only after the shared session and CSRF guards."""
    from .tender_http import send
    query={k:v[-1] for k,v in parse_qs(urlsplit(h.path).query).items()}
    base='/api/tenders/opportunities'
    if h.command=='GET':
        if path==base:send(h,listing(store,query,h.user));return
        if path==base+'/notifications':send(h,inbox(store,h.user));return
        if path.startswith(base+'/'):
            send(h,detail(store,path[len(base)+1:],h.user,number(query.get('before'),0)));return
    elif h.command=='POST':
        payload=h._json_body()
        if path==base:send(h,{'opportunity':save(store,payload,h.user)});return
        if path==base+'/action':send(h,{'opportunity':action(store,payload,h.user)});return
        if path==base+'/notifications/read':
            directory(h.user['id'])
            through=payload.get('through')
            if type(through) is not int or through<1:raise tenders.ValidationError('Invalid notification.')
            with store.connect(write=True, bump_generation=False) as db:
                db.execute('UPDATE opportunity_notifications SET read_at=? WHERE user_id=? AND id<=? AND read_at IS NULL',(tenders.timestamp(),h.user['id'],through))
            send(h,{'ok':True});return
    raise tenders.ValidationError('Not found',404)
