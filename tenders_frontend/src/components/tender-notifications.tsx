import {useCallback,useEffect,useRef,useState} from 'react';
import {ArrowUpRight,Bell,CalendarClock,CheckCheck,RefreshCw} from 'lucide-react';
import {Sheet,SheetContent,SheetHeader,SheetTitle,SheetDescription} from './ui/sheet';
import {apiFetch} from '../main';
import type {NotificationList,TenderNotification} from '@/lib/opportunity-types';

export function TenderNotifications({onOpenOpportunity,onOpenTender}:{onOpenOpportunity:(id:string)=>void;onOpenTender:(id:string)=>void}) {
  const [open,setOpen]=useState(false), [data,setData]=useState<NotificationList|null>(null);
  const [error,setError]=useState(''), [busy,setBusy]=useState(false), [loadedPage,setLoadedPage]=useState(1);
  const [kind,setKind]=useState('all');
  const openRef=useRef(false), pending=useRef(false), readPending=useRef(new Set<string>());
  const markRead=useCallback(async (items:TenderNotification[])=>{
    const ids=items.filter(n=>!n.read&&!readPending.current.has(n.id)).map(n=>n.id);
    if(!ids.length)return;
    ids.forEach(id=>readPending.current.add(id));
    try {
      const response=await apiFetch('notifications/read',{method:'POST',body:JSON.stringify({ids})});
      const result=await response.json();if(!response.ok)throw Error(result.error||'Unable to mark notifications as read.');
      setData(previous=>previous?{...previous,items:previous.items.map(n=>ids.includes(n.id)?{...n,read:true}:n),unreadCount:result.unreadCount}:previous);
    } catch(e) {setError((e as Error).message)} finally {ids.forEach(id=>readPending.current.delete(id))}
  },[]);
  const load=useCallback(async (page=1,append=false)=>{
    if(pending.current)return;pending.current=true;setBusy(true);
    try {
      const response=await apiFetch('notifications?page='+page+'&pageSize=30');
      const result=await response.json();if(!response.ok)throw Error(result.error||'Unable to load notifications.');
      setData(previous=>append&&previous?{...result,items:[...previous.items,...result.items.filter((item:TenderNotification)=>!previous.items.some(n=>n.id===item.id))]}:result);setLoadedPage(result.page||page);setError('');
      if(openRef.current)await markRead(result.items);
    } catch(e){setError((e as Error).message)}finally{pending.current=false;setBusy(false)}
  },[markRead]);
  useEffect(()=>{
    void load();
    const refresh=()=>{if(document.visibilityState==='visible'&&!openRef.current)void load()};
    const timer=setInterval(refresh,60000);
    window.addEventListener('focus',refresh);window.addEventListener('tenders:notifications-changed',refresh);
    return()=>{clearInterval(timer);window.removeEventListener('focus',refresh);window.removeEventListener('tenders:notifications-changed',refresh)};
  },[load]);
  function changeOpen(value:boolean){openRef.current=value;setOpen(value);if(value){setKind('all');setLoadedPage(1);if(data)void markRead(data.items);void load()}}
  const items=(data?.items||[]).filter(n=>kind==='all'||(kind==='reminders'?n.kind.includes('reminder'):!n.kind.includes('reminder')));
  return <><button className="notification-btn unified-notification-btn" aria-label={`Notifications${data?.unreadCount?`, ${data.unreadCount} unread`:''}`} title="Notifications" onClick={()=>changeOpen(true)}><Bell size={20}/>{(data?.unreadCount||0)>0&&<span>{data!.unreadCount>99?'99+':data!.unreadCount}</span>}</button>
    <Sheet open={open} onOpenChange={changeOpen}><SheetContent className="notification-sheet"><SheetHeader><SheetTitle>Notifications</SheetTitle><SheetDescription>Opportunity updates, assignments and chase-up reminders. Notifications shown here are marked as read.</SheetDescription></SheetHeader>
      <div className="notification-filter" role="group" aria-label="Notification type">{[['all','All'],['opportunities','Opportunities'],['reminders','Reminders']].map(([value,label])=><button key={value} aria-pressed={kind===value} onClick={()=>setKind(value)}>{label}</button>)}</div>
      {error&&<div className="error-banner" role="alert">{error}<button onClick={()=>{if(data)void markRead(data.items);void load()}}>Retry</button></div>}
      <div className="notification-items" aria-busy={busy}>{items.map(n=><article key={n.id} className={'notification-item '+(!n.read?'is-unread':'')}>
        <div className="notification-symbol">{n.kind.includes('reminder')?<CalendarClock size={19}/>:<Bell size={18}/>}</div>
        <div className="notification-copy"><div><b>{n.title}</b>{!n.read&&<span className="notification-unread-dot" aria-label="Unread"/>}</div><p>{n.message}</p><time dateTime={n.createdAt}>{new Date(n.createdAt).toLocaleString('en-AU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}</time>
        {n.kind!=='deleted'&&(n.opportunityId||n.submissionId)&&<button className="text-btn" onClick={()=>{changeOpen(false);if(n.opportunityId)onOpenOpportunity(n.opportunityId);else if(n.submissionId)onOpenTender(n.submissionId)}}>{n.opportunityId?'View opportunity':'View reminder'}<ArrowUpRight size={14}/></button>}</div>
      </article>)}{!items.length&&!busy&&<div className="op-empty"><CheckCheck size={30}/><h3>You're all caught up</h3><p>{kind==='all'?'Your notifications will appear here.':'No notifications in this category.'}</p></div>}{busy&&!data&&<div className="op-loading" role="status"><RefreshCw className="op-spin" size={20}/>Loading notifications…</div>}</div>
      <div className="notification-footer">{data&&loadedPage*30<data.total?<button className="secondary-btn" disabled={busy} onClick={()=>load(loadedPage+1,true)}>{busy?'Loading…':'Load older notifications'}</button>:<button className="text-btn" disabled={busy} onClick={()=>load()}><RefreshCw size={14}/>{busy?'Refreshing…':'Refresh notifications'}</button>}</div>
    </SheetContent></Sheet></>;
}
