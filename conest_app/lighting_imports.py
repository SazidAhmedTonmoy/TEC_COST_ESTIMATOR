"""Two-phase quotation review: inspect first, then explicitly save selected quotes.

Existing quotes are never overwritten. Exact duplicates are always skipped;
revised or matching-data quotes require a deliberate checkbox selection.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .accounts import AccessError
from .database import connect, database_path, write_lock
from .utils import utc_now

PREVIEW_SECONDS = 30 * 60
MAX_MANIFEST_BYTES = 80 * 1024 * 1024


def _text(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip().casefold()


def _numeric(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        decimal = Decimal(str(value))
        if not decimal.is_finite():
            return str(value)
        return format(decimal.normalize(), 'f') if decimal else '0'
    except InvalidOperation:
        return _text(value)


def canonical_digest(quote):
    # Ignore row order/formatting, never price, quantity or distinct repeated rows.
    rows = []
    for line in quote['lines']:
        rows.append({
            'type': _text(line.get('type_effective')),
            'supplier': _text(line.get('supplier')),
            'cat_no': re.sub(r'\s+', '', str(line.get('cat_no') or '')).casefold(),
            'description': _text(line.get('description')),
            **{key: _numeric(line.get(key)) for key in ('quantity', 'unit_ex', 'total_ex')},
        })
    rows.sort(key=lambda row: json.dumps(row, sort_keys=True))
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def backfill_signatures(conn):
    """Use original import fields where retained, not a user's edited price."""
    from .light_prices import normal_line
    for quote in conn.execute('SELECT id FROM quotes WHERE canonical_hash IS NULL').fetchall():
        lines = []
        for row in conn.execute('''SELECT l.* FROM lines l JOIN groups g ON g.id=l.group_id
                                   WHERE g.quote_id=? ORDER BY l.id''', (quote['id'],)):
            original = None
            try:
                values = json.loads(row['source_values'] or '{}')
                if isinstance(values, dict) and values.get('Description'):
                    original = normal_line(values, row['source_row'] or 0)
            except (ValueError, TypeError, KeyError):
                pass
            lines.append(original or dict(row))
        if lines:
            conn.execute('UPDATE quotes SET canonical_hash=? WHERE id=?', (canonical_digest({'lines': lines}), quote['id']))


def _quote_meta(row):
    return {key: row[key] for key in ('id', 'reference', 'project', 'quote_date', 'source', 'imported_at', 'total_ex')}


def classify_quotes(conn, quotes):
    from .light_prices import quote_digest, date_text, group_lines
    existing = [dict(row) for row in conn.execute('SELECT * FROM quotes ORDER BY id DESC')]
    product_keys = {(_text(row[0]), re.sub(r'\s+', '', str(row[1] or '')).casefold())
                    for row in conn.execute("SELECT DISTINCT supplier,cat_no FROM lines WHERE TRIM(COALESCE(cat_no,''))<>''")}
    results = []
    for index, quote in enumerate(quotes):
        digest = canonical_digest(quote)
        old_digest = quote_digest(quote)
        same_ref = [row for row in existing if _text(row['reference']) == _text(quote['reference'])]
        same_data = [row for row in existing if row['canonical_hash'] == digest or row['content_hash'] == old_digest]
        exact = [row for row in same_data if _text(row['reference']) == _text(quote['reference'])
                 and _text(date_text(row['quote_date'])) == _text(date_text(quote['quote_date']))]
        status = 'identical' if exact else 'revised' if same_ref else 'matching_data' if same_data else 'new'
        matches = exact or same_ref or same_data
        product_matches = sum(1 for line in quote['lines'] if line.get('cat_no') and
            (_text(line.get('supplier')), re.sub(r'\s+', '', line['cat_no']).casefold()) in product_keys)
        source_sum = round(sum(line['total_ex'] for line in quote['lines'] if line.get('total_ex') is not None), 2)
        results.append({
            'key': str(index), 'reference': quote['reference'], 'quote_date': quote['quote_date'],
            'project': quote['project'], 'source': quote.get('source') or '', 'status': status,
            'selected': status == 'new', 'can_import': status != 'identical',
            'line_count': len(quote['lines']), 'group_count': len(group_lines(quote['lines'])),
            'quoted_total_ex': quote.get('total_ex'), 'parsed_total_ex': source_sum,
            'unpriced_rows': sum(1 for line in quote['lines'] if line.get('total_ex') is None),
            'matching_product_rows': product_matches,
            'matches': [_quote_meta(row) for row in matches[:10]],
            'match_count': len(matches), 'related_ids': [row['id'] for row in matches],
            'lines': [{key: line.get(key) for key in ('item_no', 'description', 'supplier', 'cat_no', 'quantity', 'unit_ex', 'total_ex')}
                      for line in quote['lines']],
        })
    return results


def _folder():
    folder = database_path().parent / 'lighting_import_previews'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder


def _preview_path(token):
    if not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{32}', token):
        raise ValueError('Invalid quotation review. Check the file again.')
    path = _folder() / (token + '.json')
    if path.is_symlink():
        raise ValueError('Invalid quotation review file')
    return path


