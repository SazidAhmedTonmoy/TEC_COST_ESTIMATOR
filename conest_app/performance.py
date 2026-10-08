"""Administrator-only contribution summaries; no background polling or score ranking."""
import json
from datetime import date, datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo
from . import tenders


def contribution_report(conn, user_id, since='', until=''):
    for value in (since,until):
        if value:
            try:
                if date.fromisoformat(value).isoformat()!=value:raise ValueError()
            except ValueError:raise ValueError('Choose valid start and end dates.') from None
    if since and until and since>until:raise ValueError('Start date must be before the end date.')
    zone=ZoneInfo('Australia/Sydney')
    start=datetime.combine(date.fromisoformat(since),time.min,zone).astimezone(timezone.utc).isoformat() if since else ''
    end=datetime.combine(date.fromisoformat(until)+timedelta(days=1),time.min,zone).astimezone(timezone.utc).isoformat() if until else '9999'
    user=conn.execute('SELECT id,name,username FROM users WHERE id=?',(user_id,)).fetchone()
    if not user:
        raise LookupError('User not found')
    grouped=[dict(r) for r in conn.execute('''SELECT action,COUNT(*) AS count FROM project_activity
        WHERE user_id=? AND created_at>=? AND created_at<? GROUP BY action ORDER BY count DESC,action''',(user_id,start,end))]
    projects=conn.execute('''SELECT COUNT(DISTINCT project_id) FROM project_activity
        WHERE user_id=? AND created_at>=? AND created_at<?''',(user_id,start,end)).fetchone()[0]
    recent=[{**dict(r),'app':'Estimator'} for r in conn.execute('''SELECT action,project_name AS project,created_at
        FROM project_activity WHERE user_id=? AND created_at>=? AND created_at<? ORDER BY created_at DESC,id DESC LIMIT 30''',(user_id,start,end))]
    store=tenders.get_store()
    with store.connect() as db:
        groups=[dict(r) for r in db.execute('''SELECT action,COUNT(*) AS count FROM tender_activity
            WHERE actor_id=? AND created_at>=? AND created_at<? GROUP BY action ORDER BY count DESC,action''',(user_id,start,end))]
        tender_count=db.execute('''SELECT COUNT(DISTINCT submission_id) FROM tender_activity
            WHERE actor_id=? AND created_at>=? AND created_at<?''',(user_id,start,end)).fetchone()[0]
        imports=[json.loads(r[0]) for r in db.execute("SELECT details FROM tender_activity WHERE actor_id=? AND created_at>=? AND created_at<? AND action='Imported Excel'",(user_id,start,end))]
        recent.extend({**dict(r),'app':'Tenders'} for r in db.execute('''SELECT action,project,created_at FROM tender_activity
            WHERE actor_id=? AND created_at>=? AND created_at<? ORDER BY created_at DESC,id DESC LIMIT 30''',(user_id,start,end)))
    # Historical attribution is explicitly separate from measured website activity.
    data=store.all_data()
    username=user['username'].casefold()
    historical={
        'importedTenders':sum(bool(s.get('legacyImported')) and (s.get('importedBy')==user_id or (not s.get('importedBy') and username=='tonmoy')) for s in data['submissions']),
        'chaseUps':sum(bool(c.get('legacyChase')) and (c.get('authorId')==user_id or (not c.get('authorId') and username=='yunus')) for c in data['chases']),
    }
    historical_chases=[c for c in data['chases'] if c.get('legacyChase') and (c.get('authorId')==user_id or (not c.get('authorId') and username=='yunus')) and (not since or c.get('date','')>=since) and (not until or c.get('date','')<=until)]
    credited_ids={c['submissionId'] for c in historical_chases}
    with store.connect() as db:
        credited_ids.update(r[0] for r in db.execute('SELECT DISTINCT submission_id FROM tender_activity WHERE actor_id=? AND created_at>=? AND created_at<? AND submission_id IS NOT NULL',(user_id,start,end)))
    tender_count=len(credited_ids)
    historical['periodChaseUps']=len(historical_chases)
    from .import_history import _HISTORY_SQL, _LEGACY_UPLOADER
    uploads=[dict(r) for r in conn.execute(_HISTORY_SQL+"SELECT kind,COUNT(*) AS count FROM history WHERE uploader_id=? AND imported_at>=? AND imported_at<? GROUP BY kind",(*_LEGACY_UPLOADER,user_id,start,end))]
    uploads.extend(dict(r) for r in conn.execute('SELECT kind,COUNT(*) AS count FROM document_uploads WHERE user_id=? AND created_at>=? AND created_at<? GROUP BY kind',(user_id,start,end)))
    json_count=next((r['count'] for r in grouped if r['action']=='Imported project JSON'),0)
    if json_count:uploads.append({'kind':'project JSON','count':json_count})
    with store.connect() as db:
        row=db.execute("SELECT body FROM settings WHERE id='confirmed-imports-v33c'").fetchone()
        credit=json.loads(row[0]) if row else {}
        confirmed=credit.get('uploads',0) if credit.get('actorId')==user_id else 0
        cutoff=credit.get('throughActivityId',0) if confirmed else 0
        file_count=db.execute("SELECT COUNT(*) FROM tender_activity WHERE actor_id=? AND action='Imported Excel' AND id>? AND created_at>=? AND created_at<?",(user_id,cutoff,start,end)).fetchone()[0]
    historical['importedFiles']=confirmed
    historical['importedTenders']=0  # Uploading rows is not estimating/chasing those submissions.
    if not since and not until:file_count+=confirmed
    if file_count:uploads.append({'kind':'tender Excel','count':file_count})
    return {'person':dict(user),'since':since,'until':until,'uploads':{'total':sum(r['count'] for r in uploads),'byType':uploads},'estimator':{'projects':projects,'actions':grouped,'total':sum(r['count'] for r in grouped)},
            'tenders':{'submissions':tender_count,'actions':groups,'total':sum(r['count'] for r in groups),
                       'rowsAdded':sum(r.get('added',0) for r in imports),'rowsUpdated':sum(r.get('updated',0) for r in imports)},
            'historical':historical,'recent':sorted(recent,key=lambda r:r['created_at'],reverse=True)[:30]}
