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
from .estimate_sections import section_key


def table_exists(conn):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_public_links'").fetchone())


def shared_html(data):
    def text(v):return escape(str(v if v is not None else ''))
    def number(v):return f'{float(v or 0):,.2f}'
    p=data['project'];currency=text(p['currency'])
    def totals(values):
        return '<div class="totals">'+''.join('<div><span>'+label+'</span><strong>'+('' if key=='hours' else currency+' ')+number(values.get(key))+(' hrs' if key=='hours' else '')+'</strong></div>' for label,key in [('Total material','material'),('Total hours','hours'),('Total labour','labor'),('Quoted total','quoted')])+'</div>'
    def info(values):return '<dl>'+''.join('<div><dt>'+text(k)+'</dt><dd>'+text(v)+'</dd></div>' for k,v in values if v is not None and v!='')+'</dl>'
    groups={}
    for line in data['lines']:groups.setdefault(line.get('category_key') or section_key(line.get('category_snapshot')),[]).append(line)
    optional_lines=[line for line in data['lines'] if line.get('included_in_total') is False]
    has_excluded=bool(optional_lines)
    categories=[]
    for category,lines in groups.items():
        excluded=any(line.get('included_in_total') is False for line in lines)
        section_label='<span class="exclusion-label">Optional cost</span>' if excluded else ''
        aggregate={k:sum(float(l.get(f) or 0) for l in lines) for k,f in [('material','total_material'),('hours','total_hours'),('labor','total_labor'),('quoted','quoted_total')]}
        items=[]
        for line in lines:
            values={k:line.get(f) for k,f in [('material','total_material'),('hours','total_hours'),('labor','total_labor'),('quoted','quoted_total')]}
            components=''.join('<tr><td>'+text(c.get('description'))+'</td><td>'+text(c.get('size'))+'</td><td>'+number(c.get('scaled_quantity'))+' '+text(c.get('uom'))+'</td><td>'+text(c.get('notes'))+'</td></tr>' for c in line.get('components',[]))
            details=info([('Reference',line.get('reference_name')),('Description',line.get('description_snapshot')),('Size',line.get('size_snapshot')),('Remarks',line.get('notes'))])
            if components:details+='<div class="component-scroll"><table><thead><tr><th>Component</th><th>Size / specification</th><th>Total quantity</th><th>Remarks</th></tr></thead><tbody>'+components+'</tbody></table></div>'
            item_label='<small class="exclusion-label">Optional cost</small>' if line.get('included_in_total') is False else ''
            items.append('<details class="estimate-item'+(' section-excluded' if line.get('included_in_total') is False else '')+'"><summary><div class="item-title"><b>'+text(line.get('name_snapshot'))+'</b><small>'+number(line.get('quantity'))+' '+text(line.get('uom'))+'</small>'+item_label+'</div>'+totals(values)+'</summary><div class="item-detail">'+details+'</div></details>')
        categories.append('<details class="category'+(' section-excluded' if excluded else '')+'"><summary><div class="category-title"><h3>'+text(category)+'</h3><span>'+str(len(lines))+' items</span>'+section_label+'</div>'+totals(aggregate)+'</summary><div class="category-items">'+''.join(items)+'</div></details>')
    status={'draft':'Not started','in_progress':'In progress','in_review':'In review','submitted':'Submitted','closed':'Closed'}.get(p.get('status'),p.get('status',''))
    details=info([('Builders',p.get('client')),('Status',status),('Submission deadline',p.get('submission_deadline')),('Review deadline',p.get('review_deadline')),('Scope of work',p.get('scope_of_work')),('Project remarks',p.get('notes'))])
    total_heading='<h2>Included estimate total</h2>' if has_excluded else ''
    optional_summary=''
    if has_excluded:
        optional_values={key:sum(float(line.get(field) or 0) for line in optional_lines)
                         for key,field in [('material','total_material'),('hours','total_hours'),
                                           ('labor','total_labor'),('quoted','quoted_total')]}
        optional_summary='<section class="optional-totals"><h2>Optional costs</h2><p>These items are not included in the estimate total.</p>'+totals(optional_values)+'</section>'
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>'+text(p['name'])+' — TEC ConEst</title><link rel="stylesheet" href="/assets/public_project.css"></head><body><main><header><b>TEC ConEst Estimator</b><span>Shared project · Read only</span></header><h1>'+text(p['name'])+'</h1><section class="project-totals">'+total_heading+totals(data['totals'])+'</section>'+optional_summary+'<section><h2>Project details</h2>'+details+'</section><section class="estimate-section"><h2>Estimate categories</h2><p>All amounts in '+currency+'. Select + to expand a category or item, and − to shrink it.</p>'+''.join(categories)+'</section></main></body></html>'


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
