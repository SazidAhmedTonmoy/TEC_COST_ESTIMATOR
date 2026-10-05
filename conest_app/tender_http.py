"""Tender routes share ConEst sessions, password policy and CSRF checks."""
import gzip
import json
from pathlib import Path
from . import tenders, accounts
from .accounts import AccessError

ROOT=Path(__file__).resolve().parents[1]

def send(handler, body, mime='application/json; charset=utf-8', filename=None, cache='no-store'):
    if not isinstance(body,bytes):body=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
    def accepts_gzip(value):
        choices={}
        for entry in value.lower().split(','):
            parts=entry.strip().split(';');quality=1.0
            for param in parts[1:]:
                if param.strip().startswith('q='):
                    try:quality=float(param.strip()[2:])
                    except ValueError:quality=0
            choices[parts[0].strip()]=quality
        return choices.get('gzip',choices.get('*',0))>0
    compressed=len(body)>1024 and accepts_gzip(handler.headers.get('Accept-Encoding',''))
    if compressed:body=gzip.compress(body,compresslevel=5)
    handler.send_response(200)
    handler.send_header('Content-Type',mime)
    handler.send_header('Content-Length',str(len(body)))
    handler.send_header('Cache-Control',cache)
    handler.send_header('Vary','Accept-Encoding')
    if compressed:handler.send_header('Content-Encoding','gzip')
    if filename:handler.send_header('Content-Disposition',f'attachment; filename="{filename}"')
    handler._security_headers();handler.end_headers();handler.wfile.write(body)

def route(h,path):
    try:
        if path=='/tenders' or path.startswith('/tenders/'):
            if h.command!='GET':raise tenders.ValidationError('Method not allowed',405)
            if path.startswith('/tenders/assets/'):
                import mimetypes
                name=path.removeprefix('/tenders/assets/')
                if Path(name).name!=name or name.startswith('.'):raise tenders.ValidationError('Not found',404)
                asset=ROOT/'tenders_web/assets'/name
                if not asset.is_file():raise tenders.ValidationError('Not found',404)
                send(h,asset.read_bytes(),mimetypes.guess_type(name)[0] or 'application/octet-stream',cache='public, max-age=31536000, immutable')
            else:h._send_file(ROOT/'tenders_web/index.html')
            return
        if path=='/api/tenders/bootstrap' and h.command=='GET':
            h._guard('/api/auth/session')
            payload={'user':h.user,'csrf_token':accounts.csrf_token(h.session_token)}
            if not h.user['must_change_password']:
                data={k:v for k,v in tenders.get_store().all_data().items() if k not in ('report','projectSummary')}
                data['settings']={**data['settings'],'author':h.user['name']}
                payload['data']=data
            send(h,payload);return
        h._guard(path)
        store=tenders.get_store()
        if path=='/api/tenders/data' and h.command=='GET':
            data={k:v for k,v in store.all_data().items() if k not in ('report','projectSummary')};data['settings']={**data['settings'],'author':h.user['name']}
            send(h,data);return
        if h.command not in ('POST','DELETE'):raise tenders.ValidationError('Not found',404)
        body=h._json_body()
        if path=='/api/tenders/export.xlsx' and h.command=='POST':
            from .tender_export import export_workbook
            ids=body.get('ids')
            if not isinstance(ids,list) or any(not isinstance(i,str) for i in ids):raise tenders.ValidationError('Choose submissions to export.')
            send(h,export_workbook(store.all_data(),ids,tenders.text(body.get('description'),'Filters',limit=4000)),
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','TEC-Tenders.xlsx');return
        if path=='/api/tenders/import' and h.command=='POST':
            import base64
            import binascii
            from .tender_import import import_workbook, MAX_BYTES
            encoded=body.get('content')
            if not isinstance(encoded,str) or len(encoded)>((MAX_BYTES+2)//3)*4:
                raise tenders.ValidationError('Choose a workbook smaller than 15 MB.')
            try:content=base64.b64decode(encoded,validate=True)
            except (ValueError,binascii.Error):raise tenders.ValidationError('Invalid workbook upload.')
            mode=body.get('mode','preview')
            if mode not in ('preview','apply'):raise tenders.ValidationError('Invalid import action.')
            expected=tenders.text(body.get('token'),'Preview token',required=True,limit=100) if mode=='apply' else None
            send(h,import_workbook(store,tenders.text(body.get('filename'),'Filename',required=True,limit=255),content,h.user,expected));return
        if path=='/api/tenders/submissions' and h.command=='DELETE':
            send(h,store.delete_submission(body,h.user));return
        routes={'submissions':store.save_submission,'chases':store.add_chase,'reminders':store.save_reminder}
        kind=path.removeprefix('/api/tenders/')
        if kind not in routes or h.command!='POST':raise tenders.ValidationError('Not found',404)
        body['author']=h.user['name'];body['_actor_id']=h.user['id']
        sid=body.get('submissionId')
        if kind=='reminders' and body.get('id'):
            with store.connect() as db:sid=store.find(db,'reminders',body['id'])['submission_id']
        result=routes[kind](body)
        if kind=='submissions':sid=result['id']
        send(h,store.delta(sid))
    except tenders.ValidationError as e:
        h._send_json({'error':str(e)},e.status)
