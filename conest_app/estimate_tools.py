"""Copy and order saved estimate snapshots without touching their catalogue sources."""
import json
from .utils import utc_now,clean_text
from .workspace import check_revision,register_project,record_activity,require_project
from .projects import calculate_project,create_project


def insert_copy(conn,table,row,changes):
    values=dict(row);values.pop('id',None);values.update(changes)
    columns=list(values)
    return conn.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",tuple(values.values())).lastrowid


def line_record(conn,pid,lid,payload):
    line=conn.execute('SELECT * FROM project_lines WHERE project_id=? AND id=?',(pid,lid)).fetchone()
    if line is None:raise LookupError('Estimate item not found')
    check_revision(line,payload)
    return line


def copy_line(conn,pid,lid,payload):
    line=line_record(conn,pid,lid,payload)
    order=[r[0] for r in conn.execute('SELECT id FROM project_lines WHERE project_id=? ORDER BY sort_order,id',(pid,))]
    new=insert_copy(conn,'project_lines',line,{'revision':0,'created_at':utc_now(),'updated_at':utc_now()})
    for row in conn.execute('SELECT * FROM project_line_components WHERE project_line_id=? ORDER BY line_order,id',(lid,)).fetchall():
        insert_copy(conn,'project_line_components',row,{'project_line_id':new})
    order.insert(order.index(lid)+1,new)
    for i,ident in enumerate(order):conn.execute('UPDATE project_lines SET sort_order=? WHERE id=?',(i*10,ident))
    return new


def validate_order(ids,existing):
    if not isinstance(ids,list) or any(type(i) is not int for i in ids) or len(ids)!=len(existing) or set(ids)!=set(existing):
        raise ValueError('Order must contain every current item exactly once. Refresh and try again.')


def reorder_lines(conn,pid,payload):
    project=conn.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
    check_revision(project,payload)
    records=conn.execute('SELECT id,category_snapshot FROM project_lines WHERE project_id=?',(pid,)).fetchall()
    ids=payload.get('ids');validate_order(ids,[r['id'] for r in records])
    if 'scope_order' in payload:
        order=payload['scope_order'];categories={r['category_snapshot'] or 'Other' for r in records}
        if not isinstance(order,list) or any(not isinstance(c,str) for c in order) or len(order)!=len(categories) or set(order)!=categories:
            raise ValueError('Category order must contain every current category exactly once. Refresh and try again.')
        conn.execute('UPDATE projects SET scope_order=? WHERE id=?',(json.dumps(order),pid))
    for i,ident in enumerate(ids):conn.execute('UPDATE project_lines SET sort_order=?,revision=revision+1,updated_at=? WHERE id=?',(i*10,utc_now(),ident))


def component_action(conn,pid,lid,payload,action,cid=None):
    line=line_record(conn,pid,lid,payload)
    records=conn.execute('SELECT * FROM project_line_components WHERE project_line_id=? ORDER BY line_order,id',(lid,)).fetchall()
    ids=[r['id'] for r in records]
    if action=='copy':
        row=next((r for r in records if r['id']==cid),None)
        if row is None:raise LookupError('Component not found')
        from .estimate_options import supply_component
        primary=supply_component(line['category_snapshot'],[dict(r) for r in records])
        is_supply=primary and (row['id']==primary['id'] or row['is_supply_copy'])
        changes={'line_order':max(r['line_order'] for r in records)+1,'is_parent':0,'is_supply_copy':int(bool(is_supply))}
        if is_supply and row['id']==primary['id'] and line['supply_unit_cost_override'] is not None:
            changes.update(unit_material=line['supply_unit_cost_override'],material_factor=1)
        new=insert_copy(conn,'project_line_components',row,changes)
        ids.insert(ids.index(cid)+1,new)
    else:
        validate_order(payload.get('ids'),ids);ids=payload['ids']
    # Vacate UNIQUE line-order positions before assigning the new order.
    conn.execute('UPDATE project_line_components SET line_order=-id WHERE project_line_id=?',(lid,))
    for i,ident in enumerate(ids):conn.execute('UPDATE project_line_components SET line_order=? WHERE id=?',(i+1,ident))
    conn.execute('UPDATE project_lines SET revision=revision+1,updated_at=? WHERE id=?',(utc_now(),lid))


def copy_project(conn,pid,user,payload):
    source=require_project(conn,pid,user,'view');check_revision(source,payload)
    name=clean_text(payload.get('name') or source['name']+' — Copy')
    if not name or len(name)>500:raise ValueError('Project name must be 1–500 characters')
    deadline=payload.get('submission_deadline') or ''
    scope=payload.get('scope_of_work',source['scope_of_work'])
    if not isinstance(scope,str) or len(scope)>20000:raise ValueError('Scope of Work must be text of up to 20,000 characters')
    details={**dict(source),'name':name,'submission_deadline':deadline}
    if 'builders' in payload:details['builders']=payload['builders']
    new=create_project(conn,details)['project']['id']
    register_project(conn,new,user)
    conn.execute('UPDATE projects SET scope_of_work=?,scope_order=?,crew_size=?,hours_per_day=?,submission_deadline=? WHERE id=?',(scope,source['scope_order'],source['crew_size'],source['hours_per_day'],deadline,new))
    for line in conn.execute('SELECT * FROM project_lines WHERE project_id=? ORDER BY sort_order,id',(pid,)).fetchall():
        new_line=insert_copy(conn,'project_lines',line,{'project_id':new,'revision':0,'created_at':utc_now(),'updated_at':utc_now()})
        for row in conn.execute('SELECT * FROM project_line_components WHERE project_line_id=?',(line['id'],)).fetchall():
            insert_copy(conn,'project_line_components',row,{'project_line_id':new_line})
    record_activity(conn,new,user,'Copied project',source['name'])
    return new
