"""Optional project builders, using the existing client TEXT column.

The database column is kept for compatibility with previous installations and
revision snapshots. Each builder occupies one line. Commas, ampersands and
semicolons are part of a name, never guessed as separators. No schema change or
rewrite of historical project records is needed.
"""
from __future__ import annotations

from .utils import clean_text

MAX_BUILDERS = 100
MAX_NAME_LENGTH = 500
MAX_TOTAL_LENGTH = 20000


def read_builders(project):
    """Return a list for old scalar clients and current multi-builder records."""
    values = project.get('builders')
    if not isinstance(values, list):
        values = str(project.get('client') or '').splitlines()
    names = []
    seen = set()
    for value in values:
        name = clean_text(value)
        if name and name.casefold() not in seen:
            names.append(name)
            seen.add(name.casefold())
    return names


def validate_builders(values):
    if not isinstance(values, list) or len(values) > MAX_BUILDERS:
        raise ValueError('Builders must be a list of up to 100 names')
    for value in values:
        if not isinstance(value, str):
            raise ValueError('Each builder must be a name')
        if any(ord(c) < 32 and c != '\t' for c in value) or '\x7f' in value or '\u2028' in value or '\u2029' in value:
            raise ValueError('Enter each builder as a separate name')
        if len(clean_text(value)) > MAX_NAME_LENGTH:
            raise ValueError('Each builder name must be 500 characters or fewer')
    names = read_builders({'builders': values})
    if len('\n'.join(names)) > MAX_TOTAL_LENGTH:
        raise ValueError('Builder names must total 20,000 characters or fewer')
    return names


def stored_builders(payload, current=None):
    """Resolve new API lists or legacy clients; omitted fields stay unchanged."""
    if 'builders' in payload:
        return '\n'.join(validate_builders(payload['builders']))
    if 'client' in payload:
        client = payload['client']
        if client is not None and not isinstance(client, str):
            raise ValueError('Builder must be text')
        return '\n'.join(validate_builders((client or '').splitlines()))
    return (current or {}).get('client') or ''


def project_with_builders(project):
    result = dict(project)
    result['builders'] = read_builders(result)
    return result
