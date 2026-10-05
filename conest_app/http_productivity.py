import re
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from . import productivity as p, backups
from .accounts import AccessError
from .database import connect,write_lock
from .projects import calculate_project
from .exporter import export_project


class ProductivityHTTP:
    def _productivity_route(self,path):
        transfer=re.fullmatch(r'/api/projects/(\d+)/json',path)
        if transfer or path=='/api/project-json/import':
            from . import project_json
            self._guard(path)
            if transfer and self.command=='GET':
                with self._read_connection() as conn:result=project_json.export_json(conn,int(transfer[1]),self.user)
            elif path=='/api/project-json/import' and self.command=='POST':
                payload=self._json_body()
                with self._write_connection() as conn:result={'id':project_json.import_json(conn,payload,self.user)}
            else:raise AccessError(405,'Method not allowed')
            self._send_json(result);return True

        project=re.fullmatch(r'/api/projects/(\d+)/(revisions(?:/\d+(?:/export)?)?|presence)',path)
        price=re.fullmatch(r'/api/catalog/(\d+)/price-history',path)
        backup=re.fullmatch(r'/api/backups(?:/([^/]+)(?:/(restore|download))?)?',path)
        reminder=path in ('/api/reminders','/api/reminders/read')
        if not (project or price or backup or reminder):return False
        self._guard(path);method=self.command
        if backup:
            if self.user['role']!='admin':raise AccessError(403,'Administrator access is required')
            name,action=backup[1],backup[2]
            # Backup/restore have no open write transaction: SQLite backup copies a committed database.
            with write_lock:
                with connect() as conn:self._authorize_connection(conn,path)
                if method=='GET' and not name:result={'backups':backups.list_backups()}
                elif method=='POST' and not name:result={'backup':backups.create_backup('manual',self.user['id'])}
                elif method=='GET' and action=='download':
                    self._send_file(backups.backup_path(name),name);return True
                elif method=='POST' and action=='restore':
                    payload=self._json_body()
                    if payload.get('confirmation')!='RESTORE':raise ValueError('Type RESTORE to confirm replacing all current database data')
                    result=backups.restore_backup(name)
                    self._set_session('')
                else:raise AccessError(404,'Route not found')
        elif reminder:
            if method=='GET' and path=='/api/reminders':
                with self._read_connection() as conn:result={'reminders':p.reminders(conn,self.user)}
            elif method=='POST' and path.endswith('/read'):
                payload=self._json_body()
                with self._write_connection() as conn:
                    current=p.reminders(conn,self.user)
                    key=payload.get('key')
                    if key not in {r['key'] for r in current}:raise ValueError('Reminder is no longer current')
                    conn.execute('INSERT OR REPLACE INTO deadline_reads VALUES(?,?,?)',(self.user['id'],key,p.utc_now()))
                    result={'reminders':p.reminders(conn,self.user)}
            else:raise AccessError(404,'Route not found')
        elif price:
            item_id=int(price[1])
            if method=='GET':
                with self._read_connection() as conn:result=p.price_history(conn,item_id)
            elif method=='POST':
                payload=self._json_body()
                with self._write_connection() as conn:
                    p.capture_price(conn,item_id,self.user['id'],payload)
                    result=p.price_history(conn,item_id)
            else:raise AccessError(404,'Route not found')
        else:
            pid=int(project[1]);suffix=project[2]
            if suffix=='presence' and method=='POST':
                payload=self._json_body()
                with self._write_connection() as conn:result=p.heartbeat(conn,pid,self.user,payload)
            elif suffix=='revisions' and method=='GET':
                with self._read_connection() as conn:result={'revisions':p.revisions(conn,pid,self.user)}
            elif suffix=='revisions' and method=='POST':
                payload=self._json_body()
                with self._write_connection() as conn:
                    rid=p.save_revision(conn,pid,self.user,payload)
                    result={'id':rid,'revisions':p.revisions(conn,pid,self.user)}
            elif re.fullmatch(r'revisions/\d+',suffix) and method=='DELETE':
                with self._write_connection() as conn:
                    p.delete_revision(conn,pid,int(suffix.split('/')[1]),self.user)
                    result={'revisions':p.revisions(conn,pid,self.user)}
            elif suffix.startswith('revisions/') and method=='GET':
                rid=int(suffix.split('/')[1])
                with self._read_connection() as conn:
                    snapshot=p.revision_snapshot(conn,pid,rid,self.user)
                    if suffix.endswith('/export'):
                        # Export from an isolated database with archived estimate rows, never mutate live data.
                        with sqlite3.connect(':memory:') as isolated:
                            isolated.row_factory=sqlite3.Row;conn.backup(isolated)
                            isolated.execute('PRAGMA foreign_keys=ON')
                            isolated.execute('DELETE FROM project_lines WHERE project_id=?',(pid,))
                            def insert(table,row):
                                columns=[r[1] for r in isolated.execute(f'PRAGMA table_info({table})')]
                                values={k:v for k,v in row.items() if k in columns}
                                isolated.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",tuple(values.values()))
                            for line in snapshot['lines']:
                                insert('project_lines',line)
                                for component in line['components']:insert('project_line_components',component)
                            fields=('name','client','currency','material_markup','labor_rate','overhead_markup','notes')
                            isolated.execute('UPDATE projects SET '+','.join(f'{f}=?' for f in fields)+' WHERE id=?',tuple(snapshot['project'][f] for f in fields)+(pid,))
                            with tempfile.TemporaryDirectory() as directory:
                                target=Path(directory)/f'Tender_revision_{rid}.xlsx'
                                export_project(isolated,pid,target);self._send_file(target,target.name)
                        return True
                    query=parse_qs(urlparse(self.path).query)
                    other=query.get('compare',['current'])[0]
                    after=calculate_project(conn,pid) if other=='current' else p.revision_snapshot(conn,pid,int(other),self.user)
                    result={'snapshot':snapshot,'comparison':p.compare_snapshots(snapshot,after)}
            else:raise AccessError(404,'Route not found')
        self._send_json({'success':True,**result})
        return True
