"""Preview parsed assemblies without mutating the catalogue, then import selected rows."""
import json
import time
from pathlib import Path
from uuid import uuid4
from dataclasses import asdict
from .database import connect,database_path,write_lock,refresh_catalog_index
from .importer import parse_workbook,ParsedSheet,ParsedAssembly,ParsedComponent,_insert_assembly
from .utils import normalize_text,stable_hash,utc_now,sha256_file
from .catalog import get_catalog_item
from .productivity import capture_price,price_metadata
from .accounts import AccessError


def folder():
    p=database_path().parent/'import_previews';p.mkdir(exist_ok=True,parents=True);return p


def identity(item):
    return stable_hash({'name':normalize_text(item['name']),'unit':normalize_text(item.get('base_uom','')),
        'work':item.get('work_type','assembly'),'parts':sorted([(normalize_text(c['description']),normalize_text(c.get('size','')),
        normalize_text(c.get('uom','')),round(float(c['quantity_per_unit']),8)) for c in item['components']])})


def pricing(item):
    return stable_hash(sorted([(normalize_text(c['description']),normalize_text(c.get('size','')),normalize_text(c.get('uom','')),
      round(float(c['quantity_per_unit']),8),*[round(float(c.get(k,0)),8) for k in ('unit_material','material_factor','unit_hours','labor_factor','unit_labor_price')],
      c.get('labor_pricing','hours')) for c in item['components']]))


def totals(item):
    return {'material':sum(c['quantity_per_unit']*c['unit_material']*c['material_factor'] for c in item['components']),
      'hours':sum(c['quantity_per_unit']*c['unit_hours']*c['labor_factor'] for c in item['components'] if c.get('labor_pricing','hours')!='fixed'),
      'fixed_labor':sum(c['quantity_per_unit']*c.get('unit_labor_price',0)*c['labor_factor'] for c in item['components'] if c.get('labor_pricing')=='fixed')}


def candidates(conn):
    result={}
    parts={}
    for r in conn.execute('SELECT * FROM catalog_components ORDER BY line_order,id'):parts.setdefault(r['catalog_item_id'],[]).append(dict(r))
    for r in conn.execute('SELECT id,name,base_uom,work_type FROM catalog_items WHERE is_active=1 ORDER BY id DESC'):
        item=dict(r);item['components']=parts.get(r['id'],[])
        result.setdefault(identity(item),[]).append(item)
    return result


def build_preview(path,name,user,authorize=None):
    sheets=parse_workbook(path)
    rows=[]
    with connect() as conn:
        if authorize:authorize(conn)
        index=candidates(conn)
        for sheet in sheets:
            for assembly in sheet.assemblies:
                raw=asdict(assembly);matches=index.get(identity(raw),[])
                exact=next((m for m in matches if pricing(m)==pricing(raw)),None)
                status='duplicate' if exact else 'changed' if matches else 'new'
                match=exact or (matches[0] if matches else None)
                rows.append({'key':len(rows)+1,'sheet':sheet.sheet_name,'name':assembly.name,'unit':assembly.base_uom,
                    'basis':stable_hash(sorted((m['id'] or 0,pricing(m)) for m in matches)),
                    'status':status,'related_id':match['id'] if match else None,'before':totals(match) if match else None,
                    'after':totals(raw),'assembly':raw})
                # Repeated rows inside this workbook are duplicates too.
                index.setdefault(identity(raw),[]).append({**raw,'id':match['id'] if match else None})
    token=uuid4().hex
    data={'token':token,'owner':user['id'],'created':time.time(),'name':name,'path':str(path),
      'digest':sha256_file(path),'rows':rows,'issues':[{'sheet':s.sheet_name,**asdict(i)} for s in sheets for i in s.issues]}
    (folder()/(token+'.json')).write_text(json.dumps(data))
    public={k:v for k,v in data.items() if k not in ('owner','path','digest')}
    public['rows']=[{k:v for k,v in row.items() if k!='assembly'} for row in rows]
    return public


