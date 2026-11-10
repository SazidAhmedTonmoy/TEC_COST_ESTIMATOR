import {useEffect,useMemo,useState} from 'react';
import {BarChart3,CalendarDays,RefreshCw,Users} from 'lucide-react';
import {apiFetch} from '../main';

type OutcomeKey='added'|'approved'|'approvedNotQuoted'|'approvedQuoted'|'rejected'|'expired'|'pending'|'review';
type OutcomeCounts=Record<OutcomeKey,number>;
type Creator=OutcomeCounts&{id:number|null;name:string};
type Month=OutcomeCounts&{month:string};
type Stats={mode:string;from:string;to:string;timezone:string;outcomes:OutcomeCounts;creators:Creator[];monthlyOutcomes:Month[]};
type Slice={name:string;count:number;color:string};
const creatorColors=['#17ad9c','#e5a828','#638de8','#aa75d8','#ef7676','#65bc71','#e88738','#40adc0','#879bac','#c59acb'];
const outcomeColors={approvedQuoted:'#16b19e',approvedNotQuoted:'#e7a735',rejected:'#e47574',expired:'#879bac',pending:'#638de8',review:'#aa75d8'};
function currentSydneyDate(){
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
 const part=(type:string)=>parts.find(p=>p.type===type)?.value||'';
 return `${part('year')}-${part('month')}-${part('day')}`;
}
function Donut({title,total,centerLabel,slices}:{title:string;total:number;centerLabel:string;slices:Slice[]}){
 const present=slices.filter(slice=>slice.count>0);
 let from=0;
 const gradient=present.map(slice=>{
  const first=from;from+=slice.count/Math.max(total,1)*100;
  return `${slice.color} ${first}% ${from}%`;
 }).join(',');
 return <section className="op-analytics-card" aria-label={title}>
  <h4>{title}</h4>
  <div className="op-analytics-pie-body">
   <div className="op-analytics-donut" role="img" aria-label={`${title}: ${total}`}
    style={{background:present.length?`conic-gradient(${gradient})`:'conic-gradient(#536372 0% 100%)'}}>
    <div><strong>{total}</strong><span>{centerLabel}</span></div>
   </div>
   <div className="op-analytics-legend">
    {slices.map((slice,i)=><div className="op-analytics-legend-line" key={`${slice.name}:${i}`}>
     <span className="op-analytics-legend-dot" style={{background:slice.color}}/>
     <span title={slice.name}>{slice.name}</span><strong>{slice.count}</strong>
    </div>)}
    {!slices.length&&<p className="op-analytics-empty">No activity in this period</p>}
   </div>
  </div>
 </section>;
}
export default function OpportunityAnalytics(){
 const today=useMemo(currentSydneyDate,[]);
 const [mode,setMode]=useState<'month'|'year'|'custom'>('month');
 const [month,setMonth]=useState(today.slice(0,7));
 const [year,setYear]=useState(today.slice(0,4));
 const [from,setFrom]=useState(today.slice(0,7)+'-01');
 const [to,setTo]=useState(today);
 const [data,setData]=useState<Stats|null>(null);
 const [error,setError]=useState('');
 const [loading,setLoading]=useState(true);
 const [refresh,setRefresh]=useState(0);
 const canQuery=mode!=='custom'||(!!from&&!!to&&to>=from);
 useEffect(()=>{
  if(!canQuery){setError('End date must be on or after the start date.');setLoading(false);return;}
  const controller=new AbortController();setLoading(true);setError('');
  const params=new URLSearchParams({mode});
  if(mode==='month')params.set('month',month);
  else if(mode==='year')params.set('year',year);
  else{params.set('from',from);params.set('to',to)}
  const load=async()=>{
   try{
    const response=await apiFetch('opportunities/analytics?'+params.toString(),{signal:controller.signal});
    const responseData=await response.json();
    if(!response.ok)throw new Error(responseData.error||'Analytics could not be loaded.');
    if(!controller.signal.aborted)setData(responseData);
   }catch(e){if(!controller.signal.aborted)setError((e as Error).message)}
   finally{if(!controller.signal.aborted)setLoading(false)}
  };
  void load();return()=>controller.abort();
 },[mode,month,year,from,to,refresh,canQuery]);
 const outcome=data?.outcomes;
 const people=data?.creators||[];
 const addedSlices=useMemo(()=>{
  const top=people.slice(0,9).map((person,i)=>({name:person.name,count:person.added,color:creatorColors[i%creatorColors.length]}));
  const other=people.slice(9).reduce((total,person)=>total+person.added,0);
  return other?[...top,{name:'Other creators',count:other,color:creatorColors[9]}]:top;
 },[people]);
 const outcomeSlices:Slice[]=outcome?[
  {name:'Approved · quoted',count:outcome.approvedQuoted,color:outcomeColors.approvedQuoted},
  {name:'Approved · not quoted',count:outcome.approvedNotQuoted,color:outcomeColors.approvedNotQuoted},
  {name:'Rejected',count:outcome.rejected,color:outcomeColors.rejected},
  {name:'Expired',count:outcome.expired,color:outcomeColors.expired},
  {name:'Awaiting approval',count:outcome.pending,color:outcomeColors.pending},
  {name:'In review',count:outcome.review,color:outcomeColors.review},
 ]:[];
 const approvalSlices:Slice[]=outcome?[
  {name:'Approved · quoted',count:outcome.approvedQuoted,color:outcomeColors.approvedQuoted},
  {name:'Approved · not quoted',count:outcome.approvedNotQuoted,color:outcomeColors.approvedNotQuoted},
 ]:[];
 return <div className="op-analytics" aria-label="Opportunity outcome analytics">
  <div className="op-analytics-filters">
   <div className="op-analytics-modes" role="group" aria-label="Analytics period">
    <button type="button" aria-pressed={mode==='month'} onClick={()=>setMode('month')}>Month</button>
    <button type="button" aria-pressed={mode==='year'} onClick={()=>setMode('year')}>Month by month</button>
    <button type="button" aria-pressed={mode==='custom'} onClick={()=>setMode('custom')}>Custom range</button>
   </div>
   <div className="op-analytics-dates">
    {mode==='month'&&<label>Month<input type="month" aria-label="Analytics month" value={month} onChange={e=>setMonth(e.target.value)}/></label>}
    {mode==='year'&&<label>Year<input type="number" min="2000" max="2100" aria-label="Analytics year" value={year} onChange={e=>setYear(e.target.value)}/></label>}
    {mode==='custom'&&<><label>From<input type="date" aria-label="Analytics start date" value={from} onChange={e=>setFrom(e.target.value)}/></label><label>To<input type="date" min={from} aria-label="Analytics end date" value={to} onChange={e=>setTo(e.target.value)}/></label></>}
    <button type="button" className="secondary-btn" aria-label="Refresh analytics" onClick={()=>setRefresh(n=>n+1)}><RefreshCw size={16}/>{loading?'Loading…':'Refresh'}</button>
   </div>
  </div>
  {error&&<div className="op-refresh-warning" role="alert">{data?'Showing the last loaded analytics. ':''}{error}<button onClick={()=>setRefresh(n=>n+1)}>Retry</button></div>}
  {!data&&loading&&<div className="op-loading" role="status"><RefreshCw size={19} className="op-spin"/>Loading analytics…</div>}
  {data&&outcome&&<>
   <div className="op-analytics-period"><CalendarDays size={16}/><strong>{data.from} — {data.to}</strong><span>{loading?'Refreshing…':'Current outcomes of opportunities added in this period'}</span></div>
   <div className="op-analytics-pies">
    <Donut title="Opportunities added" total={outcome.added} centerLabel="added" slices={addedSlices}/>
    <Donut title="Opportunity outcomes" total={outcome.added} centerLabel="opportunities" slices={outcomeSlices}/>
    <Donut title="Approved opportunities" total={outcome.approved} centerLabel="approved" slices={approvalSlices}/>
   </div>
   <section className="op-analytics-table-panel"><h3><Users size={18}/> Outcomes by person who added the opportunity</h3><div className="op-analytics-table-scroll"><table><thead><tr><th>Person</th><th>Added</th><th>Approved</th><th>Approved, not quoted</th><th>Quoted</th><th>Rejected</th><th>Expired</th></tr></thead><tbody>{people.map(row=><tr key={`${row.id}:${row.name}`}><th scope="row">{row.name}</th><td>{row.added}</td><td>{row.approved}</td><td>{row.approvedNotQuoted}</td><td>{row.approvedQuoted}</td><td>{row.rejected}</td><td>{row.expired}</td></tr>)}{!people.length&&<tr><td colSpan={7}>No opportunities added in this period.</td></tr>}</tbody></table></div></section>
   <section className="op-analytics-table-panel"><h3><BarChart3 size={18}/> Month-by-month outcomes</h3><div className="op-analytics-table-scroll"><table><thead><tr><th>Month added</th><th>Added</th><th>Approved</th><th>Approved, not quoted</th><th>Quoted</th><th>Rejected</th><th>Expired</th></tr></thead><tbody>{data.monthlyOutcomes.map(row=><tr key={row.month}><th scope="row">{row.month}</th><td>{row.added}</td><td>{row.approved}</td><td>{row.approvedNotQuoted}</td><td>{row.approvedQuoted}</td><td>{row.rejected}</td><td>{row.expired}</td></tr>)}</tbody></table></div></section>
  </>}
 </div>;
}
