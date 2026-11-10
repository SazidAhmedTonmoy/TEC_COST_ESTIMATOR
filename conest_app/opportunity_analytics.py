"""Read-only, admin-only opportunity outcome analytics.

All displayed outcomes use the SAME active opportunity cohort and current
status rules. Filtering may use the original Added date (if supplied by an
Excel workbook) or the first time an opportunity was uploaded/created in
TEC ConEst. A closing deadline is never treated as an added date.

Legacy action-time metrics are retained for API compatibility; the visible
charts and contributor totals are all based on the selected creation cohort.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import opportunities as op, tenders
from .opportunity_retention import active_sql

SYDNEY = ZoneInfo('Australia/Sydney')
METRICS = ('added', 'approved', 'quoted')
OUTCOME_KEYS = ('added', 'approved', 'approvedNotQuoted', 'approvedQuoted',
                'rejected', 'expired', 'pending', 'review')


def _date(value, label):
    try:
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError()
        return date.fromisoformat(value)
    except ValueError:
        raise tenders.ValidationError('Choose a valid ' + label + ' date.') from None


def _stamp(value):
    """Convert a UTC/offset system timestamp to the Sydney calendar date."""
    if not isinstance(value, str) or not value:
        return None
    try:
        instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        return instant.astimezone(SYDNEY).date()
    except (ValueError, TypeError, OverflowError):
        return None


def _business_date(value):
    """Original added dates are *calendar dates*, not UTC instants."""
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _range(params, now=None):
    today = now or datetime.now(SYDNEY).date()
    mode = params.get('mode', 'month') or 'month'
    if mode == 'all':
        return mode, None, None
    if mode == 'month':
        month = params.get('month') or today.strftime('%Y-%m')
        if not isinstance(month, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
            raise tenders.ValidationError('Choose a valid analytics month.')
        start = _date(month + '-01', 'month')
        end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    elif mode == 'year':
        year = params.get('year') or str(today.year)
        if not str(year).isdigit() or not 2000 <= int(year) <= 2100:
            raise tenders.ValidationError('Choose a valid analytics year.')
        start = date(int(year), 1, 1)
        end = date(int(year) + 1, 1, 1)
    elif mode == 'custom':
        start = _date(params.get('from'), 'start')
        last = _date(params.get('to'), 'end')
        if last < start or (last - start).days > 366 * 5:
            raise tenders.ValidationError('Choose a date range up to five years with the end on or after the start.')
        end = last + timedelta(days=1)
    else:
        raise tenders.ValidationError('Choose Month, Month by month, Custom range, or All time.')
    return mode, start, end


def _months(start, end, known):
    if start is None:
        return sorted(known)
    cursor = date(start.year, start.month, 1)
    months = []
    while cursor < end:
        months.append(cursor.strftime('%Y-%m'))
        cursor = date(cursor.year + 1, 1, 1) if cursor.month == 12 else date(cursor.year, cursor.month + 1, 1)
    return months


def _zero_counts():
    return {key: 0 for key in OUTCOME_KEYS}


def summary(store, params, user, *, now=None):
    op.initialize(store)
    _, users = op.directory()
    actor = op._actor(user, users)
    if actor['role'] != 'admin':
        raise tenders.ValidationError('Opportunity analytics is available to administrators only.', 403)
    mode, start, end = _range(params, now)
    date_basis = params.get('dateBasis', 'added') or 'added'
    if date_basis not in ('added', 'uploaded'):
        raise tenders.ValidationError('Choose Original added date or Upload/creation date.')
    today = now or datetime.now(SYDNEY).date()
    names = {int(u['id']): u['name'] for u in users}
    active = active_sql('opportunity', 'o.id')
    with store.connect() as db:
        # The top-of-register cards use these very same live rows and statuses.
        rows = db.execute('''SELECT o.id,o.body,o.created_by,o.status,o.due
                             FROM opportunities o WHERE o.deleted_at IS NULL AND ''' + active).fetchall()
        activity = db.execute('''SELECT a.opportunity_id,a.actor_id,a.actor_name,a.action,a.created_at
              FROM opportunity_activity a JOIN opportunities o ON o.id=a.opportunity_id
              WHERE o.deleted_at IS NULL AND ''' + active + ''' AND a.action IN
              ('Created opportunity','Imported opportunity','Approved opportunity','Quoted opportunity')
              ORDER BY a.created_at,a.id''').fetchall()

    # A minority of older migrated records lack createdAt in their JSON. Their
    # original CREATE/IMPORT audit entry gives a stable timestamp without any
    # data rewrite or reliance on a subsequently edited updatedAt value.
    first_created = {}
    approved_ids, quoted_ids, events = set(), set(), []
    for entry in activity:
        action, oid = entry['action'], entry['opportunity_id']
        if action in ('Created opportunity', 'Imported opportunity'):
            first_created.setdefault(oid, entry['created_at'])
            continue
        metric = 'approved' if action == 'Approved opportunity' else 'quoted'
        (approved_ids if metric == 'approved' else quoted_ids).add(oid)
        events.append((metric, oid, entry['created_at'], entry['actor_id'], entry['actor_name']))

    outcome_counts = _zero_counts()
    by_creator = defaultdict(_zero_counts)
    by_month = defaultdict(_zero_counts)
    unavailable_dates = 0
    for row in rows:
        try:
            item = json.loads(row['body'])
            if not isinstance(item, dict):
                item = {}
        except (TypeError, ValueError):
            item = {}
        oid = row['id']
        creator_id = item.get('createdBy', row['created_by'])
        system_date = _stamp(item.get('createdAt')) or _stamp(first_created.get(oid))
        original_date = _business_date(item.get('addedDate'))
        recorded = ((original_date or system_date) if date_basis == 'added'
                    else (system_date or original_date))
        # The compatibility action-time count always uses upload/creation,
        # even when this row belongs to a different original Added-date cohort.
        events.append(('added', oid, item.get('createdAt') or first_created.get(oid) or '',
                       creator_id, item.get('createdByName') or 'Imported source'))
        if recorded is None:
            unavailable_dates += 1
        if start is not None and (recorded is None or not start <= recorded < end):
            continue

        identifier = creator_id if type(creator_id) is int and creator_id > 0 else None
        name = names.get(identifier) if identifier else None
        if not name:
            name = item.get('createdByName') or ('Workbook import' if creator_id == 0 else 'Unknown creator')
        creator_key = (identifier, name)
        month_key = recorded.strftime('%Y-%m') if recorded else 'Unknown date'

        # SQL status is canonical, just as it is for the register KPI cards.
        status = row['status'] if row['status'] in ('approved', 'rejected', 'expired', 'pending', 'review') else 'pending'
        # Read-only expiry fallback when a background sweep has not run yet.
        # The regular register performs this sweep on load.
        if status in ('pending', 'review') and row['due']:
            due = _business_date(row['due'])
            if due is not None and due < today:
                status = 'expired'
        keys = ['added', status]
        if status == 'approved':
            quoted = (item.get('quoteStatus') == 'quoted' or bool(item.get('submissionIds'))
                      or bool(item.get('linkedAt')))
            keys.append('approvedQuoted' if quoted else 'approvedNotQuoted')
        for bucket in (outcome_counts, by_creator[creator_key], by_month[month_key]):
            for key in keys:
                bucket[key] += 1

    # Retain the action-time API fields used by previous integrations/tests.
    # These are not mixed into the visible cohort/outcome cards.
    for row in rows:
        try:
            item = json.loads(row['body'])
            if not isinstance(item, dict):
                continue
        except (TypeError, ValueError):
            continue
        oid = row['id']
        if oid not in approved_ids and item.get('approvedAt'):
            events.append(('approved', oid, item.get('approvedAt'),
                           item.get('approvedBy'), item.get('approvedByName') or 'Historical approval'))
        if oid not in quoted_ids and item.get('quotedAt'):
            events.append(('quoted', oid, item.get('quotedAt'),
                           item.get('quotedBy'), item.get('quotedByName') or 'Historical quote'))
    legacy_counts = {metric: defaultdict(int) for metric in METRICS}
    legacy_months = defaultdict(lambda: {metric: 0 for metric in METRICS})
    seen = set()
    for metric, oid, at, person_id, actor_name in sorted(events, key=lambda event: event[2] or ''):
        recorded = _stamp(at)
        if recorded is None or (start is not None and not start <= recorded < end):
            continue
        key = (metric, oid)
        if key in seen:
            continue
        seen.add(key)
        identifier = person_id if type(person_id) is int and person_id > 0 else None
        name = names.get(identifier) if identifier else None
        if not name:
            name = actor_name or 'Unknown'
        legacy_counts[metric][(identifier, name)] += 1
        legacy_months[recorded.strftime('%Y-%m')][metric] += 1
    totals = {metric: sum(legacy_counts[metric].values()) for metric in METRICS}
    contributors = {metric: [
        {'id': identifier, 'name': name, 'count': count}
        for (identifier, name), count in sorted(legacy_counts[metric].items(),
                                                key=lambda entry: (-entry[1], entry[0][1].casefold()))]
                    for metric in METRICS}
    creators = [{'id': identifier, 'name': name, **counts}
                for (identifier, name), counts in sorted(by_creator.items(),
                    key=lambda entry: (-entry[1]['added'], entry[0][1].casefold()))]
    known_months = set(legacy_months) | set(by_month)
    monthly = [{'month': month, **legacy_months[month]} for month in _months(start, end, known_months)]
    monthly_outcomes = [{'month': month, **by_month[month]} for month in _months(start, end, set(by_month))]
    return {'mode': mode, 'dateBasis': date_basis,
            'from': start.isoformat() if start else None,
            'to': (end - timedelta(days=1)).isoformat() if end else None,
            'timezone': 'Australia/Sydney', 'counts': totals, 'contributors': contributors,
            'monthly': monthly, 'outcomes': outcome_counts, 'creators': creators,
            'monthlyOutcomes': monthly_outcomes, 'activeTotal': len(rows),
            'outsidePeriod': len(rows) - outcome_counts['added'] if start else 0,
            'missingDates': unavailable_dates}
