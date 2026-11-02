'use client';
import {useCallback,useEffect,useState} from 'react';
import {ArrowUpRight,BellRing,CalendarClock,ClipboardCheck,FileClock,RefreshCw,Users} from 'lucide-react';
import {apiFetch} from '../main';

type Scope='mine'|'team';
type Action={kind:'opportunity'|'chase';id:string;title:string;project:string;status:string;due:string;daysLeft?:number|null;detail?:string};
type Data={scope:Scope;scopeLabel:string;teamAvailable:boolean;counts:{needsApproval:number;needsQuote:number;dueSoon:number;followUpsDue:number};actions:Action[];actionCount:number;asOf:string};
const metrics=[
 {key:'needsApproval',label:'Needs my approval',icon:ClipboardCheck},
 {key:'needsQuote',label:'Approved, not quoted',icon:FileClock},
 {key:'dueSoon',label:'Deadlines within 3 days',icon:CalendarClock},
 {key:'followUpsDue',label:'Follow-ups due',icon:BellRing},
] as const;

export function MyWorkDashboard({onOpenOpportunity,onOpenChase}:{onOpenOpportunity:(id:string)=>void;onOpenChase:(id:string)=>void}){
 const [scope,setScope]=useState<Scope>('mine');
 const [data,setData]=useState<Data|null>(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const load=useCallback(async(signal?:AbortSignal)=>{
  setLoading(true);setError('');
  try{
   const response=await apiFetch('opportunities/my-work?scope='+scope,{signal});
   const result=await response.json() as Data & {error?:string};
   if(!response.ok)throw Error(result.error||'Unable to load your work');
   if(!signal?.aborted)setData(result);
  }catch(exc){if(!signal?.aborted)setError(exc instanceof Error?exc.message:'Unable to load My Work');}
  finally{if(!signal?.aborted)setLoading(false)}
 },[scope]);
 useEffect(()=>{
  const controller=new AbortController();
  void load(controller.signal);
  const visible=()=>{if(document.visibilityState==='visible')void load(controller.signal)};
  const interval=window.setInterval(visible,120000);
  window.addEventListener('focus',visible);
  return()=>{controller.abort();window.clearInterval(interval);window.removeEventListener('focus',visible)};
 },[load]);
 return <section className="my-work-section" aria-label="My Work dashboard">
   <div className="my-work-heading">
    <div><span className="my-work-eyebrow">PERSONAL ACTION CENTRE</span><h2>My Work</h2><p>What needs attention next · based on your saved responsibilities</p></div>
    <div className="my-work-switch" role="group" aria-label="Work scope">
     <button className={scope==='mine'?'is-active':''} aria-pressed={scope==='mine'} onClick={()=>{setData(null);setScope('mine')}}>My work</button>
     <button className={scope==='team'?'is-active':''} aria-pressed={scope==='team'} onClick={()=>{setData(null);setScope('team')}} disabled={data!==null&&!data.teamAvailable}>{data?.scopeLabel==='All teams'?'All teams':'My team'} <Users size={14}/></button>
     <button className="my-work-refresh" aria-label="Refresh My Work" title="Refresh" onClick={()=>void load()}><RefreshCw size={16}/></button>
    </div>
   </div>
   {error&&<div className="my-work-error" role="alert">{error}<button onClick={()=>void load()}>Retry</button></div>}
   <div className="my-work-metrics">
    {metrics.map(({key,label,icon:Icon})=><div className="my-work-metric" key={key}>
     <div className="my-work-metric-title"><span>{scope==='team'&&key==='needsApproval'?'Needs team approval':label}</span><Icon size={18}/></div>
     <strong>{loading&&!data?'—':data?.counts[key]??'—'}</strong>
    </div>)}
   </div>
   <div className="my-work-actions-heading"><h3>Next actions</h3><span>{data?.actionCount??0} tasks · {scope==='team'?data?.scopeLabel||'Team view':'Assigned to you'}</span></div>
   {loading&&!data?<p className="my-work-empty" role="status">Loading your work…</p>:
    !data?.actions.length?<p className="my-work-empty">You're up to date. There are no actionable items in this view.</p>:
    <div className="my-work-action-list">{data.actions.map((item,i)=><div className="my-work-action" key={item.kind+':'+item.id+':'+i}>
      <div className="my-work-action-copy"><span className={'my-work-action-status '+(item.kind==='chase'||item.daysLeft!=null&&item.daysLeft<=3?'is-urgent':'')}>{item.title}</span>
       <strong title={item.project}>{item.project}</strong>
       <small>{item.kind==='chase'?item.detail||'Scheduled follow-up':item.status==='approved'?'Approved · quote required':item.status==='review'?'In Review · decision pending':'Awaiting approval'}{item.due?' · '+item.due.slice(0,10):''}</small>
      </div>
      <button className="my-work-action-open" type="button" onClick={()=>item.kind==='chase'?onOpenChase(item.id):onOpenOpportunity(item.id)}>{item.kind==='chase'?'Open Chase-up':'View opportunity'}<ArrowUpRight size={15}/></button>
     </div>)}</div>}
   </section>;
}
