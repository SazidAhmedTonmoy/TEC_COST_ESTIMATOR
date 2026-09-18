"""Searchable, read-only upload history from retained import provenance.

Catalogue sheets are grouped into uploaded files. Lighting receipts retain the
actual uploaded filename (which can differ from a workbook's Source PDF column).
Older quote records without receipts remain legacy sources, not invented upload
events. Their uploader was explicitly confirmed by the customer as Md Sazid Ahmed
Tonmoy. Recorded upload receipts and their uploaders are never overwritten. Raw
supplier/catalogue files are not exposed or promised here.
"""
from __future__ import annotations
import json
from .accounts import AccessError

# Customer-confirmed attribution applies only to the receipt-less legacy branch.
# Match the exact named account, not the similarly named Tonmoy_1 account. The
# historical name remains visible when that account is absent; no grant/account
# or fabricated upload receipt is created, and history reads remain read-only.
_LEGACY_UPLOADER = ('Md Sazid Ahmed Tonmoy', 'Tonmoy')

_HISTORY_SQL = """
WITH legacy_identity(name,username) AS (VALUES (?,?)), legacy_uploader AS (
    SELECT u.id,i.name,i.username FROM legacy_identity i
    LEFT JOIN users u ON u.username=i.username COLLATE NOCASE
        AND TRIM(u.name)=i.name COLLATE NOCASE
), quote_counts AS (
    SELECT q.id,COUNT(DISTINCT g.id) AS items,COUNT(l.id) AS components
    FROM quotes q LEFT JOIN groups g ON g.quote_id=q.id LEFT JOIN lines l ON l.group_id=g.id
    GROUP BY q.id
), history AS (
    SELECT 'catalog:'||MIN(s.id) AS id,'catalog' AS kind,s.file_name AS filename,
        MAX(s.imported_at) AS imported_at,s.imported_by AS uploader_id,
        COALESCE(u.name,'Not recorded') AS uploader_name,COALESCE(u.username,'') AS username,
        COUNT(*) AS sheets,0 AS quotes,SUM(s.assembly_count) AS items,SUM(s.component_count) AS components,
        GROUP_CONCAT(DISTINCT s.sheet_name) AS references_text,
        COALESCE(GROUP_CONCAT(DISTINCT NULLIF(s.project_name,'')),'') AS projects_text,
        '' AS report_json,0 AS legacy
    FROM sources s LEFT JOIN users u ON u.id=s.imported_by
    GROUP BY s.file_sha256,s.file_name,s.imported_by
    UNION ALL
    SELECT 'lighting:'||r.rowid,'lighting',r.filename,r.created_at,r.user_id,
        COALESCE(u.name,'Not recorded'),COALESCE(u.username,''),0,0,0,0,
        COALESCE((SELECT GROUP_CONCAT(DISTINCT q.reference) FROM quotes q WHERE q.file_sha256=r.file_sha256),''),
        COALESCE((SELECT GROUP_CONCAT(DISTINCT q.project) FROM quotes q WHERE q.file_sha256=r.file_sha256),''),
        r.report_json,0
    FROM lighting_import_receipts r LEFT JOIN users u ON u.id=r.user_id
    UNION ALL
    SELECT 'legacy-lighting:'||MIN(q.id),'lighting',COALESCE(NULLIF(q.source,''),'Source not recorded'),
        MAX(q.imported_at),lu.id,lu.name,lu.username,0,COUNT(q.id),SUM(c.items),SUM(c.components),
        COALESCE(GROUP_CONCAT(DISTINCT q.reference),''),COALESCE(GROUP_CONCAT(DISTINCT q.project),''),'',1
    FROM quotes q JOIN quote_counts c ON c.id=q.id CROSS JOIN legacy_uploader lu
    WHERE NOT EXISTS (SELECT 1 FROM lighting_import_receipts r WHERE r.file_sha256=q.file_sha256
        AND q.file_sha256 IS NOT NULL AND q.file_sha256<>'')
    GROUP BY q.source,COALESCE(NULLIF(q.file_sha256,''),q.source),SUBSTR(q.imported_at,1,10)
)
"""


def _text(query, key, default=''):
    value = query.get(key, [default])
    return str(value[0] if isinstance(value, list) and value else value or default).strip()


def list_uploads(conn, user, query):
    actor = conn.execute('SELECT is_active FROM users WHERE id=?', (user['id'],)).fetchone()
    if not actor or not actor['is_active']:
        raise AccessError(403, 'An active account is required')
    term = _text(query, 'q')
    kind = _text(query, 'kind', 'all')
    who = _text(query, 'who', 'all')
    try:
        limit, offset = int(_text(query,'limit','20')), int(_text(query,'offset','0'))
    except (TypeError, ValueError):
        raise ValueError('Choose a valid upload history page') from None
    if len(term)>200 or kind not in ('all','catalog','lighting') or who not in ('all','me'):
        raise ValueError('Choose valid upload history filters')
    if not 1<=limit<=100 or not 0<=offset<=10000000:
        raise ValueError('Choose a valid upload history page')
    clauses, values = [], list(_LEGACY_UPLOADER)
    if kind!='all':
        clauses.append('kind=?');values.append(kind)
    if who=='me':
        clauses.append('uploader_id=?');values.append(user['id'])
    if term:
        # Literal search, including % and _, with bound parameters.
        escaped = term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        clauses.append("(filename||' '||references_text||' '||projects_text||' '||uploader_name||' '||username) LIKE ? ESCAPE '\\'")
        values.append('%'+escaped+'%')
    where = ' WHERE '+' AND '.join(clauses) if clauses else ''
    total = conn.execute(_HISTORY_SQL+'SELECT COUNT(*) FROM history'+where,values).fetchone()[0]
    rows = conn.execute(_HISTORY_SQL+'SELECT * FROM history'+where+' ORDER BY imported_at DESC,id DESC LIMIT ? OFFSET ?',(*values,limit,offset)).fetchall()
    result = []
    for row in rows:
        item=dict(row)
        # Never return absolute workstation/server source paths or receipt tokens.
        item['filename']=item['filename'].replace('\\','/').rsplit('/',1)[-1]
        report={}
        if item['report_json']:
            try:
                parsed=json.loads(item['report_json'])
                if isinstance(parsed,dict):report=parsed
            except (TypeError,ValueError):
                pass
        item.pop('report_json')
        item.pop('username')
        if report:
            for key, source in [('quotes','quotes_added'),('items','groups_added'),('components','lines_added')]:
                try:item[key]=max(0,int(report.get(source,0)))
                except (TypeError,ValueError):item[key]=0
            try:item['skipped']=max(0,int(report.get('quotes_skipped',0) or 0))
            except (TypeError,ValueError):item['skipped']=0
        else:
            item['skipped']=0
        item['legacy']=bool(item['legacy'])
        item['is_mine']=item['uploader_id']==user['id']
        result.append(item)
    return {'uploads':result,'total':total,'offset':offset,'limit':limit,
            'has_more':offset+len(result)<total,'q':term,'kind':kind,'who':who}
