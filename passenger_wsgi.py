from __future__ import annotations

import io
import gzip
from wsgiref.util import is_hop_by_hop
import os
import sys
import threading
import time
import sqlite3
import atexit
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('CONEST_COOKIE_SECURE', '1')
os.environ.setdefault('CONEST_DB_PATH', str(ROOT / 'data' / 'conest_catalog.db'))

import app as conest

_init_lock = threading.Lock()
_initialized = False
_database_keeper = None


def _ensure_initialized():
    global _initialized, _database_keeper
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        # v2.4 connect() checks the schema and upgrades only when needed,
        # using the existing cross-process migration lock.
        with conest.connect() as conn:
            conn.execute('SELECT version FROM schema_version LIMIT 1').fetchone()
        conest.IMPORT_DIR.mkdir(parents=True, exist_ok=True)
        conest.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        # Keep the WAL attached between requests, as the standalone server does.
        # This connection holds no transaction and is never used for request work.
        keeper=sqlite3.connect(str(conest.database_path()),check_same_thread=False)
        keeper.execute('SELECT version FROM schema_version LIMIT 1').fetchone()
        _database_keeper=keeper
        atexit.register(keeper.close)
        _initialized = True


class _NoCloseBytesIO(io.BytesIO):
    def close(self):
        # Preserve the in-memory response after BaseHTTPRequestHandler closes it.
        pass


class _MemorySocket:
    def __init__(self, request_bytes: bytes):
        self._rfile = _NoCloseBytesIO(request_bytes)
        self._wfile = _NoCloseBytesIO()

    def settimeout(self, _timeout):
        pass

    def makefile(self, mode, buffering=None):
        if 'r' in mode:
            return self._rfile
        return self._wfile

    def sendall(self, data):
        self._wfile.write(data)

    def shutdown(self, _how):
        pass

    def close(self):
        pass

    def response_bytes(self):
        return self._wfile.getvalue()


class _DummyServer:
    server_name = 'tec-const.ampecportal.com'
    server_port = 443


def _request_bytes(environ):
    original_method = environ.get('REQUEST_METHOD', 'GET').upper()
    method = 'GET' if original_method == 'HEAD' else original_method
    path = environ.get('PATH_INFO', '/') or '/'
    path = quote(path, safe='/%:@&=+$,;~-_.!()*\'')
    query = environ.get('QUERY_STRING', '')
    target = path + (('?' + query) if query else '')

    headers = []
    host = environ.get('HTTP_HOST') or environ.get('SERVER_NAME') or 'tec-const.ampecportal.com'
    headers.append(('Host', host))

    connection_tokens={v.strip().lower() for v in environ.get('HTTP_CONNECTION','').split(',')}
    for key, value in environ.items():
        if not key.startswith('HTTP_') or key == 'HTTP_HOST':
            continue
        name = key[5:].replace('_', '-').title()
        if is_hop_by_hop(name) or name.lower() in connection_tokens:
            continue
        headers.append((name, str(value)))

    if environ.get('CONTENT_TYPE'):
        headers.append(('Content-Type', environ['CONTENT_TYPE']))

    body = b''
    length = environ.get('CONTENT_LENGTH', '')
    if length:
        try:
            size = max(0, int(length))
        except ValueError:
            size = 0
        if size:
            body = environ['wsgi.input'].read(size)

    headers.append(('Content-Length', str(len(body))))
    headers.append(('Connection', 'close'))

    lines = [f'{method} {target} HTTP/1.1\r\n'.encode('latin-1')]
    for name, value in headers:
        lines.append(f'{name}: {value}\r\n'.encode('latin-1', 'replace'))
    lines.append(b'\r\n')
    lines.append(body)
    return b''.join(lines)


def application(environ, start_response):
    started=time.perf_counter()
    path = environ.get('PATH_INFO', '/') or '/'
    # Public HTML and assets do not need database initialization.
    if path != '/' and not path.startswith('/assets/'):
        _ensure_initialized()

    memory_socket = _MemorySocket(_request_bytes(environ))
    client_ip = environ.get('REMOTE_ADDR', '127.0.0.1')
    conest.ConEstHandler(memory_socket, (client_ip, 0), _DummyServer())

    raw = memory_socket.response_bytes()
    head, sep, body = raw.partition(b'\r\n\r\n')
    if not sep:
        start_response('500 Internal Server Error', [('Content-Type', 'text/plain; charset=utf-8')])
        return [b'Invalid application response']

    lines = head.split(b'\r\n')
    status_line = lines[0].decode('latin-1', 'replace')
    parts = status_line.split(' ', 2)
    status = (parts[1] + ' ' + (parts[2] if len(parts) > 2 else '')).strip()

    parsed_headers = []
    for line in lines[1:]:
        if b':' not in line:
            continue
        name, value = line.split(b':', 1)
        parsed_headers.append((name.decode('latin-1').strip(), value.decode('latin-1').strip()))
    status_code = int(parts[1])
    response_headers, body = prepare_response(environ, status_code, parsed_headers, body)
    response_headers.append(('X-ConEst-Adapter','2.4-r4'))
    response_headers.append(('Server-Timing',f'app;dur={(time.perf_counter()-started)*1000:.1f}'))
    start_response(status, response_headers)
    if environ.get('REQUEST_METHOD', 'GET').upper() == 'HEAD':
        return [b'']
    return [body]


def accepts_gzip(value):
    accepted = {}
    for entry in value.lower().split(','):
        coding, *parameters = entry.strip().split(';')
        quality = 1.0
        for parameter in parameters:
            key, sep, raw = parameter.strip().partition('=')
            if key == 'q' and sep:
                try: quality = float(raw)
                except ValueError: quality = 0.0
        accepted[coding] = quality
    return accepted.get('gzip', accepted.get('*', 0)) > 0


def prepare_response(environ, status, headers, body):
    # Passenger owns HTTP transport. Never forward hop-by-hop headers or a
    # stale body length from the internal HTTP/1.1 adapter to the web server.
    connection_tokens={token.strip().lower() for name,value in headers
                       if name.lower()=='connection' for token in value.split(',')}
    headers=[(name,value) for name,value in headers
             if not is_hop_by_hop(name) and name.lower() not in connection_tokens
             and name.lower() not in {'content-length','status'}]
    metadata={name.lower():value for name,value in headers}
    path=environ.get('PATH_INFO','')
    eligible=(status==200 and environ.get('REQUEST_METHOD','GET').upper() in {'GET','HEAD'}
              and (path.startswith('/api/projects/') or path.startswith('/api/catalog/'))
              and metadata.get('content-type','').startswith('application/json')
              and 'content-encoding' not in metadata and len(body)>=2048)
    if eligible:
        vary={v.strip().lower() for v in metadata.get('vary','').split(',') if v.strip()}
        if '*' not in vary and 'accept-encoding' not in vary:
            headers.append(('Vary','Accept-Encoding'))
        if accepts_gzip(environ.get('HTTP_ACCEPT_ENCODING','')):
            compressed=gzip.compress(body,compresslevel=4,mtime=0)
            if len(compressed)<len(body):
                body=compressed
                headers.append(('Content-Encoding','gzip'))
    if status in (204,304) or 100<=status<200:
        body=b''
    else:
        headers.append(('Content-Length',str(len(body))))
    return headers,body
