"""HTTP account routes and server-side access checks for every API method."""
import hmac
import os
import re
from http.cookies import SimpleCookie
from contextlib import contextmanager
from urllib.parse import urlparse, parse_qs

from . import accounts, workspace, teams, project_notes
from .database import connect, write_lock


class WorkspaceHTTP:
    user = None
    session_token = ''
    response_cookie = None

    def _read_token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            return cookie['conest_session'].value if 'conest_session' in cookie else ''
        except Exception:
            return ''

    def _set_session(self, token):
        self.session_token = token
        secure = '; Secure' if os.environ.get('CONEST_COOKIE_SECURE') == '1' else ''
        self.response_cookie = f'conest_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={accounts.SESSION_SECONDS if token else 0}{secure}'

    def _guard(self, path):
        self.user = None
        if not path.startswith('/api/') or path == '/api/health':
            return
        self.session_token = self._read_token()
        mutation = self.command not in ('GET', 'HEAD')
        if mutation:
            origin = self.headers.get('Origin')
            if origin:
                parsed = urlparse(origin)
                if parsed.scheme not in ('http', 'https') or parsed.netloc != self.headers.get('Host'):
                    raise accounts.AccessError(403, 'Request origin is not allowed')
            if self.headers.get('X-ConEst-Request') != '1':
                raise accounts.AccessError(403, 'Refresh the page and try again')
        if path == '/api/auth/login' and self.command == 'POST':
            return
        with connect() as conn:
            self._authorize_connection(conn, path)

    def _authorize_connection(self, conn, path):
        self.user = accounts.session_user(conn, self.session_token)
        if not self.user:
            raise accounts.AccessError(401, 'Please sign in to continue')
        self._set_session(self.session_token)
        mutation = self.command not in ('GET', 'HEAD')
        if mutation and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), accounts.csrf_token(self.session_token)):
            raise accounts.AccessError(403, 'Your session changed. Refresh the page and try again.')
        if self.user['must_change_password'] and path not in ('/api/auth/session', '/api/auth/profile', '/api/auth/profile/photo', '/api/auth/logout'):
            raise accounts.AccessError(403, 'Choose a new password in My profile to finish setting up your account')
        admin_required = (path.startswith('/api/users') or (path.startswith('/api/teams') and mutation)
                          or path == '/api/settings/saved-key' or (path.startswith('/api/settings') and mutation)
                          or path.startswith('/api/backups') or path.endswith('/review'))
        if admin_required and self.user['role'] != 'admin':
            raise accounts.AccessError(403, 'Administrator access is required')
        match = re.match(r'^/api/projects/(\d+)(?:/|$)', path)
        if match:
            mode = 'delete' if self.command == 'DELETE' and path == f'/api/projects/{match[1]}' else 'edit'
            # Presence and personal note-read receipts are viewer-local state.
            # Notes, revisions and every estimate/workflow mutation require edit.
            if (self.command=='POST' and re.fullmatch(r'/api/projects/\d+/copy',path)) or path.endswith('/presence'):
                mode='view'
            if self.command in ('GET','HEAD') or (self.command=='POST' and path.endswith('/notes/read')):
                mode='view'
            workspace.require_project(conn, int(match[1]), self.user, mode)

    @contextmanager
    def _read_connection(self):
        with connect() as conn:
            conn.execute('BEGIN')
            self._authorize_connection(conn, urlparse(self.path).path.rstrip('/') or '/')
            yield conn

    def _project_payload(self, conn, payload):
        result = dict(payload)
        if 'project' in result:
            result['project'] = workspace.decorate_project(conn, workspace.get_project(conn, result['project']['id']), self.user)
        if 'projects' in result:
            result['projects'] = workspace.visible_projects(conn, self.user)
        return result

    @contextmanager
    def _write_connection(self):
        with write_lock:
            with connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                # Recheck live membership and account state after acquiring the write lock.
                self._authorize_connection(conn, urlparse(self.path).path.rstrip('/') or '/')
                yield conn


    def _workspace_route(self, path):
        if not (path.startswith('/api/auth/') or path.startswith('/api/users') or path.startswith('/api/teams')
                or re.fullmatch(r'/api/projects/\d+/(workflow|activity|review|notes(?:/(?:\d+|status|read))?)', path)):
            return False
        self._guard(path)
        method = self.command
        note_state = re.fullmatch(r'/api/projects/(\d+)/notes/(status|read)',path)
        if note_state:
            pid=int(note_state[1])
            if method=='GET' and note_state[2]=='status':
                with self._read_connection() as conn: result=project_notes.note_status(conn,pid,self.user)
            elif method=='POST' and note_state[2]=='read':
                payload=self._json_body()
                with self._write_connection() as conn: result=project_notes.mark_notes_read(conn,pid,self.user,payload)
            else:raise accounts.AccessError(404,'Route not found')
            self._send_json({'success':True,**result})
            return True
        note_match = re.fullmatch(r'/api/projects/(\d+)/notes(?:/(\d+))?',path)
        if note_match:
            pid=int(note_match[1]); nid=int(note_match[2]) if note_match[2] else None
            if method=='GET' and nid is None:
                with self._read_connection() as conn: notes=project_notes.list_notes(conn,pid,self.user)
            elif method=='POST' and nid is None:
                payload=self._json_body()
                with self._write_connection() as conn: notes=project_notes.add_note(conn,pid,self.user,payload)
            elif method=='DELETE' and nid is not None:
                with self._write_connection() as conn: notes=project_notes.delete_note(conn,pid,nid,self.user)
            else: raise accounts.AccessError(404,'Route not found')
            with self._read_connection() as conn:
                access = workspace.permissions(conn, workspace.get_project(conn,pid), self.user)
            self._send_json({'success':True,'notes':notes,'can_edit':access['can_edit']},201 if method=='POST' else 200)
            return True
        if path == '/api/auth/login' and method == 'POST':
            payload = self._json_body()
            with write_lock, connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                user, token = accounts.login(conn, payload, self.client_address[0])
                conn.commit()
            self.user = user
            self._set_session(token)
            self._send_json({'success': True, 'user': user, 'csrf_token': accounts.csrf_token(token)})
            return True
        if path == '/api/auth/session' and method == 'GET':
            self._send_json({'success': True, 'user': self.user, 'csrf_token': accounts.csrf_token(self.session_token)})
            return True
        if path == '/api/auth/logout' and method == 'POST':
            with self._write_connection() as conn:
                conn.execute('DELETE FROM sessions WHERE token_hash=?', (accounts.token_digest(self.session_token),))
            self._set_session('')
            self._send_json({'success': True})
            return True
        if path == '/api/auth/profile/photo' and method == 'GET':
            with self._read_connection() as conn:
                photo = conn.execute('SELECT mime,image FROM user_avatars WHERE user_id=?', (self.user['id'],)).fetchone()
            if not photo:
                raise accounts.AccessError(404, 'Profile photo not found')
            body = bytes(photo['image'])
            self.send_response(200)
            self.send_header('Content-Type', photo['mime'])
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'private, no-store')
            self._security_headers(); self.end_headers(); self.wfile.write(body)
            return True
        if path == '/api/auth/profile' and method == 'PATCH':
            payload = self._json_body()
            with self._write_connection() as conn:
                user = accounts.edit_user(conn, self.user['id'], payload, self.user)
                # Rotate the current session even for a simple profile edit.
                conn.execute('DELETE FROM sessions WHERE token_hash=?', (accounts.token_digest(self.session_token),))
                token = accounts.start_session(conn, user['id'])
                conn.commit()
            self.user = user
            self._set_session(token)
            self._send_json({'success': True, 'user': user, 'csrf_token': accounts.csrf_token(token)})
            return True
        if path == '/api/users' and method == 'GET':
            with self._read_connection() as conn:
                users = workspace.user_directory(conn)
            self._send_json({'success': True, 'users': users})
            return True
        if path == '/api/users' and method == 'POST':
            payload = self._json_body()
            with self._write_connection() as conn:
                user = accounts.create_user(conn, payload)
                conn.commit()
            self._send_json({'success': True, 'user': user}, 201)
            return True
        match = re.fullmatch(r'/api/users/(\d+)', path)
        if match and method == 'PATCH':
            payload = self._json_body()
            with self._write_connection() as conn:
                user = accounts.edit_user(conn, int(match[1]), payload, self.user, admin=True)
                conn.commit()
            self._send_json({'success': True, 'user': user})
            return True
        match = re.fullmatch(r'/api/users/(\d+)', path)
        if match and method == 'DELETE':
            from .release_v23 import delete_account
            payload = self._json_body()
            with self._write_connection() as conn:
                result = delete_account(conn, int(match[1]), self.user, payload)
            self._send_json({'success': True, **result})
            return True
        if path == '/api/teams' and method == 'GET':
            with self._read_connection() as conn:
                result = teams.list_teams(conn, self.user)
            self._send_json({'success': True, 'teams': result})
            return True
        match = re.fullmatch(r'/api/teams/(\d+)', path)
        if (path == '/api/teams' and method == 'POST') or (match and method == 'PATCH'):
            payload = self._json_body()
            with self._write_connection() as conn:
                result = teams.save_team(conn, payload, self.user, int(match[1]) if match else None)
            self._send_json({'success': True, 'team': result}, 201 if method == 'POST' else 200)
            return True
        match = re.fullmatch(r'/api/projects/(\d+)/review', path)
        if match and method == 'POST':
            self._json_body()
            with self._write_connection() as conn:
                project = workspace.review_project(conn, int(match[1]), self.user)
            self._send_json({'success': True, 'project': project})
            return True
        match = re.fullmatch(r'/api/projects/(\d+)/workflow', path)
        if match and method == 'PATCH':
            payload = self._json_body()
            with self._write_connection() as conn:
                project = workspace.update_workflow(conn, int(match[1]), payload, self.user)
                conn.commit()
            self._send_json({'success': True, 'project': project})
            return True
        match = re.fullmatch(r'/api/projects/(\d+)/activity', path)
        if match and method == 'GET':
            query = parse_qs(urlparse(self.path).query)
            cursor_text = query.get('before_id', [None])[0]
            try:
                cursor = int(cursor_text) if cursor_text is not None else None
            except (ValueError, TypeError):
                raise ValueError('Choose a valid activity cursor') from None
            pid = int(match[1])
            with self._read_connection() as conn:
                activity = workspace.project_activity(conn, pid, self.user, before_id=cursor)
                contributors = workspace.project_contributors(conn, pid)
                total = conn.execute('SELECT COUNT(*) FROM project_activity WHERE project_id=?', (pid,)).fetchone()[0]
                more = bool(activity and conn.execute('SELECT 1 FROM project_activity WHERE project_id=? AND id<? LIMIT 1',
                    (pid, activity[-1]['id'])).fetchone())
            self._send_json({'success': True, 'activity': activity, 'contributors':contributors,
                             'total_activity':total, 'next_before_id':activity[-1]['id'] if more else None})
            return True
        raise accounts.AccessError(404, 'Route not found')

    def _public_payload(self, payload):
        # Project responses are decorated within their read/write transaction.
        # Do not pair a newer revision with an older set of prices or quantities.
        return payload

    def _audit(self, conn, project_id, action, details=''):
        workspace.record_activity(conn, project_id, self.user, action, details)
