"""Copy and order saved estimate snapshots without touching their catalogue sources."""
import json
from .utils import utc_now,clean_text
from .workspace import check_revision,register_project,record_activity,require_project
from .projects import calculate_project,create_project
from .estimate_sections import excluded_categories, encode_exclusions, prune_exclusions, section_key, project_section_keys


def set_section_inclusion(conn, pid, user, payload):
    """Change a project's totals without deleting or repricing any estimate line."""
    project = require_project(conn, pid, user, 'edit')
    if 'expected_revision' not in payload:
        raise ValueError('Refresh the estimate before changing section inclusion')
    check_revision(project, payload)
    category = payload.get('category')
    included = payload.get('included')
    if not isinstance(category, str) or not category.strip() or len(category) > 500:
        raise ValueError('Choose a valid estimate section')
    category = section_key(category)
    if type(included) is not bool:
        raise ValueError('Section inclusion must be true or false')
    if category not in project_section_keys(conn, pid):
        raise LookupError('This section no longer exists. Refresh the estimate.')
    before = excluded_categories(project['excluded_categories'])
    after = before - {category} if included else before | {category}
    if before == after:
        return
    conn.execute('UPDATE projects SET excluded_categories=? WHERE id=?', (encode_exclusions(after), pid))
    record_activity(conn, pid, user, 'Included estimate section' if included else 'Excluded estimate section', category)


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
        order=payload['scope_order'];categories={section_key(r['category_snapshot']) for r in records}
        if not isinstance(order,list) or any(not isinstance(c,str) for c in order):
            raise ValueError('Category order must contain every current category exactly once. Refresh and try again.')
        order=[section_key(c) for c in order]
        if len(order)!=len(categories) or set(order)!=categories:
            raise ValueError('Category order must contain every current category exactly once. Refresh and try again.')
        conn.execute('UPDATE projects SET scope_order=? WHERE id=?',(json.dumps(order),pid))
    for i,ident in enumerate(ids):conn.execute('UPDATE project_lines SET sort_order=?,revision=revision+1,updated_at=? WHERE id=?',(i*10,utc_now(),ident))


def component_action(conn,pid,lid,payload,action,cid=None):
    line=line_record(conn,pid,lid,payload)
    records=conn.execute('SELECT * FROM project_line_components WHERE project_line_id=? ORDER BY line_order,id',(lid,)).fetchall()
    ids=[r['id'] for r in records]
    if action=='remove':
        if cid not in ids:raise LookupError('Component not found')
        from .estimate_options import supply_component
        primary=supply_component(section_key(line['category_snapshot']),[dict(r) for r in records])
        if primary and primary['id']==cid:
            conn.execute('UPDATE project_lines SET supply_unit_cost_override=NULL,supply_quantity_override=NULL WHERE id=?',(lid,))
        conn.execute('DELETE FROM project_line_components WHERE id=? AND project_line_id=?',(cid,lid))
        ids.remove(cid)
    elif action=='copy':
        row=next((r for r in records if r['id']==cid),None)
        if row is None:raise LookupError('Component not found')
        from .estimate_options import supply_component
        primary=supply_component(section_key(line['category_snapshot']),[dict(r) for r in records])
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
    reset=payload.get('zero_quantities',False)
    if type(reset) is not bool:raise ValueError('Zero quantities must be true or false')
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
        changes={'project_id':new,'revision':0,'created_at':utc_now(),'updated_at':utc_now()}
        if reset:changes.update(quantity=0,supply_quantity_override=None)
        new_line=insert_copy(conn,'project_lines',line,changes)
        for row in conn.execute('SELECT * FROM project_line_components WHERE project_line_id=?',(line['id'],)).fetchall():
            changes={'project_line_id':new_line}
            if reset and row['fixed_quantity']:changes['quantity_per_unit']=0
            insert_copy(conn,'project_line_components',row,changes)
    conn.execute('UPDATE projects SET excluded_categories=? WHERE id=?',
                 (encode_exclusions(excluded_categories(source['excluded_categories'])),new))
    prune_exclusions(conn,new)
    record_activity(conn,new,user,'Copied project',source['name'])
    return new


def delete_section(conn,pid,user,payload):
    project=require_project(conn,pid,user,'edit')
    if 'expected_revision' not in payload:raise ValueError('Refresh the estimate before deleting a section')
    check_revision(project,payload)
    category=payload.get('category')
    if not isinstance(category,str) or not clean_text(category):raise ValueError('Choose a section to delete')
    category=section_key(category)
    rows=[r for r in conn.execute('SELECT id,category_snapshot FROM project_lines WHERE project_id=?',(pid,))
          if section_key(r['category_snapshot'])==category]
    if not rows:raise LookupError('This section no longer exists. Refresh the estimate.')
    from .productivity import save_revision
    from uuid import uuid4
    save_revision(conn,pid,user,{'label':'Before section deletion · '+utc_now()+' · '+uuid4().hex[:8]})
    conn.executemany('DELETE FROM project_lines WHERE id=? AND project_id=?',((r['id'],pid) for r in rows))
    try:order=json.loads(project['scope_order'] or '[]')
    except (ValueError,TypeError):order=[]
    conn.execute('UPDATE projects SET scope_order=? WHERE id=?',(json.dumps(list(dict.fromkeys(section_key(x) for x in order if isinstance(x,str) and section_key(x)!=category))),pid))
    prune_exclusions(conn,pid)
    record_activity(conn,pid,user,'Deleted estimate section',f'{category} · {len(rows)} items')
