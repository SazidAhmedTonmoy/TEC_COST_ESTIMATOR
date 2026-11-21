from __future__ import annotations

import io
import gzip
import json
from wsgiref.util import is_hop_by_hop
import os
import sys
import threading
import time
import sqlite3
import atexit
from contextlib import ExitStack
from http import HTTPStatus
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('CONEST_COOKIE_SECURE', '1')
os.environ.setdefault('CONEST_DB_PATH', str(ROOT / 'data' / 'conest_catalog.db'))

from conest_app import __version__
from conest_app.runtime_health import startup_failure
from conest_app.request_limits import request_gate, body_budget
from conest_app.runtime_metrics import runtime_metrics

_startup_import_error = None
try:
    import app as conest
except Exception as exc:
    # An incomplete production environment can fail before the HTTP handler is
    # imported. Preserve that cause in the log and return a bounded JSON error.
    conest = None
    _startup_import_error = exc

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
        # connect() checks the schema and upgrades only when needed,
        # using the existing cross-process migration lock.
        with conest.connect() as conn:
            conn.execute('SELECT version FROM schema_version LIMIT 1').fetchone()
        conest.IMPORT_DIR.mkdir(parents=True, exist_ok=True)
        conest.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        # Keep the WAL attached between requests, as the standalone server does.
        # This connection holds no transaction and is never used for request work.
        keeper=sqlite3.connect(str(conest.database_path()),check_same_thread=False)
        try:
            keeper.execute('SELECT version FROM schema_version LIMIT 1').fetchone()
        except Exception:
            keeper.close()
            raise
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
    server_name = 'tec-flow.ampecportal.com'
    server_port = 443


class RequestRejected(Exception):
    def __init__(self, status, message, reason='invalid_request'):
        self.status, self.message, self.reason = status, message, reason
        super().__init__(message)


def _body_size(environ):
    # WSGI has already decoded any HTTP transfer framing. Never read an
    # unbounded stream or buffer a body before checking the upload ceiling.
    limit = getattr(conest, 'MAX_UPLOAD_BYTES', 80 * 1024 * 1024)
    length = environ.get('CONTENT_LENGTH', '')
    if length:
        if not str(length).isascii() or not str(length).isdigit():
            raise RequestRejected(400, 'Invalid Content-Length')
        if len(str(length)) > 20:
            raise RequestRejected(400, 'Invalid Content-Length')
        size = int(length)
        if size > limit:
            raise RequestRejected(413, 'Request is too large', 'request_too_large')
        return size
    if environ.get('wsgi.input_terminated'):
        # Safely terminated streams reserve their budget as bounded chunks are
        # read. Many WSGI servers set this flag on empty GET requests too.
        return 0
    if environ.get('HTTP_TRANSFER_ENCODING'):
        raise RequestRejected(411, 'Content-Length is required by this server')
    return 0


def _body_bytes(environ, reservations=None):
    size = _body_size(environ)
    if environ.get('CONTENT_LENGTH', ''):
        body = environ['wsgi.input'].read(size) if size else b''
        if len(body) != size:
            raise RequestRejected(400, 'Incomplete request body')
        return body
    if environ.get('wsgi.input_terminated'):
        limit = getattr(conest, 'MAX_UPLOAD_BYTES', 80 * 1024 * 1024)
        parts, total = [], 0
        while total <= limit:
            read_size = min(64 * 1024, limit + 1 - total)
            if reservations is not None and not reservations.enter_context(body_budget.reserve(read_size)):
                raise RequestRejected(503, 'The server is processing other uploads. Please retry shortly.', 'body_budget_full')
            chunk = environ['wsgi.input'].read(read_size)
            if not chunk:
                return b''.join(parts)
            total += len(chunk)
            if total > limit:
                raise RequestRejected(413, 'Request is too large', 'request_too_large')
            parts.append(chunk)
    return b''


def _request_bytes(environ, reservations=None):
    original_method = environ.get('REQUEST_METHOD', 'GET').upper()
    method = 'GET' if original_method == 'HEAD' else original_method
    path = environ.get('PATH_INFO', '/') or '/'
    path = quote(path, safe='/%:@&=+$,;~-_.!()*\'')
    query = environ.get('QUERY_STRING', '')
    if any(c in original_method + str(query) for c in '\r\n\x00'):
        raise RequestRejected(400, 'Invalid request target')
    target = path + (('?' + query) if query else '')

    headers = []
    host = environ.get('HTTP_HOST') or environ.get('SERVER_NAME') or 'tec-flow.ampecportal.com'
    headers.append(('Host', host))

    connection_tokens={v.strip().lower() for v in environ.get('HTTP_CONNECTION','').split(',')}
    for key, value in environ.items():
        if not key.startswith('HTTP_') or key in ('HTTP_HOST', 'HTTP_CONTENT_LENGTH'):
            continue
        name = key[5:].replace('_', '-').title()
        if is_hop_by_hop(name) or name.lower() in connection_tokens:
            continue
        headers.append((name, str(value)))

    if environ.get('CONTENT_TYPE'):
        headers.append(('Content-Type', environ['CONTENT_TYPE']))

    if any(any(c in str(value) + name for c in '\r\n\x00') for name, value in headers):
        raise RequestRejected(400, 'Invalid request headers')
    body = _body_bytes(environ, reservations)

    headers.append(('Content-Length', str(len(body))))
    headers.append(('Connection', 'close'))

    lines = [f'{method} {target} HTTP/1.1\r\n'.encode('latin-1')]
    for name, value in headers:
        lines.append(f'{name}: {value}\r\n'.encode('latin-1', 'replace'))
    lines.append(b'\r\n')
    lines.append(body)
    return b''.join(lines)


