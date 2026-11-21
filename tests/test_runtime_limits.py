"""Admission, privacy and actual WSGI authorization without a network listener."""
from concurrent.futures import ThreadPoolExecutor
import base64
import io
import json
import os
from pathlib import Path
import tempfile
import secrets
import threading
import time
import unittest
from unittest.mock import patch

from conest_app import wsgi_runtime as wsgi
from conest_app.request_limits import BodyBudget, RequestGate
from conest_app.runtime_metrics import RuntimeMetrics, route_group


def request(path='/', method='GET', body=b'', token='', **extra):
    environ = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'QUERY_STRING': '',
               'CONTENT_LENGTH': str(len(body)), 'CONTENT_TYPE': 'application/json',
               'wsgi.input': io.BytesIO(body), 'SERVER_NAME': 'localhost',
               'HTTP_HOST': 'localhost', 'REMOTE_ADDR': '127.0.0.1'}
    if token:
        environ['HTTP_COOKIE'] = 'conest_session=' + token
    environ.update(extra)
    result = {}
    def start(status, headers):
        result.update(status=int(status.split(' ', 1)[0]), headers=dict(headers))
    result['body'] = b''.join(wsgi.application(environ, start))
    return result


class RuntimeLimitTests(unittest.TestCase):
    def test_waiting_users_are_admitted_in_order(self):
        from types import SimpleNamespace
        from conest_app import request_limits

        gate = RequestGate(active=1, queued=2, timeout=1)
        order = []

        class ControlledEvent:
            def __init__(self):
                self.waiting = threading.Event()
                self.released = threading.Event()

            def wait(self, _timeout=None):
                self.waiting.set()
                # Test ordering independently of wall-clock scheduling. This
                # bound detects a deadlock; it does not expire the gate ticket.
                if not self.released.wait(10):
                    raise AssertionError('The queued request was not released')
                return True

            def set(self):
                self.released.set()

        first_waiter, second_waiter = ControlledEvent(), ControlledEvent()
        waiters = iter((first_waiter, second_waiter))
        gate_threading = SimpleNamespace(Lock=threading.Lock, Event=lambda: next(waiters))

        def work(number):
            with gate.enter() as admitted:
                self.assertTrue(admitted[0])
                order.append(number)

        # Replace only the gate's Event factory, not threading.Event globally:
        # ThreadPoolExecutor still uses ordinary thread synchronization.
        with patch.object(request_limits, 'threading', gate_threading):
            with ThreadPoolExecutor(max_workers=2) as pool:
                try:
                    with gate.enter() as held:
                        self.assertTrue(held[0])
                        first = pool.submit(work, 1)
                        self.assertTrue(first_waiter.waiting.wait(10))
                        self.assertEqual(gate.snapshot()['waiting'], 1)
                        second = pool.submit(work, 2)
                        self.assertTrue(second_waiter.waiting.wait(10))
                        self.assertEqual(gate.snapshot()['waiting'], 2)
                    first.result(timeout=10)
                    second.result(timeout=10)
                finally:
                    first_waiter.set()
                    second_waiter.set()
        self.assertEqual(order, [1, 2])
        state = gate.snapshot()
        self.assertEqual((state['active'], state['waiting']), (0, 0))
        self.assertEqual((state['peak_active'], state['peak_waiting']), (1, 2))

    def test_admission_bounds_waiters_times_out_and_releases_after_failure(self):
        from types import SimpleNamespace
        from conest_app import request_limits

        gate = RequestGate(active=1, queued=1, timeout=.05)
        entered = threading.Event()
        expire = threading.Event()

        class ControlledTimeout:
            def wait(self, _timeout=None):
                # Signal only after RequestGate has actually queued the ticket.
                entered.set()
                if not expire.wait(10):
                    raise AssertionError('The test did not trigger the timeout')
                return False

            def set(self):
                expire.set()

        gate_threading = SimpleNamespace(Lock=threading.Lock, Event=ControlledTimeout)

        def waiting():
            with gate.enter() as result:
                return result

        with patch.object(request_limits, 'threading', gate_threading):
            with gate.enter() as first:
                self.assertTrue(first[0])
                with ThreadPoolExecutor(max_workers=1) as pool:
                    try:
                        pending = pool.submit(waiting)
                        self.assertTrue(entered.wait(10))
                        self.assertEqual(gate.snapshot()['waiting'], 1)
                        with gate.enter() as extra:
                            self.assertEqual(extra[:2], (False, 'queue_full'))
                        # Expire the waiting ticket only after queue-full has
                        # been checked, so runner preemption cannot change it.
                        expire.set()
                        self.assertEqual(pending.result(timeout=10)[:2], (False, 'queue_timeout'))
                        self.assertEqual(gate.snapshot()['waiting'], 0)
                    finally:
                        expire.set()
        with self.assertRaises(RuntimeError):
            with gate.enter():
                raise RuntimeError('simulated handler failure')
        with gate.enter() as next_request:
            self.assertTrue(next_request[0])
        state = gate.snapshot()
        self.assertEqual((state['active'], state['waiting']), (0, 0))
        self.assertEqual((state['peak_active'], state['peak_waiting']), (1, 1))

    def test_body_budget_rejects_before_read_and_releases(self):
        budget = BodyBudget(20)
        with budget.reserve(15) as first:
            self.assertTrue(first)
            with budget.reserve(6) as second:
                self.assertFalse(second)
        with self.assertRaises(ValueError):
            with budget.reserve(20):
                raise ValueError('simulated failure')
        self.assertEqual(budget.snapshot()['reserved_bytes'], 0)
        stream = io.BytesIO(b'{}')
        with patch.object(wsgi, 'body_budget', BodyBudget(1)):
            response = request(method='POST', body=b'{}', **{'wsgi.input': stream})
        self.assertEqual(response['status'], 503)
        self.assertEqual(stream.tell(), 0)
        self.assertEqual(response['headers']['Retry-After'], '2')

    def test_wsgi_rejects_size_invalid_lengths_and_header_injection_before_read(self):
        for length, status in [('999999999', 413), ('-1', 400), ('invalid', 400), ('1' * 10000, 400)]:
            stream = io.BytesIO(b'private')
            result = request(method='POST', CONTENT_LENGTH=length, **{'wsgi.input': stream})
            self.assertEqual(result['status'], status)
            self.assertEqual(stream.tell(), 0)
        result = request(HTTP_HOST='localhost\r\nInjected: value')
        self.assertEqual(result['status'], 400)
        self.assertEqual(request(method='POST', body=b'{}', CONTENT_LENGTH='3')['status'], 400)

    def test_decoded_terminated_stream_is_bounded_and_unsupported_framing_rejected(self):
        with patch.object(wsgi.conest, 'MAX_UPLOAD_BYTES', 3):
            body = wsgi._body_bytes({'CONTENT_LENGTH': '', 'wsgi.input_terminated': True,
                                    'wsgi.input': io.BytesIO(b'{}')})
            self.assertEqual(body, b'{}')
            with self.assertRaises(wsgi.RequestRejected) as error:
                wsgi._body_bytes({'CONTENT_LENGTH': '', 'wsgi.input_terminated': True,
                                  'wsgi.input': io.BytesIO(b'1234')})
            self.assertEqual(error.exception.status, 413)
        result = request(method='POST', CONTENT_LENGTH='', HTTP_TRANSFER_ENCODING='chunked')
        self.assertEqual(result['status'], 411)

    def test_wsgi_overload_is_bounded_retryable_and_does_not_start_work(self):
        gate = RequestGate(active=1, queued=0, timeout=.01)
        with patch.object(wsgi, 'request_gate', gate), patch.object(wsgi, '_application') as dispatch:
            with gate.enter():
                result = request('/api/tenders/data')
        self.assertEqual(result['status'], 503)
        self.assertEqual(result['headers']['Retry-After'], '2')
        dispatch.assert_not_called()

    def test_metrics_are_bounded_and_contain_no_paths_query_or_arbitrary_labels(self):
        metrics = RuntimeMetrics(sample_limit=3)
        for n in range(6):
            metrics.observe('/api/projects/12345?token=secret', 200, n,
                            rejection='private person or error content')
        metrics.observe('/share/project/private-token', 503, 10, rejection='queue_full')
        value = metrics.snapshot()
        text = json.dumps(value)
        for private in ('12345', 'secret', 'private', 'token=', 'person'):
            self.assertNotIn(private, text)
        self.assertEqual(value['completed_requests'], 7)
        self.assertEqual(value['latency_ms']['recent_sample_count'], 3)
        self.assertEqual(value['rejections'], {'queue_full': 1})
        self.assertEqual(route_group('/api/projects-secret'), 'other')

    def test_metrics_endpoint_rechecks_administrator_role(self):
        from conest_app import accounts
        from conest_app.database import connect
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'CONEST_DB_PATH': str(Path(directory) / 'accounts.db'),
                                         'CONEST_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
                                         'CONEST_ENCRYPTION_KEY_FILE': ''}), \
                 patch.object(wsgi, '_ensure_initialized'), \
                 patch.object(wsgi.conest.ConEstHandler, 'log_message'):
                with connect() as db:
                    row = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
                    identifier = row['id']
                    db.execute('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?',
                               (accounts.password_hash(secrets.token_urlsafe(24)), identifier))
                    token = accounts.start_session(db, identifier)
                self.assertEqual(request('/api/admin/runtime-metrics')['status'], 401)
                good = request('/api/admin/runtime-metrics', token=token)
                self.assertEqual(good['status'], 200)
                self.assertEqual(good['headers']['Cache-Control'], 'no-store')
                self.assertIn('this Python worker', json.loads(good['body'])['runtime']['scope'])
                with connect() as db:
                    db.execute("UPDATE users SET role='user' WHERE id=?", (identifier,))
                self.assertEqual(request('/api/admin/runtime-metrics', token=token)['status'], 403)

    def test_monitor_checker_reports_latency_error_rate_and_queue_pressure(self):
        from tools.check_runtime_metrics import check
        metrics = RuntimeMetrics()
        for _ in range(20):
            metrics.observe('/api/tenders/data', 200, 20)
        payload = {'success': True, 'runtime': metrics.snapshot(),
                   'admission': {'active': 1, 'active_limit': 2, 'waiting': 0, 'queue_limit': 5}}
        self.assertTrue(check(payload)['healthy'])
        metrics.observe('/api/tenders/data', 503, 3000)
        metrics.observe('/api/tenders/data', 503, 3000)
        payload['runtime'] = metrics.snapshot()
        payload['admission']['waiting'] = 4
        self.assertEqual(set(check(payload)['alerts']), {
            'server_error_rate_since_worker_start', 'recent_p95_latency', 'request_queue_nearly_full'})

    def test_standalone_server_rejects_over_capacity_without_spawning_a_thread(self):
        from unittest.mock import Mock
        server = object.__new__(wsgi.conest.ConEstServer)
        server._connection_slots = threading.BoundedSemaphore(1)
        server.shutdown_request = Mock()
        stream = Mock()
        server._connection_slots.acquire()
        with patch('http.server.ThreadingHTTPServer.process_request') as spawn:
            server.process_request(stream, ('127.0.0.1', 1))
        spawn.assert_not_called()
        self.assertIn(b'503 Service Unavailable', stream.sendall.call_args.args[0])
        self.assertIn(b'Retry-After: 2', stream.sendall.call_args.args[0])
        server.shutdown_request.assert_called_once_with(stream)
        server._connection_slots.release()


if __name__ == '__main__':
    unittest.main()
