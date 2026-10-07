"""Administrator-only contribution summaries; no background polling or score ranking."""
import json
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
from . import tenders


def contribution_report(conn, user_id, since=''):
    if since:
        try:
            if date.fromisoformat(since).isoformat()!=since:
                raise ValueError()
        except ValueError:
            raise ValueError('Choose a valid start date.') from None
    start=datetime.combine(date.fromisoformat(since),time.min,ZoneInfo('Australia/Sydney')).astimezone(timezone.utc).isoformat() if since else ''
    user=conn.execute('SELECT id,name,username FROM users WHERE id=?',(user_id,)).fetchone()
    if not user:
        raise LookupError('User not found')
    grouped=[dict(r) for r in conn.execute('''SELECT action,COUNT(*) AS count FROM project_activity
        WHERE user_id=? AND created_at>=? GROUP BY action ORDER BY count DESC,action''',(user_id,start))]
    projects=conn.execute('''SELECT COUNT(DISTINCT project_id) FROM project_activity
        WHERE user_id=? AND created_at>=?''',(user_id,start)).fetchone()[0]
    recent=[{**dict(r),'app':'Estimator'} for r in conn.execute('''SELECT action,project_name AS project,created_at
        FROM project_activity WHERE user_id=? AND created_at>=? ORDER BY created_at DESC,id DESC LIMIT 30''',(user_id,start))]
    store=tenders.get_store()
    with store.connect() as db:
        groups=[dict(r) for r in db.execute('''SELECT action,COUNT(*) AS count FROM tender_activity
            WHERE actor_id=? AND created_at>=? GROUP BY action ORDER BY count DESC,action''',(user_id,start))]
        tender_count=db.execute('''SELECT COUNT(DISTINCT submission_id) FROM tender_activity
            WHERE actor_id=? AND created_at>=?''',(user_id,start)).fetchone()[0]
        imports=[json.loads(r[0]) for r in db.execute("SELECT details FROM tender_activity WHERE actor_id=? AND created_at>=? AND action='Imported Excel'",(user_id,start))]
        recent.extend({**dict(r),'app':'Tenders'} for r in db.execute('''SELECT action,project,created_at FROM tender_activity
            WHERE actor_id=? AND created_at>=? ORDER BY created_at DESC,id DESC LIMIT 30''',(user_id,start)))
    # Historical attribution is explicitly separate from measured website activity.
    data=store.all_data()
    username=user['username'].casefold()
    historical={
        'importedTenders':sum(bool(s.get('legacyImported')) for s in data['submissions']) if username=='tonmoy' else 0,
        'chaseUps':sum(bool(c.get('legacyChase')) for c in data['chases']) if username=='yunus' else 0,
    }
    return {'person':dict(user),'since':since,'estimator':{'projects':projects,'actions':grouped,'total':sum(r['count'] for r in grouped)},
            'tenders':{'submissions':tender_count,'actions':groups,'total':sum(r['count'] for r in groups),
                       'rowsAdded':sum(r.get('added',0) for r in imports),'rowsUpdated':sum(r.get('updated',0) for r in imports)},
            'historical':historical,'recent':sorted(recent,key=lambda r:r['created_at'],reverse=True)[:30]}
