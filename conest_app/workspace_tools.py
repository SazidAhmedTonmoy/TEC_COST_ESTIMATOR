"""Authenticated user guide and account clipboard."""
import json
from . import help_guide
from .utils import utc_now


def read_state(conn, uid, key):
    row=conn.execute('SELECT body FROM user_workspace_state WHERE user_id=? AND key=?',(uid,key)).fetchone()
    return json.loads(row[0]) if row else {}


def save_state(conn, uid, key, value):
    conn.execute('INSERT INTO user_workspace_state VALUES(?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET body=excluded.body',(uid,key,json.dumps(value,ensure_ascii=False)))


def route(h,path):
    if path not in ('/api/clipboard', '/api/help/guide'):
        return False
    h._guard(path)
    uid=h.user['id']
    if path=='/api/help/guide' and h.command=='GET':
        h._send_json(help_guide.guide_payload());return True
    if path=='/api/clipboard':
        if h.command=='GET':
            with h._read_connection() as db:value=read_state(db,uid,'clipboard')
            h._send_json(value);return True
        if h.command=='POST':
            value=h._json_body();component=value.get('component')
            if component is not None and (not isinstance(component,dict) or len(json.dumps(component))>50000):raise ValueError('Invalid copied component.')
            value={'component':component,'userId':uid,'updatedAt':utc_now()}
            with h._write_connection() as db:save_state(db,uid,'clipboard',value)
            h._send_json(value);return True
    return False
