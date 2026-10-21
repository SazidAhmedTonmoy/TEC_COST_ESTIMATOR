"""Process due opportunity events for a Passenger deployment, without a browser."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-config', type=Path, required=True)
    args = parser.parse_args()
    if not args.runtime_config.is_file():
        raise SystemExit('Open /api/health on the deployed app before scheduling deadline checks.')
    config = json.loads(args.runtime_config.read_text())
    for key, env in [('catalog', 'CONEST_DB_PATH'), ('tenders', 'CONEST_TENDERS_DB_PATH')]:
        path = Path(config[key])
        if not path.is_absolute():
            raise SystemExit('Invalid runtime database path.')
        if not path.is_file():
            if key == 'tenders':
                # The first Tender visit creates its database and loads the seed.
                return
            raise SystemExit('The existing catalog database could not be found.')
        os.environ[env] = str(path)
    from conest_app import opportunities, tenders
    opportunities.process_due(tenders.get_store(), force=True)


if __name__ == '__main__':
    main()
