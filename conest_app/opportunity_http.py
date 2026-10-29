"""Authenticated opportunity and unified inbox routes for the Tender workspace."""
import base64
import binascii
import threading
from urllib.parse import parse_qs, urlsplit

from . import opportunities, tenders

_IMPORT_SLOTS = threading.BoundedSemaphore(2)


def route(handler, path, store, send):
    prefix = '/api/tenders/opportunities'
    notification_path = '/api/tenders/notifications'
    if not (path == prefix or path.startswith(prefix + '/') or path == notification_path or path.startswith(notification_path + '/')):
        return False
    opportunities.initialize(store)
    params = {key: values[-1] for key, values in parse_qs(urlsplit(handler.path).query).items()}
    if handler.command == 'GET':
        if path == prefix:
            result = opportunities.list_opportunities(store, params, handler.user)
        elif path == prefix + '/duplicates':
            from .opportunity_matching import check_duplicates
            result = check_duplicates(store, params, handler.user)
        elif path == prefix + '/link-projects':
            from .opportunity_matching import project_choices
            result = project_choices(store, params, handler.user)
        elif path == prefix + '/detail':
            result = opportunities.detail(store, params.get('id'), handler.user)
        elif path == prefix + '/activity':
            result = opportunities.activity_history(store, params, handler.user)
        elif path == prefix + '/regions':
            result = opportunities.regions(store, handler.user)
        elif path == notification_path:
            result = opportunities.notifications(store, params, handler.user)
        elif path in (prefix + '/export.xlsx', prefix + '/template.xlsx'):
            from .opportunity_import import export_workbook
            identifiers = params.get('ids', '')
            ids = [identifier for identifier in identifiers.split(',') if identifier] if identifiers else None
            if ids is None and not path.endswith('/template.xlsx'):
                opportunities.process_due(store)
                where, values = opportunities._query(params)
                with store.connect() as db:
                    ids = [r[0] for r in db.execute('SELECT o.id FROM opportunities o WHERE ' + where, values)]
            content = export_workbook(store, ids=ids, template=path.endswith('/template.xlsx'))
            send(handler, content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                 'TEC-Opportunities-Template.xlsx' if path.endswith('/template.xlsx') else 'TEC-Opportunities.xlsx')
            return True
        else:
            raise tenders.ValidationError('Not found', 404)
        send(handler, result)
        return True
    if handler.command not in ('POST', 'DELETE'):
        raise tenders.ValidationError('Method not allowed', 405)
    payload = handler._json_body()
    if path == prefix and handler.command == 'DELETE':
        result = opportunities.delete(store, payload, handler.user)
    elif handler.command != 'POST':
        raise tenders.ValidationError('Not found', 404)
    elif path == prefix + '/save':
        result = opportunities.save(store, payload, handler.user)
    elif path == prefix + '/decision':
        result = opportunities.decide(store, payload, handler.user)
    elif path == prefix + '/link-project':
        from .opportunity_matching import link_project
        result = link_project(store, payload, handler.user)
    elif path == prefix + '/quote':
        result = opportunities.quote(store, payload, handler.user)
    elif path in (prefix + '/assign', prefix + '/access'):
        result = opportunities.update_authority(store, payload, handler.user, path.rsplit('/', 1)[-1])
    elif path == prefix + '/regions':
        result = opportunities.regions(store, handler.user, payload)
    elif path == notification_path + '/read':
        result = opportunities.mark_read(store, payload, handler.user)
    elif path == prefix + '/import':
        from .opportunity_import import import_workbook, MAX_BYTES
        encoded = payload.get('content')
        if not isinstance(encoded, str) or len(encoded) > ((MAX_BYTES + 2) // 3) * 4:
            raise tenders.ValidationError('Choose a workbook smaller than 15 MB.')
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise tenders.ValidationError('Invalid workbook upload.') from None
        mode = payload.get('mode', 'preview')
        if mode not in ('preview', 'apply'):
            raise tenders.ValidationError('Invalid import action.')
        expected = tenders.text(payload.get('token'), 'Preview token', required=True, limit=100) if mode == 'apply' else None
        if not _IMPORT_SLOTS.acquire(blocking=False):
            raise tenders.ValidationError('Two workbooks are being processed. Please try again shortly.', 503)
        try:
            result = import_workbook(store,
                tenders.text(payload.get('filename'), 'Filename', required=True, limit=255),
                content, handler.user, expected_token=expected,
                region_hint=tenders.text(payload.get('region'), 'Region', limit=50))
        finally:
            _IMPORT_SLOTS.release()
    else:
        raise tenders.ValidationError('Not found', 404)
    send(handler, result)
    return True
