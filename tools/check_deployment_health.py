"""Validate production against this checkout without logging response bodies."""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conest_app import __version__
from conest_app.auto_upgrade import CURRENT_SCHEMA


REQUIRED_CHECKS = ('tenders', 'opportunities', 'timezones', 'sqlite')


def _release_label(value):
    # The response is untrusted. Never print arbitrary version/error text: it
    # could contain proxy HTML, control characters, paths or credentials.
    if isinstance(value, str) and re.fullmatch(r'[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}', value):
        return value
    return 'missing or invalid'


def _schema_label(value):
    return str(value) if type(value) is int and 0 <= value <= 1000000 else 'missing or invalid'


def validation_errors(response, require_tenders=False):
    """Return safe reasons for rejection; an empty list means ready."""
    if not isinstance(response, dict):
        return ['Health response is not a JSON object.']
    errors = []
    if response.get('success') is not True or response.get('status') != 'ok':
        errors.append('Application health is not ready.')
    if response.get('release') != __version__:
        errors.append(
            f'Release mismatch: expected {__version__}, received {_release_label(response.get("release"))}. '
            'Verify the upload destination and restart the Passenger application serving this URL.'
        )
    if response.get('schema_version') != CURRENT_SCHEMA:
        errors.append(
            f'Schema mismatch: expected {CURRENT_SCHEMA}, received {_schema_label(response.get("schema_version"))}.'
        )
    if require_tenders:
        checks = response.get('checks')
        pending = [name for name in REQUIRED_CHECKS
                   if not isinstance(checks, dict) or checks.get(name) != 'ok']
        if pending:
            errors.append('Required checks are not ready: ' + ', '.join(pending) + '.')
    return errors


def matches(response, require_tenders=False):
    """Keep the existing boolean API and strict release/schema checks."""
    return not validation_errors(response, require_tenders=require_tenders)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-tenders', action='store_true',
                        help='Require Tender, Opportunity, timezone and SQLite checks')
    parser.add_argument('--explain', action='store_true',
                        help='Print safe rejection reasons to stderr; never the response body')
    args = parser.parse_args(argv)
    try:
        response = json.load(sys.stdin)
        errors = validation_errors(response, require_tenders=args.require_tenders)
    except (ValueError, RecursionError):
        errors = ['Health response is not valid JSON. Check the site URL, proxy and application startup.']
    if errors and args.explain:
        print('Deployment health check failed: ' + ' '.join(errors), file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
