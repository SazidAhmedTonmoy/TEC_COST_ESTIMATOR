import {useCallback,useEffect,useRef,useState} from 'react';
import {ArrowUpRight,Bell,CalendarClock,CheckCheck,MessageSquare,RefreshCw,Search,X} from 'lucide-react';
import {Sheet,SheetContent,SheetHeader,SheetTitle,SheetDescription} from './ui/sheet';
import {apiFetch} from '../main';
import type {NotificationList,TenderNotification} from '@/lib/opportunity-types';

const categories=[['all','All'],['opportunities','Opportunities'],['chases','Chase-ups'],['reminders','Reminders']] as const;
type Category=typeof categories[number][0];
const PAGE_SIZE=30;

export function TenderNotifications({onOpenOpportunity,onOpenTender}:{onOpenOpportunity:(id:string)=>void;onOpenTender:(id:string,tab:'history'|'chase')=>void}) {
  const [open,setOpen]=useState(false), [data,setData]=useState<NotificationList|null>(null);
  const [error,setError]=useState(''), [busy,setBusy]=useState(false), [loadedPage,setLoadedPage]=useState(1);
  const [kind,setKind]=useState<Category>('all'), [query,setQuery]=useState('');
  const openRef=useRef(false), filters=useRef({kind:'all' as Category,q:''}), pageRef=useRef(1);
  const active=useRef<AbortController|null>(null), readPending=useRef(new Set<string>());
  const markRead=useCallback(async (items:TenderNotification[])=>{
    const ids=items.filter(n=>!n.read&&!readPending.current.has(n.id)).map(n=>n.id);
    if(!ids.length)return;
    ids.forEach(id=>readPending.current.add(id));
    try {
      const response=await apiFetch('notifications/read',{method:'POST',body:JSON.stringify({ids})});
      const result=await response.json();if(!response.ok)throw Error(result.error||'Unable to mark notifications as read.');
      setData(previous=>previous?{...previous,items:previous.items.map(n=>ids.includes(n.id)?{...n,read:true}:n),unreadCount:result.unreadCount}:previous);
    } catch(e) {if(openRef.current)setError((e as Error).message)} finally {ids.forEach(id=>readPending.current.delete(id))}
  },[]);
  const load=useCallback(async (page=1,append=false)=>{
    active.current?.abort();
    const controller=new AbortController();active.current=controller;setBusy(true);
    const {kind,q}=openRef.current?filters.current:{kind:'all',q:''};
    const params=new URLSearchParams({page:String(page),pageSize:String(PAGE_SIZE),kind,q});
    try {
      const response=await apiFetch('notifications?'+params.toString(),{signal:controller.signal});
      const result:NotificationList&{error?:string}=await response.json();
      if(!response.ok)throw Error(result.error||'Unable to load notifications.');
      if(controller.signal.aborted||active.current!==controller)return;
      setData(previous=>append&&previous?{...result,items:[...previous.items,...result.items.filter(item=>!previous.items.some(n=>n.id===item.id))]}:result);
      pageRef.current=result.page||page;setLoadedPage(pageRef.current);setError('');
      if(openRef.current)await markRead(result.items);
    } catch(e){if(!controller.signal.aborted&&active.current===controller)setError((e as Error).message)}
    finally{if(active.current===controller){active.current=null;setBusy(false)}}
  },[markRead]);
  useEffect(()=>{
    void load();
    const refresh=()=>{if(document.visibilityState==='visible'&&!active.current&&(!openRef.current||pageRef.current===1))void load()};
    const changed=()=>{if(document.visibilityState==='visible')void load()};
    const timer=setInterval(refresh,30000);
    window.addEventListener('focus',refresh);window.addEventListener('tenders:notifications-changed',changed);
    return()=>{clearInterval(timer);window.removeEventListener('focus',refresh);window.removeEventListener('tenders:notifications-changed',changed);active.current?.abort();active.current=null};
  },[load]);
  useEffect(()=>{
    if(!open)return;
    const timer=setTimeout(()=>void load(),query.trim()?250:0);
    return()=>clearTimeout(timer);
  },[open,query,kind,load]);
  function resetResults(){active.current?.abort();active.current=null;pageRef.current=1;setLoadedPage(1);setError('');setBusy(true);setData(previous=>previous?{...previous,items:[],total:0}:null)}
  function changeOpen(value:boolean){
    openRef.current=value;setOpen(value);
    if(value){filters.current={kind:'all',q:''};setKind('all');setQuery('');resetResults()}
    else {active.current?.abort();active.current=null;setBusy(false);void load()}
  }
  function changeQuery(value:string){if(value===query)return;filters.current={...filters.current,q:value};setQuery(value);resetResults()}
  function changeKind(value:Category){if(value===kind)return;filters.current={...filters.current,kind:value};setKind(value);resetResults()}
  const items=data?.items||[];
  return <><button className="notification-btn unified-notification-btn" aria-label={`Notifications${data?.unreadCount?`, ${data.unreadCount} unread`:''}`} title="Notifications" onClick={()=>changeOpen(true)}><Bell size={20}/>{(data?.unreadCount||0)>0&&<span>{data!.unreadCount>99?'99+':data!.unreadCount}</span>}</button>
    <Sheet open={open} onOpenChange={changeOpen}><SheetContent className="notification-sheet"><SheetHeader><SheetTitle>Notifications</SheetTitle><SheetDescription>Opportunity updates, recorded chase-ups and reminders. Displayed notifications are marked as read.</SheetDescription></SheetHeader>
      <div className="notification-search"><Search size={17} aria-hidden="true"/><input type="search" aria-label="Search notifications by user name, project or message" placeholder="Search user, project or message…" value={query} maxLength={200} onChange={e=>changeQuery(e.target.value)}/>{query&&<button type="button" aria-label="Clear notification search" title="Clear search" onClick={()=>changeQuery('')}><X size={16}/></button>}</div>
      <div className="notification-filter" role="group" aria-label="Notification type">{categories.map(([value,label])=><button key={value} aria-pressed={kind===value} onClick={()=>changeKind(value)}>{label}</button>)}</div>
      {query.trim()&&!busy&&!error&&<div className="notification-result-count" role="status">{data?.total||0} matching notification{data?.total===1?'':'s'}</div>}
      {error&&<div className="error-banner" role="alert">{error}<button onClick={()=>void load()}>Retry</button></div>}
      <div className="notification-items" aria-busy={busy}>{items.map(n=><article key={n.id} className={'notification-item '+(!n.read?'is-unread':'')}>
        <div className="notification-symbol">{n.kind==='reminder'?<CalendarClock size={19}/>:n.kind==='chase-recorded'?<MessageSquare size={18}/>:<Bell size={18}/>}</div>
        <div className="notification-copy"><div><b>{n.title}</b>{!n.read&&<span className="notification-unread-dot" aria-label="Unread"/>}</div><p>{n.message}</p><time dateTime={n.createdAt}>{new Date(n.createdAt).toLocaleString('en-AU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}</time>
        {n.kind!=='deleted'&&(n.opportunityId||n.submissionId)&&<button className="text-btn" onClick={()=>{changeOpen(false);if(n.opportunityId)onOpenOpportunity(n.opportunityId);else if(n.submissionId)onOpenTender(n.submissionId,n.kind==='chase-recorded'?'history':'chase')}}>{n.opportunityId?'View opportunity':n.kind==='chase-recorded'?'View chase-up':'View reminder'}<ArrowUpRight size={14}/></button>}</div>
      </article>)}{!items.length&&!busy&&!error&&<div className="op-empty">{query.trim()?<Search size={30}/>:<CheckCheck size={30}/>}<h3>{query.trim()?'No matching notifications':"You're all caught up"}</h3><p>{query.trim()?'Try a different user name or project.':kind==='all'?'Your notifications will appear here.':'No notifications in this category.'}</p></div>}{busy&&!items.length&&<div className="op-loading" role="status"><RefreshCw className="op-spin" size={20}/>Loading notifications…</div>}</div>
      <div className="notification-footer">{data&&loadedPage*PAGE_SIZE<data.total?<button className="secondary-btn" disabled={busy} onClick={()=>void load(loadedPage+1,true)}>{busy?'Loading…':'Load older notifications'}</button>:<button className="text-btn" disabled={busy} onClick={()=>void load()}><RefreshCw size={14}/>{busy?'Refreshing…':'Refresh notifications'}</button>}</div>
    </SheetContent></Sheet></>;
}