def _simple_response(environ, start_response, status, message, retry=False):
    body = json.dumps({'success': False, 'error': message}, separators=(',', ':')).encode()
    headers = [('Content-Type', 'application/json; charset=utf-8'),
               ('Content-Length', str(len(body))), ('Cache-Control', 'no-store'),
               ('X-Content-Type-Options', 'nosniff'), ('X-ConEst-Adapter', __version__)]
    if retry:
        headers.append(('Retry-After', '2'))
    start_response(f'{status} {HTTPStatus(status).phrase}', headers)
    return [b'' if environ.get('REQUEST_METHOD', 'GET').upper() == 'HEAD' else body]


def application(environ, start_response):
    """Bound application work and record only aggregate operational data."""
    started = time.perf_counter()
    status_code = 500
    rejection = ''

    def capture_status(status, headers, exc_info=None):
        nonlocal status_code
        status_code = int(status.split(' ', 1)[0])
        if status_code == 503 and not any(name.lower() == 'retry-after' for name, _ in headers):
            headers = [*headers, ('Retry-After', '2')]
        if exc_info is None:
            return start_response(status, headers)
        return start_response(status, headers, exc_info)

    with request_gate.enter() as (admitted, reason, queue_ms):
        try:
            if not admitted:
                rejection = reason
                return _simple_response(environ, capture_status, 503,
                    'The server is busy. Please retry shortly.', retry=True)
            try:
                with ExitStack() as reservations:
                    body_admitted = reservations.enter_context(body_budget.reserve(_body_size(environ)))
                    if not body_admitted:
                        rejection = 'body_budget_full'
                        return _simple_response(environ, capture_status, 503,
                            'The server is processing other uploads. Please retry shortly.', retry=True)
                    return _application(environ, capture_status, reservations)
            except RequestRejected as exc:
                rejection = exc.reason
                return _simple_response(environ, capture_status, exc.status, exc.message)
        finally:
            runtime_metrics.observe(environ.get('PATH_INFO', '/'), status_code,
                                    (time.perf_counter() - started) * 1000, queue_ms, rejection)


def _application(environ, start_response, reservations=None):
    started=time.perf_counter()
    path = environ.get('PATH_INFO', '/') or '/'
    # Public HTML and assets do not need database initialization.
    try:
        if _startup_import_error is not None:
            raise _startup_import_error
        memory_socket = _MemorySocket(_request_bytes(environ, reservations))
        if path != '/' and not path.startswith(('/assets/', '/tenders/')):
            _ensure_initialized()
        client_ip = environ.get('REMOTE_ADDR', '127.0.0.1')
        conest.ConEstHandler(memory_socket, (client_ip, 0), _DummyServer())
    except RequestRejected:
        raise
    except Exception as exc:
        body = json.dumps(startup_failure(exc, 'SESSION_STARTUP_FAILED'), separators=(',', ':')).encode('utf-8')
        start_response('503 Service Unavailable', [
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Content-Length', str(len(body))), ('Cache-Control', 'no-store'),
            ('X-Content-Type-Options', 'nosniff'), ('X-ConEst-Adapter', __version__),
            ('Server-Timing', f'app;dur={(time.perf_counter()-started)*1000:.1f}'),
        ])
        return [b'' if environ.get('REQUEST_METHOD', 'GET').upper() == 'HEAD' else body]

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
    response_headers.append(('X-ConEst-Adapter',__version__))
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
    # Compress data and public bundles served through Python. Apache may serve
    # assets directly instead. Authentication/settings responses remain excluded.
    media_type=metadata.get('content-type','').split(';',1)[0].strip().lower()
    data_response=(path.startswith(('/api/projects/', '/api/catalog/', '/api/tenders/'))
                   or path in {'/api/dashboard', '/api/reminders'}) and media_type=='application/json'
    public_asset=path.startswith(('/assets/', '/tenders/assets/')) and media_type in {
        'text/css','text/javascript','application/javascript','image/svg+xml'}
    eligible=(status in (200,201) and (data_response or public_asset)
              and 'content-encoding' not in metadata and 'content-range' not in metadata
              and 'no-transform' not in metadata.get('cache-control','').lower()
              and len(body)>=2048)
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
