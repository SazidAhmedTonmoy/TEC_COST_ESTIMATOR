"""Validate production against this checkout, never a stale schema literal."""
import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from conest_app import __version__
from conest_app.auto_upgrade import CURRENT_SCHEMA

def matches(response):
    return response.get('success') is True and response.get('status')=='ok' and response.get('release')==__version__ and response.get('schema_version')==CURRENT_SCHEMA

if __name__=='__main__':
    try:ok=matches(json.load(sys.stdin))
    except (ValueError,AttributeError):ok=False
    sys.exit(0 if ok else 1)