def commit_preview(token,user,payload,authorize):
    if len(token)!=32 or any(c not in '0123456789abcdef' for c in token):raise ValueError('Invalid preview')
    manifest=folder()/(token+'.json')
    if not manifest.exists():raise LookupError('Preview not found; upload the workbook again')
    data=json.loads(manifest.read_text())
    if data['owner']!=user['id']:raise AccessError(403,'This preview belongs to another user')
    if time.time()-data['created']>86400:raise AccessError(409,'Preview expired; upload the workbook again')
    selected=payload.get('selected')
    if not isinstance(selected,list) or any(type(i)is not int for i in selected):raise ValueError('Select the rows to import')
    valid={r['key'] for r in data['rows']}
    if set(selected)-valid:raise ValueError('Unknown preview row')
    if not selected:raise ValueError('Select at least one row')
    metadata=price_metadata(payload)
    with write_lock:
        if not manifest.exists():raise AccessError(409,'Preview already imported')
        with connect() as conn:
            authorize(conn)
            # Recompute classifications before committing; concurrent catalogue edits require a fresh preview.
            index=candidates(conn)
            for row in data['rows']:
                matches=index.get(identity(row['assembly']),[])
                exact=next((m for m in matches if pricing(m)==pricing(row['assembly'])),None)
                status='duplicate' if exact else 'changed' if matches else 'new'
                if row['key'] in selected and (status!=row['status'] or stable_hash(sorted((m['id'] or 0,pricing(m)) for m in matches))!=row['basis']):
                    raise AccessError(409,'The catalogue changed after this preview. Upload again to review current prices.')
                index.setdefault(identity(row['assembly']),[]).append({**row['assembly'],'id':row['related_id']})
        from .backups import create_backup
        backup=create_backup('before-import',user['id'])
        with connect() as conn:
            conn.execute('BEGIN IMMEDIATE');authorize(conn)
            source_ids={};created=0;duplicates=0
            for row in data['rows']:
                if row['key'] not in selected:continue
                # Identical data is already represented; codes alone never add a second copy.
                if row['status']=='duplicate':duplicates+=1;continue
                sheet=row['sheet']
                if sheet not in source_ids:
                    # A selection is a separate import batch, allowing later selection of previously skipped rows.
                    digest=stable_hash({'file':data['digest'],'token':token})
                    c=conn.execute('''INSERT INTO sources(file_name,file_sha256,sheet_name,project_name,import_format,row_count,header_count,
                     assembly_count,component_count,warning_count,imported_at,imported_by) VALUES(?,?,?,'','preview selection',0,0,0,0,0,?,?)''',
                     (data['name'],digest,sheet,utc_now(),user['id']))
                    source_ids[sheet]=c.lastrowid
                raw=dict(row['assembly']);raw['components']=[ParsedComponent(**c) for c in raw['components']]
                item_id,is_new=_insert_assembly(conn,ParsedAssembly(**raw),source_ids[sheet]);created+=int(is_new)
                conn.execute('UPDATE sources SET assembly_count=assembly_count+1,component_count=component_count+? WHERE id=?',(len(raw['components']),source_ids[sheet]))
                capture_price(conn,item_id,user['id'],{**metadata,'source':metadata['source'] or data['name']},row['related_id'])
            for issue in data['issues']:
                source_id=source_ids.get(issue['sheet'])
                if source_id:
                    conn.execute('INSERT INTO import_issues(source_id,severity,issue_code,message,row_no,payload_json,created_at) VALUES(?,?,?,?,?,?,?)',
                      (source_id,issue['severity'],issue['issue_code'],issue['message'],issue['row_no'],json.dumps(issue.get('payload',{})),utc_now()))
                    conn.execute('UPDATE sources SET warning_count=warning_count+1 WHERE id=?',(source_id,))
            if created:refresh_catalog_index(conn)
            conn.commit()
        manifest.unlink()
    return {'catalog_items_created':created,'duplicates_skipped':duplicates,'selected':len(selected),'backup':backup['name']}
