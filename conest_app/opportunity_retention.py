"""Logical reset membership without removing legacy foreign-key parents.

The owner-requested reset retires a fixed cohort from the active register.
Original records, links and historical activity remain unchanged. A builder
name may be used again later without rewriting the original reset record.
"""
from __future__ import annotations


KINDS = frozenset(('opportunity', 'notification', 'builder'))


def ensure_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS opportunity_reset_entries (
        kind TEXT NOT NULL, record_key TEXT NOT NULL,
        retired_at TEXT NOT NULL, restored_at TEXT,
        PRIMARY KEY(kind,record_key))''')
    db.execute('''CREATE TABLE IF NOT EXISTS opportunity_reset_history (
        reset_key TEXT PRIMARY KEY, actor_name TEXT NOT NULL,
        action TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL)''')


def active_sql(kind, key_sql):
    """Return a predicate for a trusted, application-owned SQL key expression."""
    if kind not in KINDS:
        raise ValueError('Unknown opportunity reset record kind')
    return ("NOT EXISTS (SELECT 1 FROM opportunity_reset_entries reset_entry "
            "WHERE reset_entry.kind='" + kind + "' AND reset_entry.record_key=" + key_sql +
            ' AND reset_entry.restored_at IS NULL)')


def is_retired(db, kind, key):
    if kind not in KINDS:
        raise ValueError('Unknown opportunity reset record kind')
    return db.execute('''SELECT 1 FROM opportunity_reset_entries
        WHERE kind=? AND record_key=? AND restored_at IS NULL''', (kind, key)).fetchone() is not None


def reactivate_builder(db, key, moment):
    db.execute('''UPDATE opportunity_reset_entries SET restored_at=?
        WHERE kind='builder' AND record_key=? AND restored_at IS NULL''', (moment, key))


def retire_current(db, moment):
    """Capture the cohort while the caller excludes concurrent writers."""
    db.execute('''INSERT INTO opportunity_reset_entries(kind,record_key,retired_at)
        SELECT 'opportunity',id,? FROM opportunities''', (moment,))
    db.execute('''INSERT INTO opportunity_reset_entries(kind,record_key,retired_at)
        SELECT 'builder',builder_key,? FROM opportunity_builders''', (moment,))
    db.execute('''INSERT INTO opportunity_reset_entries(kind,record_key,retired_at)
        SELECT 'notification',id,? FROM tender_notifications WHERE target_kind='opportunity' ''', (moment,))
