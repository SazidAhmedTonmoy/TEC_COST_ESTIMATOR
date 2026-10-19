"""Revocable, project-scoped public estimate views. Tokens are stored only as hashes."""
import hashlib
import re
import secrets
from html import escape
from .database import connect
from .projects import calculate_project
from .workspace import require_project, record_activity
from .accounts import AccessError
from .utils import utc_now


def table_exists(conn):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_public_links'").fetchone())


def shared_html(data):
    def text(value):return escape(str(value if value is not None else ''))
    def number(value):return f'{float(value or 0):,.2f}'
    def pairs(values):return '<dl>'+''.join('<div><dt>'+text(k)+'</dt><dd>'+text(v)+'</dd></div>' for k,v in values if v is not None and v!='')+'</dl>'
    p=data['project'];currency=text(p['currency'])
    details=[('Builders',p.get('client')),('Status',str(p.get('status','')).replace('_',' ').title()),('Submission deadline',p.get('submission_deadline')),('Review deadline',p.get('review_deadline')),('Scope of work',p.get('scope_of_work')),('Project remarks',p.get('notes')),('Currency',p.get('currency')),('Labour rate / hour',number(p.get('labor_rate'))),('Material mark-up',number(100*p.get('material_markup',0))+'%'),('Labour hour mark-up',number(100*p.get('labor_hours_markup',0))+'%'),('Final mark-up',number(100*p.get('overhead_markup',0))+'%'),('Crew size',p.get('crew_size')),('Hours / person / day',p.get('hours_per_day')),('Person days',number(data.get('crew_plan',{}).get('person_days'))),('Crew working days',number(data.get('crew_plan',{}).get('working_days')))]
    totals='<div class="totals">'+''.join('<article><span>'+label+'</span><strong>'+('' if key=='hours' else currency+' ')+number(data['totals'][key])+(' hrs' if key=='hours' else '')+'</strong></article>' for label,key in [('Materials','material'),('Labour hours','hours'),('Labour','labor'),('Quoted total','quoted')])+'</div>'
    rows=[]
    for line in data['lines']:
        line={**line, 'direct_total':line.get('total_material',0)+line.get('total_labor',0)}
        info=pairs([('Reference',line.get('reference_name')),('Size',line.get('size_snapshot')),('Description',line.get('description_snapshot')),('Remarks',line.get('notes')),('Work type',line.get('work_type_snapshot')),('Material mark-up excluded', 'Yes' if line.get('exclude_material_markup') else 'No'),('Hours mark-up excluded','Yes' if line.get('exclude_hours_markup') else 'No'),('Final mark-up excluded','Yes' if line.get('exclude_final_markup') else 'No')])
        components=''.join('<tr>'+''.join('<td>'+text(c.get(k,''))+'</td>' for k in ['description','size','uom'])+''.join('<td>'+number(c.get(k))+'</td>' for k in ['quantity_per_unit','scaled_quantity','unit_material','material_factor','unit_hours','labor_factor','unit_labor_price','total_material','total_hours','total_labor','grand_total'])+'<td>'+text(c.get('labor_pricing','hourly'))+'</td><td>'+text(c.get('notes',''))+'</td></tr>' for c in line.get('components',[]))
        info+='<div class="scroll"><table><thead><tr>'+''.join('<th>'+s+'</th>' for s in ['Component','Size','Unit','Qty / item','Total quantity','Material / unit','Material factor','Hours / unit','Labour factor','Fixed labour / unit','Total material','Total hours','Total labour','Direct cost','Labour basis','Remarks'])+'</tr></thead><tbody>'+components+'</tbody></table></div>'
        rows.append('<tr><td><details><summary>'+text(line.get('name_snapshot'))+'</summary>'+info+'</details></td><td>'+text(line.get('category_snapshot'))+'</td><td>'+number(line.get('quantity'))+' '+text(line.get('uom'))+'</td>'+''.join('<td>'+number(line.get(k))+'</td>' for k in ['unit_supply_material','unit_installation_material','total_material','unit_hours','total_hours','total_labor','direct_total','quoted_total'])+'</tr>')
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>'+text(p['name'])+' — TEC ConEst</title><link rel="stylesheet" href="/assets/public_project.css"></head><body><main><header><b>TEC ConEst Estimator</b><span>Shared project · Read only</span></header><h1>'+text(p['name'])+'</h1>'+totals+'<section><h2>Project details</h2>'+pairs(details)+'</section><section><h2>Estimate items and components</h2><p>All amounts in '+currency+'. Expand an item to view its component build-up.</p><div class="scroll"><table><thead><tr>'+''.join('<th>'+s+'</th>' for s in ['Item / component','Category','Quantity','Supply / unit','Install material / unit','Material','Hours / unit','Hours','Labour','Direct cost','Quoted'])+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></section></main></body></html>'


def route(handler,path):
    public=re.fullmatch(r'/share/project/([A-Za-z0-9_-]{43})',path)
    manage=re.fullmatch(r'/api/projects/(\d+)/share',path)
    if public:
        if handler.command!='GET':raise AccessError(405,'Shared projects are read-only')
        with connect() as conn:
            conn.execute('BEGIN')
            row=conn.execute('SELECT project_id FROM project_public_links WHERE token_hash=?',(hashlib.sha256(public[1].encode()).hexdigest(),)).fetchone() if table_exists(conn) else None
            if not row or not conn.execute('SELECT 1 FROM projects WHERE id=?',(row['project_id'],)).fetchone():raise AccessError(404,'This share link is unavailable or has been revoked')
            body=shared_html(calculate_project(conn,row['project_id'])).encode()
        handler.send_response(200)
        for key,value in [('Content-Type','text/html; charset=utf-8'),('Content-Length',str(len(body))),('Cache-Control','no-store'),('Referrer-Policy','no-referrer'),('X-Robots-Tag','noindex, nofollow'),('X-Content-Type-Options','nosniff'),('Content-Security-Policy',"default-src 'none'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")]:handler.send_header(key,value)
        handler.end_headers();handler.wfile.write(body);return True
    if not manage:return False
    handler._guard(path)
    if handler.command!='POST':raise AccessError(405,'Method not allowed')
    payload=handler._json_body();pid=int(manage[1]);action=payload.get('action')
    if action not in ('create','revoke'):raise ValueError('Choose create or revoke')
    with handler._write_connection() as conn:
        require_project(conn,pid,handler.user,'manage')
        conn.execute('CREATE TABLE IF NOT EXISTS project_public_links(project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE, token_hash TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL)')
        conn.execute('DELETE FROM project_public_links WHERE project_id=?',(pid,))
        result={'success':True}
        if action=='create':
            token=secrets.token_urlsafe(32)
            conn.execute('INSERT INTO project_public_links VALUES(?,?,?)',(pid,hashlib.sha256(token.encode()).hexdigest(),utc_now()))
            result['path']='/share/project/'+token
        record_activity(conn,pid,handler.user,'Created public project link' if action=='create' else 'Revoked public project link',touch=False)
    handler._send_json(result);return True
