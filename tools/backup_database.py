"""Back up both databases; cron uses paths registered by the running website."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--daily',action='store_true');parser.add_argument('--runtime-config',type=Path)
    args=parser.parse_args()
    if args.runtime_config:
        if not args.runtime_config.is_file():raise SystemExit('Runtime backup configuration is missing. Open /api/health on the website first.')
        config=json.loads(args.runtime_config.read_text())
        for key,env in [('catalog','CONEST_DB_PATH'),('tenders','CONEST_TENDERS_DB_PATH')]:
            path=Path(config[key])
            if not path.is_absolute() or (key=='catalog' and not path.is_file()):raise SystemExit(f'{key} database not found; no replacement database was created.')
            os.environ[env]=str(path)
    from conest_app.database import database_path
    from conest_app.backups import create_backup_set,daily_backup
    if not database_path().is_file():raise SystemExit('Catalog database not found')
    result=daily_backup() if args.daily else create_backup_set()
    for item in result:print('Backup created:',item['database'],item['name'])
    if not result:print('Daily backup is not due or has already completed today.')

if __name__=='__main__':main()
