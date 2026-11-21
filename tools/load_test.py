"""Offline, authenticated WSGI load check on disposable database copies.

No URL or live-host mode exists. Credentials are generated in memory. Reports
contain timings, counts and integrity results, never application records.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta, timezone, datetime
import gzip
import hashlib
import io
import json
import math
import os
import re
from pathlib import Path
import secrets
import shutil
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def percentile(values, fraction):
    return round(sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)], 2) if values else 0.0


class Client:
    def __init__(self, application, token):
        self.application = application
        self.token = token
        self.csrf = hashlib.sha256(('conest-csrf:' + token).encode()).hexdigest()

    def request(self, method, path, payload=None):
        target = urlsplit(path)
        body = json.dumps(payload).encode() if payload is not None else b''
        env = {
            'REQUEST_METHOD': method, 'PATH_INFO': target.path, 'QUERY_STRING': target.query,
            'CONTENT_LENGTH': str(len(body)), 'CONTENT_TYPE': 'application/json',
            'wsgi.input': io.BytesIO(body), 'wsgi.url_scheme': 'https',
            'HTTP_HOST': 'offline.test', 'SERVER_NAME': 'offline.test',
            'REMOTE_ADDR': '127.0.0.1', 'HTTP_COOKIE': 'conest_session=' + self.token,
            'HTTP_ACCEPT_ENCODING': 'gzip',
        }
        if method not in ('GET', 'HEAD'):
            env.update(HTTP_X_CONEST_REQUEST='1', HTTP_X_CSRF_TOKEN=self.csrf)
        response = {}
        def start(status, headers):
            response['status'] = int(status.split(' ', 1)[0])
            response['headers'] = {key.lower(): value for key, value in headers}
        started = time.perf_counter()
        raw = b''.join(self.application(env, start))
        elapsed = (time.perf_counter() - started) * 1000
        service = re.search(r'(?:^|,)\s*app;dur=([0-9.]+)', response.get('headers', {}).get('server-timing', ''))
        self.last_service_ms = float(service[1]) if service else elapsed
        if response.get('headers', {}).get('content-encoding') == 'gzip':
            raw = gzip.decompress(raw)
        try:
            parsed = json.loads(raw)
        except (ValueError, UnicodeError):
            parsed = {}
        return response.get('status', 0), parsed, elapsed


def fixture_copy(source, destination):
    # A supplied backup should be closed. Reject an active main-file snapshot
    # instead of silently omitting committed data still in its WAL.
    for suffix in ('-wal', '-journal'):
        sidecar = Path(str(source) + suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise ValueError('Use a completed SQLite backup, not an active database file.')
    shutil.copy2(source, destination)


def prepare_users(db_connect, accounts, count):
    password = secrets.token_urlsafe(24)
    password_hash = accounts.password_hash(password)
    prefix = 'load_' + secrets.token_hex(5)
    users = []
    now = datetime.now(timezone.utc).isoformat()
    with db_connect() as db:
        for index in range(count + 1):
            role = 'admin' if index == count else 'user'
            cursor = db.execute('''INSERT INTO users
                (username,name,password_hash,role,must_change_password,created_at,updated_at)
                VALUES (?,?,?,?,0,?,?)''',
                (f'{prefix}_{index}', f'Offline test user {index}', password_hash, role, now, now))
            users.append({'id': cursor.lastrowid, 'token': accounts.start_session(db, cursor.lastrowid)})
    # Test sessions are issued by the normal account code. Password verification
    # and the production login rate limiter are deliberately outside this load.
    return users[:-1], users[-1]


def prepare_records(client, label, catalog_item_id):
    status, data, _ = client.request('POST', '/api/projects', {'name': label})
    if status != 201 or 'project' not in data:
        raise RuntimeError(f'Synthetic estimator setup failed with HTTP {status}.')
    project = data['project']
    status, data, _ = client.request('POST', f"/api/projects/{project['id']}/lines",
                                     {'catalog_item_id': catalog_item_id, 'quantity': 1})
    if status != 201 or not data.get('lines'):
        raise RuntimeError(f'Synthetic estimate-line setup failed with HTTP {status}.')
    project, line = data['project'], data['lines'][0]
    status, data, _ = client.request('POST', '/api/tenders/opportunities/save', {
        'project': label, 'region': 'NSW', 'due': (date.today() + timedelta(days=365)).isoformat(),
        'builders': ['Offline load fixture builder'],
    })
    if status != 200 or 'opportunity' not in data:
        raise RuntimeError(f'Synthetic opportunity setup failed with HTTP {status}.')
    return project, line, data['opportunity']


def run_level(count, iterations, application, users, db_connect, store, latency_gate):
    label = 'Offline concurrency ' + secrets.token_hex(8)
    with db_connect() as db:
        selected = db.execute('''SELECT ci.id FROM catalog_items ci JOIN catalog_components cc ON cc.catalog_item_id=ci.id
            WHERE ci.is_active=1 AND ci.data_status!='reference_only' GROUP BY ci.id
            HAVING COUNT(cc.id) BETWEEN 1 AND 20 ORDER BY ABS(COUNT(cc.id)-3),ci.id LIMIT 1''').fetchone()
        if not selected:
            raise RuntimeError('Load fixture needs one usable catalog item with components.')
        catalog_item_id = selected['id']
    state = []
    for index, user in enumerate(users[:count]):
        client = Client(application, user['token'])
        project, line, opportunity = prepare_records(client, f'{label} {index}', catalog_item_id)
        state.append((client, project, line, opportunity))
    # Setup adds catalogue usage records. Warm the resulting committed version
    # before the timed concurrent stage, not an obsolete pre-setup cache entry.
    for path in ('/api/tenders/data', '/api/tenders/opportunities?pageSize=18', '/api/catalog/search?q=cable&limit=25'):
        if state[0][0].request('GET', path)[0] != 200:
            raise RuntimeError('Stage warm-up failed.')
    barrier = threading.Barrier(count)
    def journey(index):
        client, project, line, opportunity = state[index]
        samples, statuses, writes = [], Counter(), 0
        operations = Counter()
        operation_samples = {}
        service_samples = {}
        verification_failures = 0
        barrier.wait(timeout=60)
        for iteration in range(iterations):
            # Six reads and two writes per round across both application DBs.
            requests = [
                ('GET', '/api/tenders/data', None, 'tender_data'),
                ('GET', '/api/tenders/opportunities?pageSize=18', None, 'opportunity_list'),
                ('GET', '/api/catalog/search?q=cable&limit=25', None, 'catalog_search'),
                ('GET', '/api/tenders/opportunities/deadline-load?due=' + opportunity['due'], None, 'deadline_load'),
                ('POST', '/api/tenders/opportunities/save',
                 {'id': opportunity['id'], 'revision': opportunity['revision'],
                  'remarks': f'Load check round {iteration}'}, 'opportunity_write'),
                ('PATCH', f"/api/projects/{project['id']}/lines/{line['id']}",
                 {'quantity': iteration + 2, 'expected_revision': line['revision']}, 'estimator_write'),
                ('GET', f"/api/projects/{project['id']}", None, 'estimator_read'),
                ('GET', '/api/tenders/notifications?limit=25', None, 'notifications'),
            ]
            for method, path, payload, operation in requests:
                try:
                    status, data, elapsed = client.request(method, path, payload)
                    samples.append(elapsed)
                    operation_samples.setdefault(operation, []).append(elapsed)
                    service_samples.setdefault(operation, []).append(client.last_service_ms)
                    statuses[status] += 1
                    operations[operation] += 1
                    if status == 200:
                        if operation == 'opportunity_write':
                            updated = data.get('opportunity', {})
                            if updated.get('remarks') == payload['remarks'] and updated.get('revision') == opportunity['revision'] + 1:
                                opportunity = updated
                                writes += 1
                            else:
                                verification_failures += 1
                        elif operation == 'estimator_write':
                            updated = next((item for item in data.get('lines', []) if item.get('id') == line['id']), {})
                            if updated.get('quantity') == payload['quantity'] and updated.get('revision') == line['revision'] + 1:
                                line, project = updated, data['project']
                                writes += 1
                            else:
                                verification_failures += 1
                        elif operation == 'estimator_read':
                            saved_line = next((item for item in data.get('lines', []) if item.get('id') == line['id']), {})
                            if saved_line.get('quantity') != iteration + 2:
                                verification_failures += 1
                except Exception:
                    # Never include exception values/response bodies in reports.
                    statuses[0] += 1
        return samples, statuses, writes, verification_failures, operations, operation_samples, service_samples, project, line, opportunity

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=count) as pool:
        results = list(pool.map(journey, range(count)))
    elapsed = time.perf_counter() - started
    samples, statuses, operations = [], Counter(), Counter()
    operation_samples = {}
    service_samples = {}
    writes = verification_failures = 0
    for measured, codes, committed, failures, actions, per_operation, service, project, line, opportunity in results:
        samples.extend(measured)
        statuses.update(codes)
        operations.update(actions)
        for operation, timings in per_operation.items():
            operation_samples.setdefault(operation, []).extend(timings)
        for operation, timings in service.items():
            service_samples.setdefault(operation, []).extend(timings)
        writes += committed
        verification_failures += failures
        with db_connect() as db:
            saved = db.execute('SELECT quantity,revision FROM project_lines WHERE id=? AND project_id=?',
                               (line['id'], project['id'])).fetchone()
            if not saved or saved['quantity'] != iterations + 1 or saved['revision'] != line['revision']:
                verification_failures += 1
        with store.connect() as db:
            saved = db.execute('SELECT body FROM opportunities WHERE id=?', (opportunity['id'],)).fetchone()
            saved = json.loads(saved['body']) if saved else {}
            if saved.get('remarks') != f'Load check round {iterations - 1}' or saved.get('revision') != opportunity['revision']:
                verification_failures += 1
    expected_requests = count * iterations * 8
    expected_writes = count * iterations * 2
    unexpected = sum(number for code, number in statuses.items() if code != 200)
    passed = (unexpected == 0 and len(samples) == expected_requests and writes == expected_writes
              and verification_failures == 0 and percentile(samples, .95) <= latency_gate)
    return {
        'concurrent_simulated_users': count, 'iterations_per_user': iterations,
        'requests': expected_requests, 'completed_requests': sum(statuses.values()),
        'duration_seconds': round(elapsed, 3), 'requests_per_second': round(expected_requests / elapsed, 2),
        'latency_ms': {'p50': percentile(samples, .50), 'p95': percentile(samples, .95),
                       'p99': percentile(samples, .99), 'maximum': round(max(samples, default=0), 2),
                       'mean': round(statistics.mean(samples), 2) if samples else 0},
        'http_status_counts': dict(sorted(statuses.items())), 'unexpected_responses': unexpected,
        'expected_successful_writes': expected_writes, 'verified_successful_writes': writes,
        'write_verification_failures': verification_failures, 'operations': dict(operations),
        'operation_latency_ms': {operation: {'mean': round(statistics.mean(values), 2),
                                  'p95': percentile(values, .95), 'p99': percentile(values, .99),
                                  'service_mean': round(statistics.mean(service_samples[operation]), 2),
                                  'service_p95': percentile(service_samples[operation], .95)}
                                 for operation, values in operation_samples.items()},
        'p95_gate_ms': latency_gate, 'passed': passed,
    }


def run(args):
    original_hashes = {key: digest(path) for key, path in (
        ('catalog', args.catalog_db), ('tenders', args.tenders_db))}
    with tempfile.TemporaryDirectory(prefix='tec-flow-load-') as temporary:
        directory = Path(temporary)
        catalog = directory / 'catalog.db'
        tender_path = directory / 'tenders.db'
        fixture_copy(args.catalog_db, catalog)
        fixture_copy(args.tenders_db, tender_path)
        os.environ['CONEST_DB_PATH'] = str(catalog)
        os.environ['CONEST_TENDERS_DB_PATH'] = str(tender_path)
        if getattr(args, 'use_configured_key', False):
            if not (os.environ.get('CONEST_ENCRYPTION_KEY') or os.environ.get('CONEST_ENCRYPTION_KEY_FILE')):
                raise ValueError('Already protected databases require their original configured key.')
        else:
            os.environ['CONEST_ENCRYPTION_KEY'] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
            os.environ.pop('CONEST_ENCRYPTION_KEY_FILE', None)
        sys.path.insert(0, str(ROOT))
        # Suppress ordinary access logs and failure detail; report safe aggregate
        # outcomes only. Temp records and randomly generated keys are discarded.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            from conest_app import wsgi_runtime as wsgi
            from conest_app import accounts, tenders
            from conest_app.database import connect
            from conest_app.runtime_metrics import runtime_snapshot
            from conest_app.request_limits import request_gate
            wsgi.conest.IMPORT_DIR = directory / 'imports'
            wsgi.conest.EXPORT_DIR = directory / 'exports'
            wsgi._ensure_initialized()
            store = tenders.get_store()
            store.all_data()
            with connect() as db:
                catalog_projects = db.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
                catalog_items = db.execute('SELECT COUNT(*) FROM catalog_items').fetchone()[0]
                project_lines = db.execute('SELECT COUNT(*) FROM project_lines').fetchone()[0]
            with store.connect() as db:
                tender_counts = {table: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                                 for table in ('submissions', 'chases', 'opportunities')}
            users, admin = prepare_users(connect, accounts, max(args.users))
            monitor = Client(wsgi.application, admin['token'])
            warmup = Client(wsgi.application, users[0]['token'])
            for path in ('/api/tenders/data', '/api/catalog/search?q=cable&limit=25',
                         '/api/tenders/opportunities?pageSize=18'):
                if warmup.request('GET', path)[0] != 200:
                    raise RuntimeError('Warm-up failed; inspect the isolated test environment.')
            levels = [run_level(count, args.iterations, wsgi.application, users, connect, store, args.p95_ms)
                      for count in args.users]
            monitor_status, monitor_payload, _ = monitor.request('GET', '/api/admin/runtime-metrics')
            normal_status, _, _ = warmup.request('GET', '/api/admin/runtime-metrics')
            integrity = {}
            with connect() as db:
                integrity['catalog'] = db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                integrity['catalog_foreign_keys'] = len(db.execute('PRAGMA foreign_key_check').fetchall()) == 0
            with store.connect() as db:
                integrity['tenders'] = db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                integrity['tenders_foreign_keys'] = len(db.execute('PRAGMA foreign_key_check').fetchall()) == 0
            metrics = runtime_snapshot()
            from tools.check_runtime_metrics import check as check_runtime_metrics
            monitor_thresholds = check_runtime_metrics(metrics, max_p95_ms=args.p95_ms)
            monitor_ok = monitor_status == 200 and normal_status == 403 and 'runtime' in monitor_payload
            bounded = (metrics['admission']['peak_active'] <= request_gate.limit
                       and metrics['admission']['peak_waiting'] <= request_gate.queue_limit
                       and metrics['admission']['active'] == metrics['admission']['waiting'] == 0)
            tenders.close_store()
            if wsgi._database_keeper is not None:
                wsgi._database_keeper.close()
                wsgi._database_keeper = None
        originals_unchanged = all(digest(path) == original_hashes[key] for key, path in (
            ('catalog', args.catalog_db), ('tenders', args.tenders_db)))
        return {
            'scope': 'Offline, in-process WSGI requests; one Python worker; copied supplied databases; synthetic authenticated sessions.',
            'exclusions': ['network/TLS latency', 'reverse proxy and Passenger limits', 'browser rendering',
                           'password hashing/sign-in load', 'large uploads and external AI calls',
                           'large-estimate recalculations and catalog/import mutations',
                           'multi-process or multi-host capacity', 'cold startup and schema migration time'],
            'python': sys.version.split()[0], 'sqlite': sqlite3.sqlite_version,
            'fixture_counts_before_test_records': {'catalog_projects': catalog_projects,
                                                  'catalog_items': catalog_items, 'project_lines': project_lines, **tender_counts},
            'levels': levels, 'integrity': integrity, 'original_files_unchanged': originals_unchanged,
            'monitor_access_verified': monitor_ok, 'admission_bounds_verified': bounded,
            'monitor_threshold_check': monitor_thresholds,
            'runtime_metrics': metrics,
            'passed': all(level['passed'] for level in levels) and all(integrity.values())
                      and originals_unchanged and monitor_ok and monitor_thresholds['healthy'] and bounded,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog-db', type=Path, required=True, help='Closed backup of accounts/Estimator database; copied before use')
    parser.add_argument('--tenders-db', type=Path, required=True, help='Closed Tender database backup; copied before use')
    parser.add_argument('--users', default='10,25,50', help='Comma-separated concurrent simulated users (1..100)')
    parser.add_argument('--iterations', type=int, default=10, help='Eight requests per user per iteration')
    parser.add_argument('--p95-ms', type=float, default=2000, help='Predeclared p95 latency acceptance threshold')
    parser.add_argument('--output', type=Path, required=True, help='Aggregate JSON report destination')
    parser.add_argument('--use-configured-key', action='store_true',
                        help='For already protected database copies: use the matching encryption key configured in the environment')
    args = parser.parse_args()
    try:
        args.users = [int(value) for value in args.users.split(',')]
        if not args.users or any(value < 1 or value > 100 for value in args.users):
            raise ValueError('Choose 1 to 100 concurrent users.')
        if not 1 <= args.iterations <= 100 or not 0 < args.p95_ms <= 60000:
            raise ValueError('Use 1 to 100 iterations and a positive p95 threshold up to 60000 ms.')
        args.catalog_db = args.catalog_db.resolve(strict=True)
        args.tenders_db = args.tenders_db.resolve(strict=True)
        if args.output.resolve() in (args.catalog_db, args.tenders_db):
            raise ValueError('Report output must not overwrite an input database.')
        result = run(args)
    except Exception as exc:
        # Exception class only: a failed SQL assertion must not dump user data.
        result = {'passed': False, 'error_type': type(exc).__name__,
                  'error': 'Offline load test could not finish. Check backup compatibility and test prerequisites.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('passed', 'levels', 'error') if key in result}, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
