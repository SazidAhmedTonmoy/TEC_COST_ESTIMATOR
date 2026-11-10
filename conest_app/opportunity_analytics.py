"""Admin-only, event-time opportunity activity analytics without a schema change.

Adds use each opportunity's immutable createdAt. Approvals and quotes use
actor-attributed audit actions, with historical timestamp fallbacks only where
no corresponding audit event exists. Deadlines are deliberately not counted.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import opportunities as op, tenders
from .opportunity_retention import active_sql

SYDNEY=ZoneInfo('Australia/Sydney')
METRICS=('added', 'approved', 'quoted')


def _date(value, label):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat()!=value:
            raise ValueError()
        return date.fromisoformat(value)
    except ValueError:
        raise tenders.ValidationError('Choose a valid ' + label + ' date.') from None


def _stamp(value):
    if not isinstance(value,str) or not value:return None
    try:
        moment=datetime.fromisoformat(value.replace('Z','+00:00'))
        if moment.tzinfo is None:moment=moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(SYDNEY).date()
    except ValueError:
        return None


def _range(params, now=None):
    today=now or datetime.now(SYDNEY).date()
    mode=params.get('mode','month') or 'month'
    if mode=='month':
        month=params.get('month') or today.strftime('%Y-%m')
        if not isinstance(month,str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',month):
            raise tenders.ValidationError('Choose a valid analytics month.')
        start=_date(month+'-01','month')
        end=date(start.year+1,1,1) if start.month==12 else date(start.year,start.month+1,1)
    elif mode=='year':
        year=params.get('year') or str(today.year)
        if not str(year).isdigit() or not 2000<=int(year)<=2100:
            raise tenders.ValidationError('Choose a valid analytics year.')
        start=date(int(year),1,1);end=date(int(year)+1,1,1)
    elif mode=='custom':
        start=_date(params.get('from'),'start')
        last=_date(params.get('to'),'end')
        if last<start or (last-start).days>366*5:
            raise tenders.ValidationError('Choose a date range up to five years with the end on or after the start.')
        end=last+timedelta(days=1)
    else:
        raise tenders.ValidationError('Choose Month, Year, or Custom date range.')
    return mode,start,end


def summary(store, params, user, *, now=None):
    op.initialize(store)
    _,users=op.directory()
    actor=op._actor(user, users)
    if actor['role']!='admin':
        raise tenders.ValidationError('Opportunity analytics is available to administrators only.',403)
    mode,start,end=_range(params,now)
    names={int(u['id']):u['name'] for u in users}
    events=[]
    # Use only active register records (exclude archived/deleted reset cohorts).
    with store.connect() as db:
        rows=db.execute('SELECT o.id,o.body,o.created_by FROM opportunities o WHERE o.deleted_at IS NULL AND '
                         +active_sql('opportunity','o.id')).fetchall()
        activity=db.execute("""SELECT a.opportunity_id,a.actor_id,a.actor_name,a.action,a.created_at
            FROM opportunity_activity a JOIN opportunities o ON o.id=a.opportunity_id
            WHERE o.deleted_at IS NULL AND """+active_sql('opportunity','o.id')+
            " AND a.action IN ('Approved opportunity','Quoted opportunity') ORDER BY a.created_at,a.id").fetchall()
    approved_ids=set();quoted_ids=set()
    for event in activity:
        key='approved' if event['action']=='Approved opportunity' else 'quoted'
        (approved_ids if key=='approved' else quoted_ids).add(event['opportunity_id'])
        events.append((key,event['opportunity_id'],event['created_at'],event['actor_id'],event['actor_name']))
    for row in rows:
        try:item=json.loads(row['body'])
        except (TypeError,ValueError):continue
        oid=row['id']
        events.append(('added',oid,item.get('createdAt',''),item.get('createdBy',row['created_by']),item.get('createdByName') or 'Imported source'))
        if oid not in approved_ids and item.get('approvedAt'):
            events.append(('approved',oid,item.get('approvedAt'),item.get('approvedBy'),item.get('approvedByName') or 'Historical approval'))
        if oid not in quoted_ids and item.get('quotedAt'):
            events.append(('quoted',oid,item.get('quotedAt'),item.get('quotedBy'),item.get('quotedByName') or 'Historical quote'))
    by_metric={metric:defaultdict(int) for metric in METRICS}
    month_counts=defaultdict(lambda:{metric:0 for metric in METRICS})
    seen=set()
    for metric,oid,at,person_id,actor_name in sorted(events,key=lambda x:x[2] or ''):
        recorded=_stamp(at)
        if not recorded or not start<=recorded<end:continue
        # A single opportunity is counted once in each metric in a selected period.
        key=(metric,oid)
        if key in seen:continue
        seen.add(key)
        identifier=person_id if isinstance(person_id,int) else None
        name=names.get(identifier) if identifier else None
        if not name:name=actor_name or ('Workbook import' if identifier==0 else 'Unknown')
        by_metric[metric][(identifier,name)]+=1
        month_counts[recorded.strftime('%Y-%m')][metric]+=1
    totals={metric:sum(by_metric[metric].values()) for metric in METRICS}
    contributors={metric:[{'id':identifier,'name':name,'count':count}
        for (identifier,name),count in sorted(by_metric[metric].items(),key=lambda value:(-value[1],value[0][1].casefold()))]
        for metric in METRICS}
    months=[];cursor=date(start.year,start.month,1)
    while cursor<end:
        month=cursor.strftime('%Y-%m')
        months.append({'month':month,**month_counts[month]})
        cursor=date(cursor.year+1,1,1) if cursor.month==12 else date(cursor.year,cursor.month+1,1)
    return {'mode':mode,'from':start.isoformat(),'to':(end-timedelta(days=1)).isoformat(),
            'timezone':'Australia/Sydney','counts':totals,'contributors':contributors,'monthly':months}
