"""Reconcile opportunity deadlines without a browser or a persistent web worker."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-config', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.runtime_config.read_text())
    for key, env in [('catalog','CONEST_DB_PATH'),('tenders','CONEST_TENDERS_DB_PATH')]:
        path = Path(config[key])
        if not path.is_absolute() or not path.is_file():
            raise SystemExit(f'{key} database not found; no replacement database was created.')
        os.environ[env] = str(path)
    from conest_app import opportunities, tenders
    # Use the existing connection helper without running startup migrations/seed
    # scans for every cron tick. The deployed app initializes tables on first use.
    store = object.__new__(tenders.Store)
    store.path = Path(os.environ['CONEST_TENDERS_DB_PATH'])
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='opportunities'").fetchone():
            return
    opportunities.reconcile(store)


if __name__ == '__main__':
    main()
