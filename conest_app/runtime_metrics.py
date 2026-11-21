"""Bounded, process-local operational metrics with no request or user contents."""
from collections import Counter, deque
import math
import os
import threading
import time


def route_group(path):
    """A fixed vocabulary prevents IDs, share tokens or queries becoming labels."""
    path = str(path).split('?', 1)[0]
    for prefix in ('/api/admin', '/api/health', '/api/auth',
                   '/api/tenders/opportunities', '/api/tenders', '/api/projects',
                   '/api/catalog', '/api/dashboard', '/api/settings', '/assets'):
        if path == prefix or path.startswith(prefix + '/'):
            return prefix
    if path in ('/', '/tenders', '/tenders/'):
        return 'page'
    return 'other'


def _percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)], 2)


class RuntimeMetrics:
    def __init__(self, sample_limit=2048):
        self._lock = threading.Lock()
        self._started = time.monotonic()
        self._sample_limit = sample_limit
        self._latency = deque(maxlen=sample_limit)
        self._queue = deque(maxlen=sample_limit)
        self._status = Counter()
        self._routes = Counter()
        self._reasons = Counter()
        self._completed = 0
        self._duration = 0.0

    def observe(self, path, status, elapsed_ms, queue_ms=0.0, rejection=''):
        # Only callers' fixed reason constants are accepted, never error text.
        allowed_reasons = {'queue_full', 'queue_timeout', 'connections_full',
                           'body_budget_full', 'request_too_large', 'invalid_request'}
        with self._lock:
            self._completed += 1
            self._duration += elapsed_ms
            self._latency.append(max(0.0, elapsed_ms))
            self._queue.append(max(0.0, queue_ms))
            self._status[f'{max(1, min(5, int(status) // 100))}xx'] += 1
            self._routes[route_group(path)] += 1
            if rejection in allowed_reasons:
                self._reasons[rejection] += 1

    def snapshot(self):
        with self._lock:
            elapsed = max(0.001, time.monotonic() - self._started)
            return {
                'scope': 'this Python worker; counters reset when it restarts',
                'worker_pid': os.getpid(),
                'uptime_seconds': round(elapsed, 1),
                'completed_requests': self._completed,
                'requests_per_second_since_start': round(self._completed / elapsed, 3),
                'status_classes': dict(self._status),
                'route_groups': dict(self._routes),
                'rejections': dict(self._reasons),
                'latency_ms': {
                    'mean_since_start': round(self._duration / self._completed, 2) if self._completed else 0.0,
                    'recent_sample_count': len(self._latency),
                    'sample_limit': self._sample_limit,
                    'p50_recent': _percentile(self._latency, .50),
                    'p95_recent': _percentile(self._latency, .95),
                    'p99_recent': _percentile(self._latency, .99),
                    'max_recent': round(max(self._latency, default=0.0), 2),
                    'queue_p95_recent': _percentile(self._queue, .95),
                },
            }


runtime_metrics = RuntimeMetrics()


def runtime_snapshot():
    from .request_limits import request_gate, body_budget
    from . import __version__
    return {'success': True, 'release': __version__,
            'runtime': runtime_metrics.snapshot(), 'admission': request_gate.snapshot(),
            'buffered_input': body_budget.snapshot()}
