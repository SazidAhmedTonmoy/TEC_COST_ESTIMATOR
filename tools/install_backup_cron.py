"""Install one idempotent 00:10 server-time cron job, preserving other jobs."""
import hashlib,shlex,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def cron_line(root=ROOT,python=None):
    root=Path(root).resolve();python=python or sys.executable
    quote=lambda s:shlex.quote(str(s)).replace('%',r'\%')
    tag='# TEC_CONEST_DAILY_'+hashlib.sha256(str(root).encode()).hexdigest()[:12]
    command=f'cd {quote(root)} && {quote(python)} {quote(root/"tools/backup_database.py")} --daily --runtime-config {quote(root/"tmp/backup-runtime.json")} >> {quote(root/"tmp/backup.log")} 2>&1'
    return '10 0 * * * '+command+' '+tag,tag

def updated_crontab(existing,line,tag):
    return '\n'.join([s for s in existing.splitlines() if not s.rstrip().endswith(tag)]+[line])+'\n'

def main():
    if not (ROOT/'tmp/backup-runtime.json').is_file():raise SystemExit('Visit the deployed /api/health endpoint before installing backups.')
    line,tag=cron_line()
    try:
        result=subprocess.run(['crontab','-l'],capture_output=True,text=True)
        if result.returncode and 'no crontab' not in result.stderr.lower():raise RuntimeError(result.stderr.strip() or 'Cannot read crontab')
        content=updated_crontab(result.stdout if not result.returncode else '',line,tag)
        subprocess.run(['crontab','-'],input=content,text=True,check=True)
    except (OSError,RuntimeError,subprocess.CalledProcessError) as exc:
        raise SystemExit('Could not install scheduled backups. Add this command in cPanel Cron Jobs at minute 10, hour 0, every day:\n'+line+'\n'+str(exc))
    print('Catalog and Tenders backups scheduled for 12:10 am every day, server time.')

if __name__=='__main__':main()
