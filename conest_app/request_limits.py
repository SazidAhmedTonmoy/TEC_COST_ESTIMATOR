"""Bound work admitted to one Python worker, independently of its web server.

These limits are backpressure, not a replacement for proxy connection timeouts.
No running database transaction is cancelled when an admission wait expires.
"""
from contextlib import contextmanager
from collections import deque
import os
import threading
import time


def _number(name, default, minimum, maximum, converter=int):
    try:
        value = converter(os.environ.get(name, default))
    except (TypeError, ValueError, OverflowError):
        return default
    return value if minimum <= value <= maximum else default


class RequestGate:
    def __init__(self, active=4, queued=64, timeout=5.0):
        self.limit = active
        self.queue_limit = queued
        self.timeout = timeout
        self._lock = threading.Lock()
        self._waiters = deque()
        self._active = self._peak_active = self._peak_waiting = 0
        self._rejected = 0

    @contextmanager
    def enter(self):
        started = time.perf_counter()
        acquired = False
        reason = ''
        ticket = None
        with self._lock:
            if self._active < self.limit and not self._waiters:
                acquired = True
                self._active += 1
                self._peak_active = max(self._peak_active, self._active)
            elif len(self._waiters) >= self.queue_limit:
                reason = 'queue_full'
            else:
                # FIFO admission keeps a busy client's next request from
                # repeatedly taking a slot ahead of users already waiting.
                # Each ticket has one wake-up event: do not wake every queued
                # Python thread whenever a single request finishes.
                ticket = {'ready': threading.Event(), 'admitted': False}
                self._waiters.append(ticket)
                self._peak_waiting = max(self._peak_waiting, len(self._waiters))
        if ticket is not None:
            try:
                ticket['ready'].wait(max(0, self.timeout - (time.perf_counter() - started)))
            except BaseException:
                with self._lock:
                    if ticket['admitted']:
                        self._release_locked()
                    else:
                        self._waiters.remove(ticket)
                raise
            with self._lock:
                acquired = ticket['admitted']
                if not acquired:
                    self._waiters.remove(ticket)
                    reason = 'queue_timeout'
        if not acquired:
            with self._lock:
                self._rejected += 1
        try:
            yield acquired, reason, (time.perf_counter() - started) * 1000
        finally:
            if acquired:
                with self._lock:
                    self._release_locked()

    def _release_locked(self):
        if self._waiters:
            # Transfer the active slot directly; a newly arriving request
            # cannot take it before the oldest waiting request resumes.
            ticket = self._waiters.popleft()
            ticket['admitted'] = True
            ticket['ready'].set()
        else:
            self._active -= 1

    def snapshot(self):
        with self._lock:
            return {
                'active_limit': self.limit, 'queue_limit': self.queue_limit,
                'queue_timeout_seconds': self.timeout,
                'active': self._active, 'waiting': len(self._waiters),
                'peak_active': self._peak_active, 'peak_waiting': self._peak_waiting,
                'rejected': self._rejected,
            }


request_gate = RequestGate(
    _number('CONEST_MAX_ACTIVE_REQUESTS', 4, 1, 128),
    _number('CONEST_MAX_QUEUED_REQUESTS', 64, 0, 1024),
    _number('CONEST_REQUEST_QUEUE_TIMEOUT_SECONDS', 5.0, 0.01, 30.0, float),
)


class BodyBudget:
    """Bound declared input bytes buffered simultaneously by the WSGI adapter."""
    def __init__(self, limit=128 * 1024 * 1024):
        self.limit = limit
        self._lock = threading.Lock()
        self._used = self._peak = self._rejected = 0

    @contextmanager
    def reserve(self, size):
        with self._lock:
            admitted = self._used + size <= self.limit
            if admitted:
                self._used += size
                self._peak = max(self._peak, self._used)
            else:
                self._rejected += 1
        try:
            yield admitted
        finally:
            if admitted:
                with self._lock:
                    self._used -= size

    def snapshot(self):
        with self._lock:
            return {'limit_bytes': self.limit, 'reserved_bytes': self._used,
                    'peak_reserved_bytes': self._peak, 'rejected': self._rejected}


body_budget = BodyBudget(_number('CONEST_MAX_BUFFERED_BODY_MIB', 128, 80, 512) * 1024 * 1024)
