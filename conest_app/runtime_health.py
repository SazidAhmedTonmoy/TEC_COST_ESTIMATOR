"""Hosted-startup diagnostics without exposing server paths or exception text."""
from __future__ import annotations

import logging
import sqlite3
import sys
import uuid
from contextlib import closing
from zoneinfo import ZoneInfo


log = logging.getLogger(__name__)


def startup_failure(exc, code):
    """Give the browser a safe reference and retain the original cause privately."""
    reference = uuid.uuid4().hex[:12]
    messages = {
        'SESSION_STARTUP_FAILED': 'The server could not start the application.',
        'TENDERS_STARTUP_FAILED': 'Tenders could not open its data on the server.',
    }
    diagnostics_available = False
    try:
        from .startup_diagnostics import record_failure
        diagnostics_available = bool(record_failure(exc, code, reference))
    except Exception:
        pass  # Diagnostics must never replace the original startup response.
    try:
        log.error('TEC ConEst startup error %s; reference: %s', code, reference,
                  exc_info=(type(exc), exc, exc.__traceback__))
    except Exception:
        pass  # Some hosting/custom logging handlers can themselves raise.
    return {
        'success': False,
        'error': messages.get(code, 'The server could not finish starting.') +
                 f' Error reference: {reference}. Ask your administrator to check the hosting setup and server log.',
        'error_code': code,
        'error_reference': reference,
        'diagnostics_available': diagnostics_available,
    }


def check_sqlite_runtime():
    """Check features in the actual Python-linked SQLite, not a shell sqlite CLI."""
    if sys.version_info < (3, 10):
        raise RuntimeError('TEC ConEst requires Python 3.10 or newer.')
    if sqlite3.sqlite_version_info < (3, 24, 0):
        raise RuntimeError('The production Python needs SQLite 3.24 or newer for UPSERT support.')
    with closing(sqlite3.connect(':memory:')) as db:
        try:
            ready = db.execute("SELECT json_extract('{\"ready\":true}', '$.ready')").fetchone()[0]
        except sqlite3.OperationalError as exc:
            raise RuntimeError('The production Python SQLite library needs JSON support.') from exc
        if ready != 1:
            raise RuntimeError('The production Python SQLite JSON support is not working.')
        db.execute('CREATE TABLE runtime_probe(id INTEGER PRIMARY KEY, value INTEGER)')
        db.execute('INSERT INTO runtime_probe VALUES(1,0)')
        db.execute('INSERT INTO runtime_probe VALUES(1,1) ON CONFLICT(id) DO UPDATE SET value=excluded.value')
        if db.execute('SELECT value FROM runtime_probe WHERE id=1').fetchone()[0] != 1:
            raise RuntimeError('The production Python SQLite UPSERT support is not working.')


def check_timezones(names=('Australia/Sydney', 'Australia/Melbourne')):
    for name in set(names):
        try:
            ZoneInfo(name)
        except (KeyError, ValueError) as exc:
            raise RuntimeError('Timezone data is unavailable. Install requirements.txt in the production Python environment.') from exc


def tender_readiness():
    """Exercise the same store and directory path as authenticated Tender startup.

    This explicit deployment check returns status labels only. The write probe
    is rolled back and changes no row; it checks the runtime database directory
    and SQLite write access instead of assuming catalog health covers Tenders.
    """
    from . import tenders

    check_sqlite_runtime()
    check_timezones()
    store = tenders.get_store()
    tenders.live_teams(store.all_data())
    with store.connect() as db:
        zones = [r[0] for r in db.execute('SELECT DISTINCT timezone FROM opportunity_regions')]
        db.execute('SELECT id,status,region,due FROM opportunities LIMIT 0')
        db.execute('SELECT id,user_id,read_at FROM tender_notifications LIMIT 0')
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE tender_generation SET value=value WHERE 0')
        db.execute('UPDATE opportunity_generation SET value=value WHERE 0')
        db.rollback()
    check_timezones(zones)
    return {'tenders': 'ok', 'opportunities': 'ok', 'timezones': 'ok', 'sqlite': 'ok'}
