"""Supplier quotes in the main application database; types stay internal."""
from pathlib import Path
from datetime import datetime
from collections import OrderedDict
from contextlib import contextmanager
from decimal import Decimal,InvalidOperation
import hashlib,io,json,os,re,sqlite3,threading
from .database import database_path, write_lock

LOCK=write_lock
def db_path():
    return database_path()

def ensure_schema(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS quotes(id INTEGER PRIMARY KEY,reference TEXT NOT NULL,project TEXT,quote_date TEXT,source TEXT,content_hash TEXT NOT NULL,imported_at TEXT NOT NULL,total_ex REAL,UNIQUE(reference,quote_date,content_hash));
        CREATE TABLE IF NOT EXISTS groups(id INTEGER PRIMARY KEY,quote_id INTEGER NOT NULL REFERENCES quotes(id),type_code TEXT,base_qty REAL,description TEXT,supplier TEXT,cat_no TEXT,search_text TEXT,source_group TEXT);
        CREATE TABLE IF NOT EXISTS lines(id INTEGER PRIMARY KEY,group_id INTEGER NOT NULL REFERENCES groups(id),line_order INTEGER,item_no TEXT,type_raw TEXT,type_effective TEXT,supplier TEXT,quantity REAL,cat_no TEXT,description TEXT,raw_description TEXT,unit_ex REAL,total_ex REAL,status TEXT,page INTEGER,source_row INTEGER,connection_basis TEXT,source_values TEXT);
        CREATE INDEX IF NOT EXISTS idx_lighting_lines_group ON lines(group_id);CREATE INDEX IF NOT EXISTS idx_lighting_groups_quote ON groups(quote_id);''')

@contextmanager
def connect():
    path=db_path();path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path,timeout=30);conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON');conn.execute('PRAGMA busy_timeout=30000')
    try:
        ensure_schema(conn)
        yield conn;conn.commit()
    except:conn.rollback();raise
    finally:conn.close()

def clean(value):return re.sub(r'\s+',' ',str(value or '')).strip()
def number(value):
    if value is None or str(value).strip() in ('','-','—'):return None
    text=str(value).strip().replace(',','').replace('$','')
    try:
        d=Decimal(text)
        if not d.is_finite():raise ValueError('Non-finite price or quantity')
        return float(d)
    except InvalidOperation:raise ValueError('Invalid price or quantity: '+text[:30])
def date_text(value):
    if hasattr(value,'strftime'):return value.strftime('%Y-%m-%d')
    value=clean(value)
    for fmt in ('%Y-%m-%d','%A, %d %B %Y','%d/%m/%Y','%d %B %Y'):
        try:return datetime.strptime(value,fmt).strftime('%Y-%m-%d')
        except ValueError:pass
    return value

def effective_type(raw,description):
    if clean(raw):return clean(raw).upper()
    match=re.search(r'\bType\s+([A-Z][A-Z0-9_./-]*(?:\s+OPT)?)\b',description,re.I)
    return clean(match[1]).upper() if match else ''
def display_description(description):
    return clean(re.sub(r'(?:\|\s*)?\bType\s+[A-Z][A-Z0-9_./-]*(?:\s+OPT)?\b','',description,flags=re.I))

def normal_line(values,index):
    desc=str(values.get('Description') or '').strip();cat=clean(values.get('Cat No'));qty=number(values.get('Qty'));unit=number(values.get('Unit Ex GST'));total=number(values.get('Total Ex GST'))
    # Commercial notes without pricing are excluded; priced freight is retained even if Cat No says NOTE.
    if not desc or (qty is None and unit is None and total is None):return None
    if cat.upper() in ('NOTE','NOTES') and unit is None and total is None:return None
    if not cat and not clean(values.get('Supplier')):return None
    if any(v is not None and v<0 for v in (qty,unit,total)):raise ValueError('Negative quote amounts need review before importing')
    if total is None and qty is not None and unit is not None:total=round(qty*unit,2)
    typ=effective_type(values.get('Type'),desc)
    return dict(item_no=clean(values.get('Item')),type_raw=clean(values.get('Type')),type_effective=typ,
        supplier=clean(values.get('Supplier')),quantity=qty,cat_no=cat,description=display_description(desc),raw_description=desc,
        unit_ex=unit,total_ex=total,status=clean(values.get('Status')) or ('Not quoted' if unit is None else 'Quoted'),
        source_values=json.dumps(values,default=str,ensure_ascii=False),page=int(number(values.get('PDF Page')) or 0),source_row=index,source_group=clean(values.get('Connection Group')))

def parse_xlsx(content):
    from openpyxl import load_workbook
    wb=load_workbook(io.BytesIO(content),data_only=True,read_only=True)
    try:
        if 'All Items' not in wb.sheetnames:raise ValueError('Use a connected price workbook with an All Items sheet')
        rows=wb['All Items'].iter_rows(values_only=True);headers=next(rows)
        needed={'Project','Quote Ref','Quote Date','Supplier','Qty','Cat No','Description','Unit Ex GST','Total Ex GST'}
        if not needed.issubset(set(headers)):raise ValueError('The All Items sheet is missing required quote columns')
        quotes=OrderedDict();excluded=0
        for i,row in enumerate(rows,2):
            values=dict(zip(headers,row));ref=clean(values.get('Quote Ref'))
            if not ref:continue
            line=normal_line(values,i)
            if line is None:excluded+=1;continue
            key=(ref,date_text(values.get('Quote Date')))
            quote=quotes.setdefault(key,dict(reference=ref,quote_date=key[1],project=clean(values.get('Project')),source=clean(values.get('Source PDF')),total_ex=None,lines=[]))
            quote['lines'].append(line)
        if 'Project Index' in wb.sheetnames:
            for row in wb['Project Index'].iter_rows(min_row=4,values_only=True):
                if len(row)>6:
                    key=(clean(row[3]),date_text(row[2]))
                    if key in quotes:quotes[key]['total_ex']=number(row[6])
        if not quotes:raise ValueError('No supported price rows found')
        return list(quotes.values()),excluded
    finally:wb.close()

def parse_pdf(content,filename):
    import pdfplumber
    quote=dict(reference='',project='',quote_date='',source=filename,total_ex=None,lines=[]);excluded=0
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages)>100:raise ValueError('Upload a quote of at most 100 pages')
        text=pdf.pages[0].extract_text() or ''
        ref=re.search(r'REF:\s*([A-Z0-9-]+)',text,re.I)
        if not ref:raise ValueError('No supported TLE quote reference found; scanned PDFs need OCR first')
        quote['reference']=ref[1]
        dat=re.search(r'DATE:\s*(.*?)\s*PROJECT:',text,re.I)
        quote['quote_date']=date_text(dat[1]) if dat else ''
        for page_no,page in enumerate(pdf.pages,1):
            for table in page.extract_tables():
                active=False
                for row_no,row in enumerate(table,1):
                    if len(row)!=12:continue
                    if clean(row[0])=='TO:' and page_no==1:quote['project']=clean(row[3])
                    if clean(row[0])=='ITEM' and clean(row[4]).upper()=='CAT NO':active=True;continue
                    if not active:continue
                    if not any(clean(x) for x in row[:10]):
                        if row[10]:quote['total_ex']=number(row[10])
                        continue
                    values=dict(zip(['Item','Type','Supplier','Qty','Cat No','Description','ETA','Unit Ex GST','GST','Unit Inc GST','Total Ex GST','Total Inc GST'],row));values['PDF Page']=page_no
                    line=normal_line(values,page_no*1000+row_no)
                    if line:quote['lines'].append(line)
                    else:excluded+=1
        if not quote['lines']:raise ValueError('No supported price rows found; use a text-based TLE quotation PDF')
        if not quote['project']:quote['project']=quote['reference']
    return [quote],excluded

def group_lines(lines):
    groups=OrderedDict();previous=None
    for index,line in enumerate(lines):
        explicit=line['type_effective']
        if explicit:key=explicit;basis='Same type' if key in groups else 'Primary'
        elif previous is not None:key=previous;basis='Blank type → previous'
        else:key=f'__untyped_{index}';basis='Standalone; no preceding type'
        # Description-embedded type is authoritative when the separate Type column is empty.
        if not line['type_raw'] and explicit:basis+=' (type in description)'
        if explicit:previous=key
        groups.setdefault(key,[]).append({**line,'type_effective':explicit or ('' if key.startswith('__untyped_') else key),'connection_basis':basis})
    return groups

def quote_digest(quote):
    # Same quoted line re-uploaded through XLSX or PDF must not create another record.
    fields=('item_no','type_effective','supplier','quantity','cat_no','description','unit_ex','total_ex')
    data=[{k:clean(l[k]).casefold() if isinstance(l[k],str) else l[k] for k in fields} for l in quote['lines']]
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def import_content(filename,content):
    if len(content)>30*1024*1024:raise ValueError('Upload a file smaller than 30 MB')
    suffix=Path(filename).suffix.lower()
    quotes,excluded=parse_xlsx(content) if suffix=='.xlsx' else parse_pdf(content,filename) if suffix=='.pdf' else (_ for _ in ()).throw(ValueError('Upload XLSX or PDF'))
    return save_quotes(quotes,excluded)

def save_quotes(quotes,excluded=0):
    report={'quotes_added':0,'quotes_skipped':0,'groups_added':0,'lines_added':0,'notes_excluded':excluded}
    with LOCK,connect() as conn:
        pending=[]
        for quote in quotes:
            digest=quote_digest(quote)
            if conn.execute('SELECT 1 FROM quotes WHERE reference=? AND quote_date=? AND content_hash=?',(quote['reference'],quote['quote_date'],digest)).fetchone():report['quotes_skipped']+=1
            else:pending.append((quote,digest))
        if pending and conn.execute('SELECT COUNT(*) FROM quotes').fetchone()[0]:
            from .backups import create_backup
            create_backup('before-import')
        for quote,digest in pending:
            qid=conn.execute('INSERT INTO quotes(reference,project,quote_date,source,content_hash,imported_at,total_ex) VALUES(?,?,?,?,?,?,?)',(quote['reference'],quote['project'],quote['quote_date'],quote['source'],digest,datetime.now().isoformat(),quote['total_ex'])).lastrowid
            for typ,members in group_lines(quote['lines']).items():
                primary=members[0];search=' '.join([quote['project'],quote['reference']]+[str(l.get(k) or '') for l in members for k in ('supplier','cat_no','description')]).casefold()
                gid=conn.execute('INSERT INTO groups(quote_id,type_code,base_qty,description,supplier,cat_no,search_text,source_group) VALUES(?,?,?,?,?,?,?,?)',(qid,typ,primary['quantity'],primary['description'],primary['supplier'],primary['cat_no'],search,primary['source_group'])).lastrowid
                for index,line in enumerate(members):
                    keys=('item_no','type_raw','type_effective','supplier','quantity','cat_no','description','raw_description','unit_ex','total_ex','status','page','source_row','connection_basis','source_values')
                    conn.execute('INSERT INTO lines(group_id,line_order,'+','.join(keys)+') VALUES('+','.join('?' for _ in range(len(keys)+2))+')',(gid,index,*(line[k] for k in keys)))
                report['groups_added']+=1;report['lines_added']+=len(members)
            report['quotes_added']+=1
    return report

def search(query='',limit=40,offset=0,supplier=''):
    terms=clean(query).casefold().split()[:12];offset=max(0,int(offset));limit=min(100,max(1,int(limit)))
    where=' AND '.join('instr(g.search_text,?)>0' for _ in terms) or '1=1'
    supplier=clean(supplier)
    if supplier:
        where+=' AND EXISTS (SELECT 1 FROM lines sl WHERE sl.group_id=g.id AND sl.supplier=? COLLATE NOCASE)'
        terms.append(supplier)
    with connect() as conn:
        count=conn.execute(f'SELECT COUNT(*) FROM groups g WHERE {where}',terms).fetchone()[0]
        rows=conn.execute(f'''SELECT g.id,g.description,g.supplier,g.cat_no,g.base_qty,q.reference,q.project,q.quote_date,q.source,
            COUNT(l.id) component_count,SUM(l.total_ex) connected_total_ex,SUM(CASE WHEN l.total_ex IS NULL THEN 1 ELSE 0 END) missing_prices
            FROM groups g JOIN quotes q ON q.id=g.quote_id JOIN lines l ON l.group_id=g.id WHERE {where}
            GROUP BY g.id ORDER BY q.quote_date DESC,q.id DESC,g.id LIMIT ? OFFSET ?''',(*terms,limit,offset)).fetchall()
        results=[]
        for row in rows:
            item=dict(row);item['connected_unit_ex']=item['connected_total_ex']/item['base_qty'] if item['base_qty'] and not item['missing_prices'] else None
            results.append(item)
        stats={name:conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for name,table in [('quotes','quotes'),('groups','groups'),('lines','lines')]}
        return {'results':results,'total':count,'offset':offset,'stats':stats,'suppliers':[r[0] for r in conn.execute("SELECT DISTINCT supplier FROM lines WHERE supplier<>'' ORDER BY supplier COLLATE NOCASE")]}

def detail(ident):
    with connect() as conn:
        row=conn.execute('SELECT g.id,g.description,g.supplier,g.cat_no,g.base_qty,q.reference,q.project,q.quote_date,q.source FROM groups g JOIN quotes q ON q.id=g.quote_id WHERE g.id=?',(ident,)).fetchone()
        if row is None:raise LookupError('Lighting price group not found')
        item=dict(row);item['components']=[dict(l) for l in conn.execute('SELECT item_no,supplier,quantity,cat_no,description,unit_ex,total_ex,status,page FROM lines WHERE group_id=? ORDER BY line_order,id',(ident,))]
        item['missing_prices']=sum(l['total_ex'] is None for l in item['components'])
        item['connected_total_ex']=sum(l['total_ex'] or 0 for l in item['components'])
        item['connected_unit_ex']=item['connected_total_ex']/item['base_qty'] if item['base_qty'] and not item['missing_prices'] else None
        for l in item['components']:l['quantity_per_primary']=l['quantity']/item['base_qty'] if item['base_qty'] and l['quantity'] is not None else None
        return item
