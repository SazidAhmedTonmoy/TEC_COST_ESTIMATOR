"""Validate production against this checkout, never a stale schema literal."""
import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from conest_app import __version__
from conest_app.auto_upgrade import CURRENT_SCHEMA

def matches(response, require_tenders=False):
    if not isinstance(response, dict):return False
    ready = response.get('success') is True and response.get('status')=='ok' and response.get('release')==__version__ and response.get('schema_version')==CURRENT_SCHEMA
    if require_tenders:
        checks = response.get('checks')
        ready = ready and isinstance(checks, dict) and all(checks.get(name)=='ok' for name in ('tenders','opportunities','timezones','sqlite'))
    return bool(ready)

if __name__=='__main__':
    try:ok=matches(json.load(sys.stdin), require_tenders='--require-tenders' in sys.argv[1:])
    except (ValueError,AttributeError):ok=False
    sys.exit(0 if ok else 1)