def _cleanup():
    before = time.time() - PREVIEW_SECONDS
    for path in _folder().glob('*.json'):
        try:
            if not path.is_symlink() and path.stat().st_mtime < before:
                path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass


def create_preview(filename, content, user, authorize=None):
    from .quotation_parser import parse_content
    _cleanup()
    quotes, excluded = parse_content(filename, content)
    token = uuid.uuid4().hex
    with connect() as conn:
        if authorize:
            authorize(conn)
        checked = classify_quotes(conn, quotes)
    manifest = {'user_id': user['id'], 'created_at': time.time(), 'filename': Path(filename).name,
                'file_sha256': hashlib.sha256(content).hexdigest(), 'quotes': quotes,
                'excluded': excluded, 'checked': [{k: row[k] for k in ('status', 'related_ids')} for row in checked]}
    encoded = json.dumps(manifest, ensure_ascii=False).encode('utf-8')
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError('The extracted quotation is too large for review. Split it into smaller files.')
    path = _preview_path(token)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(encoded)
    return {'preview_id': token, 'filename': manifest['filename'], 'expires_in': PREVIEW_SECONDS,
            'quotes': checked, 'notes_excluded': excluded,
            'summary': {status: sum(row['status'] == status for row in checked)
                        for status in ('new', 'identical', 'revised', 'matching_data')}}


def _read_preview(token, user):
    path = _preview_path(token)
    if not path.exists():
        raise AccessError(410, 'This quotation review has expired or was cancelled. Check the file again.')
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError('The stored review is invalid. Check the file again.')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest['user_id'] != user['id']:
        raise AccessError(403, 'This quotation review belongs to another account')
    if time.time() - manifest['created_at'] > PREVIEW_SECONDS:
        path.unlink(missing_ok=True)
        raise AccessError(410, 'This quotation review expired after 30 minutes. Check the file again.')
    return manifest


def cancel_preview(token, user):
    _read_preview(token, user)
    _preview_path(token).unlink(missing_ok=True)


def commit_preview(token, selected, user, authorize=None):
    from .light_prices import quote_digest, insert_quote
    if not isinstance(selected, list) or any(not isinstance(key, str) for key in selected) or len(set(selected)) != len(selected):
        raise ValueError('Select the quotations to import using the review checkboxes')
    if not selected:
        raise ValueError('Select at least one quotation to import')
    _preview_path(token)  # Validate token even for a replayed receipt.
    with write_lock:
        with connect() as conn:
            if authorize:
                authorize(conn)
            receipt = conn.execute('SELECT * FROM lighting_import_receipts WHERE token=?', (token,)).fetchone()
            if receipt:
                if receipt['user_id'] != user['id']:
                    raise AccessError(403, 'This import belongs to another account')
                return {**json.loads(receipt['report_json']), 'already_completed': True}
        manifest = _read_preview(token, user)
        if any(key not in {str(i) for i in range(len(manifest['quotes']))} for key in selected):
            raise ValueError('Invalid quotation selection. Check the file again.')
        with connect() as check:
            current = classify_quotes(check, manifest['quotes'])
            needs_write = any(row['key'] in selected and row['status'] != 'identical' for row in current)
        if needs_write:
            from .backups import create_backup
            try:
                create_backup('before-import', user['name'])
            except OSError as exc:
                raise ValueError('The safety backup could not be written. No prices were imported. Ask your administrator to check available disk space and folder permissions.') from exc
        report = {'quotes_added': 0, 'quotes_skipped': 0, 'quotes_not_selected': 0,
                  'groups_added': 0, 'lines_added': 0, 'notes_excluded': manifest['excluded']}
        with connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if authorize:
                authorize(conn)
            # Cross-process idempotency: another worker may have committed while
            # this worker was making its backup.
            receipt = conn.execute('SELECT * FROM lighting_import_receipts WHERE token=?', (token,)).fetchone()
            if receipt:
                if receipt['user_id'] != user['id']:
                    raise AccessError(403, 'This import belongs to another account')
                return {**json.loads(receipt['report_json']), 'already_completed': True}
            current = classify_quotes(conn, manifest['quotes'])
            for index, (quote, checked) in enumerate(zip(manifest['quotes'], current)):
                if checked['status'] == 'identical':
                    report['quotes_skipped'] += 1; continue
                if str(index) not in selected:
                    report['quotes_not_selected'] += 1; continue
                prior = manifest['checked'][index]
                if checked['status'] != prior['status'] or checked['related_ids'] != prior['related_ids']:
                    raise AccessError(409, 'The price library changed after this check. Check the file again and review the updated matches before importing.')
                _, groups, lines = insert_quote(conn, quote, quote_digest(quote), canonical_digest(quote), manifest['file_sha256'])
                report['quotes_added'] += 1; report['groups_added'] += groups; report['lines_added'] += lines
            conn.execute('INSERT INTO lighting_import_receipts VALUES (?,?,?,?,?,?)',
                (token, user['id'], manifest['filename'], manifest['file_sha256'], json.dumps(report), utc_now()))
    _preview_path(token).unlink(missing_ok=True)
    return report
