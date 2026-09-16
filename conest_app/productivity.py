"""Tender snapshots, attributable prices, presence, checks and deadline reminders."""
import json
import time
from datetime import date, timedelta
from .utils import utc_now, stable_hash, normalize_text
from .workspace import require_project, record_activity, check_revision, visible_projects
from .projects import calculate_project
from .accounts import AccessError


def initialize_productivity(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS tender_revisions(id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      label TEXT NOT NULL, snapshot_json TEXT NOT NULL, created_by INTEGER REFERENCES users(id),
      created_at TEXT NOT NULL, UNIQUE(project_id,label));
    CREATE TABLE IF NOT EXISTS project_presence(project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, tab_id TEXT NOT NULL,
      last_seen REAL NOT NULL, PRIMARY KEY(project_id,user_id,tab_id));
    CREATE TABLE IF NOT EXISTS check_acknowledgements(project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
      issue_key TEXT NOT NULL, reason TEXT NOT NULL, user_id INTEGER REFERENCES users(id), created_at TEXT NOT NULL,
      PRIMARY KEY(project_id,issue_key));
    CREATE TABLE IF NOT EXISTS deadline_reads(user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      reminder_key TEXT NOT NULL, read_at TEXT NOT NULL, PRIMARY KEY(user_id,reminder_key));
    CREATE TABLE IF NOT EXISTS catalog_price_history(id INTEGER PRIMARY KEY AUTOINCREMENT,
      catalog_item_id INTEGER REFERENCES catalog_items(id) ON DELETE CASCADE,
      related_item_id INTEGER REFERENCES catalog_items(id) ON DELETE SET NULL,
      supplier TEXT NOT NULL DEFAULT '', quote_date TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '',
      snapshot_json TEXT NOT NULL, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_price_history ON catalog_price_history(catalog_item_id,id DESC);
    ''')


def save_revision(conn,pid,user,payload):
    project=require_project(conn,pid,user)
    check_revision(project,payload)
    label=payload.get('label','').strip()
    if not label or len(label)>100: raise ValueError('Enter a revision name of up to 100 characters')
    if conn.execute('SELECT 1 FROM tender_revisions WHERE project_id=? AND label=?',(pid,label)).fetchone():raise ValueError('A revision with this name already exists. Choose another name.')
    snapshot=calculate_project(conn,pid)
    cursor=conn.execute('INSERT INTO tender_revisions(project_id,label,snapshot_json,created_by,created_at) VALUES(?,?,?,?,?)',
        (pid,label,json.dumps(snapshot),user['id'],utc_now()))
    record_activity(conn,pid,user,'Saved tender revision',label,touch=False)
    return cursor.lastrowid


def revisions(conn,pid,user):
    require_project(conn,pid,user,'view')
    return [{**dict(r),'can_delete':user['role']=='admin' or r['created_by']==user['id']} for r in conn.execute('''SELECT r.id,r.label,r.created_at,r.created_by,u.name AS author,
      json_extract(r.snapshot_json,'$.totals.quoted') AS quoted,
      json_extract(r.snapshot_json,'$.project.currency') AS currency
      FROM tender_revisions r LEFT JOIN users u ON u.id=r.created_by WHERE r.project_id=? ORDER BY r.id DESC''',(pid,))]


def delete_revision(conn,pid,rid,user):
    require_project(conn,pid,user,'view')
    row=conn.execute('SELECT created_by,label FROM tender_revisions WHERE project_id=? AND id=?',(pid,rid)).fetchone()
    if not row:raise LookupError('Tender revision not found')
    if user['role']!='admin' and row['created_by']!=user['id']:
        raise AccessError(403,'Only the revision creator or an administrator can delete it')
    conn.execute('DELETE FROM tender_revisions WHERE project_id=? AND id=?',(pid,rid))
    record_activity(conn,pid,user,'Deleted tender revision',row['label'],touch=False)


def revision_snapshot(conn,pid,rid,user):
    require_project(conn,pid,user,'view')
    row=conn.execute('SELECT * FROM tender_revisions WHERE project_id=? AND id=?',(pid,rid)).fetchone()
    if not row: raise LookupError('Tender revision not found')
    return json.loads(row['snapshot_json'])


def compare_snapshots(before,after):
    fields=('name_snapshot','size_snapshot','sort_order','category_snapshot','quantity','uom','work_type_snapshot','notes','quoted_total','supply_quantity_override','supply_unit_cost_override')
    component_fields=('description','size','is_supply_copy','fixed_quantity','source_quantity','quantity_per_unit','uom','unit_material','material_factor','unit_hours','labor_factor','labor_pricing','unit_labor_price')
    old={r['id']:r for r in before['lines']};new={r['id']:r for r in after['lines']}
    changes=[]
    for key in sorted(old.keys()|new.keys()):
        a,b=old.get(key),new.get(key)
        kind='Added' if not a else 'Removed' if not b else 'Changed'
        delta={f:{'before':a.get(f) if a else None,'after':b.get(f) if b else None} for f in fields if not a or not b or a.get(f)!=b.get(f)}
        def parts(line):return [{f:c.get(f) for f in component_fields} for c in line.get('components',[])] if line else []
        if a and b and parts(a)!=parts(b):delta['components']={'before':parts(a),'after':parts(b)}
        if delta:changes.append({'line_id':key,'name':(b or a)['name_snapshot'],'kind':kind,'fields':delta})
    settings={f:{'before':before['project'].get(f),'after':after['project'].get(f)} for f in
        ('name','client','currency','material_markup','labor_rate','overhead_markup','notes','scope_of_work','submission_deadline')
        if before['project'].get(f)!=after['project'].get(f)}
    return {'changes':changes,'settings':settings,'before_totals':before['totals'],'after_totals':after['totals'],
      'before_currency':before['project']['currency'],'after_currency':after['project']['currency']}


def heartbeat(conn,pid,user,payload):
    project=require_project(conn,pid,user,'view')
    tab=payload.get('tab_id','')
    if not isinstance(tab,str) or not 1<=len(tab)<=100:raise ValueError('Invalid browser tab identifier')
    conn.execute('DELETE FROM project_presence WHERE last_seen<?',(time.time()-90,))
    if payload.get('leave'):
        conn.execute('DELETE FROM project_presence WHERE project_id=? AND user_id=? AND tab_id=?',(pid,user['id'],tab))
    else:
        conn.execute('INSERT OR REPLACE INTO project_presence VALUES(?,?,?,?)',(pid,user['id'],tab,time.time()))
    people=[]
    for row in conn.execute('''SELECT DISTINCT u.id,u.name,u.role,t.name AS team FROM project_presence p
      JOIN users u ON u.id=p.user_id LEFT JOIN teams t ON t.id=u.team_id WHERE p.project_id=? AND u.is_active=1''',(pid,)):
        actor=dict(row)
        try:require_project(conn,pid,actor,'view')
        except AccessError:continue
        people.append(actor)
    editor=conn.execute('SELECT name FROM users WHERE id=?',(project['updated_by'],)).fetchone()
    return {'people':people,'revision':project['revision'],'updated_by':editor[0] if editor else None,'updated_at':project['updated_at']}


def reminders(conn,user):
    today=date.today();result=[]
    for p in visible_projects(conn,user):
        if not p['can_edit'] or p['status'] in ('submitted','completed') or not p['submission_deadline']:continue
        days=(date.fromisoformat(p['submission_deadline'])-today).days
        if days>7:continue
        stage='overdue' if days<0 else 'today' if days==0 else 'soon'
        key=f"{p['id']}:{p['submission_deadline']}:{stage}"
        read=conn.execute('SELECT 1 FROM deadline_reads WHERE user_id=? AND reminder_key=?',(user['id'],key)).fetchone()
        result.append({'key':key,'project_id':p['id'],'name':p['name'],'deadline':p['submission_deadline'],'days':days,'stage':stage,'read':bool(read)})
    return sorted(result,key=lambda r:r['deadline'])


def price_metadata(payload):
    result={k:payload.get(k,'') for k in ('supplier','quote_date','source')}
    for k,v in result.items():
        if not isinstance(v,str) or len(v)>1000:raise ValueError('Price source fields must be text of up to 1,000 characters')
        result[k]=v.strip()
    if result['quote_date']:
        if len(result['quote_date'])!=10:raise ValueError('Quote date must be YYYY-MM-DD')
        date.fromisoformat(result['quote_date'])
    return result


def capture_price(conn,item_id,user_id=None,metadata=None,related=None):
    from .catalog import get_catalog_item
    item=get_catalog_item(conn,item_id)
    if not item:raise LookupError('Catalog item not found')
    if related is not None:
        if type(related) is not int or not conn.execute('SELECT 1 FROM catalog_items WHERE id=?',(related,)).fetchone():raise ValueError('Source catalog item not found')
        if related!=item_id and not conn.execute('SELECT 1 FROM catalog_price_history WHERE catalog_item_id=?',(related,)).fetchone():
            capture_price(conn,related,user_id,{'source':'Existing price before a linked version was saved'})
    meta=price_metadata(metadata or {})
    snapshot={k:item.get(k) for k in ('name','base_uom','work_type','unit_material','unit_hours','unit_labor_price','components')}
    conn.execute('''INSERT INTO catalog_price_history(catalog_item_id,related_item_id,supplier,quote_date,source,snapshot_json,created_by,created_at)
      VALUES(?,?,?,?,?,?,?,?)''',(item_id,related,meta['supplier'],meta['quote_date'],meta['source'],json.dumps(snapshot),user_id,utc_now()))


def price_history(conn,item_id):
    from .catalog import get_catalog_item
    item=get_catalog_item(conn,item_id)
    if not item:raise LookupError('Catalog item not found')
    # Linked versions form a family; no matching by name alone across different products.
    ids={item_id}
    while True:
        old=len(ids)
        for r in conn.execute('SELECT catalog_item_id,related_item_id FROM catalog_price_history WHERE related_item_id IS NOT NULL'):
            if r[0] in ids or r[1] in ids:ids.update(r)
        if old==len(ids):break
    marks=','.join('?' for _ in ids)
    history=[]
    for r in conn.execute(f'''SELECT h.*,u.name AS author FROM catalog_price_history h LEFT JOIN users u ON u.id=h.created_by
      WHERE h.catalog_item_id IN ({marks}) ORDER BY h.id DESC''',tuple(ids)):
        row=dict(r);row['snapshot']=json.loads(row.pop('snapshot_json'));history.append(row)
    sources=[dict(r) for r in conn.execute(f'''SELECT DISTINCT s.file_name,s.sheet_name,s.imported_at FROM source_occurrences o
       JOIN sources s ON s.id=o.source_id WHERE o.catalog_item_id IN ({marks})''',tuple(ids))]
    return {'history':history,'sources':sources}
