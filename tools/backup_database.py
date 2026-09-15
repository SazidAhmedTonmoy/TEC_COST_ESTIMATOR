"""Create a consistent backup in the shared two-snapshot backup folder."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from conest_app.database import database_path
from conest_app.backups import create_backup

def main():
    if not database_path().is_file():raise SystemExit('Database not found')
    result=create_backup()
    print('Backup created:',database_path().parent/'backups'/result['name'])

if __name__=='__main__':main()
