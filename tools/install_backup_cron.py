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

def opportunity_cron_line(root=ROOT,python=None):
    root=Path(root).resolve();python=python or sys.executable
    quote=lambda s:shlex.quote(str(s)).replace('%',r'\%')
    tag='# TEC_CONEST_OPPORTUNITIES_'+hashlib.sha256(str(root).encode()).hexdigest()[:12]
    command=f'cd {quote(root)} && {quote(python)} {quote(root/"tools/check_opportunity_deadlines.py")} --runtime-config {quote(root/"tmp/backup-runtime.json")} >> {quote(root/"tmp/opportunities.log")} 2>&1'
    return '*/5 * * * * '+command+' '+tag

def main():
    if not (ROOT/'tmp/backup-runtime.json').is_file():raise SystemExit('Visit the deployed /api/health endpoint before installing backups.')
    line,tag=cron_line()
    opportunity_line,opportunity_tag=opportunity_cron_line()
    try:
        result=subprocess.run(['crontab','-l'],capture_output=True,text=True)
        if result.returncode and 'no crontab' not in result.stderr.lower():raise RuntimeError(result.stderr.strip() or 'Cannot read crontab')
        content=updated_crontab(result.stdout if not result.returncode else '',line,tag)
        content=updated_crontab(content,opportunity_line,opportunity_tag)
        subprocess.run(['crontab','-'],input=content,text=True,check=True)
    except (OSError,RuntimeError,subprocess.CalledProcessError) as exc:
        raise SystemExit('Could not install scheduled jobs. Add these lines in cPanel Cron Jobs:\n'+line+'\n'+opportunity_line+'\n'+str(exc))
    print('Catalog and Tenders backups scheduled for 12:10 am every day, server time.')
    print('Opportunity deadline checks scheduled every five minutes (Sydney closing dates).')

if __name__=='__main__':main()
