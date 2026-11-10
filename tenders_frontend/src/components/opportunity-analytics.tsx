import {useEffect,useMemo,useState} from 'react';
import {BarChart3,CalendarDays,RefreshCw,Users} from 'lucide-react';
import {apiFetch} from '../main';

type Metric='added'|'approved'|'quoted';
type Contributor={id:number|null;name:string;count:number};
type Stats={mode:string;from:string;to:string;timezone:string;counts:Record<Metric,number>;contributors:Record<Metric,Contributor[]>;monthly:Array<{month:string}&Record<Metric,number>>};
const metrics:Metric[]=['added','approved','quoted'];
const titles:Record<Metric,string>={added:'Opportunities added',approved:'Approved',quoted:'Quoted'};
const colors=['#17ad9c','#e5a828','#638de8','#aa75d8','#ef7676','#65bc71','#e88738','#40adc0','#879bac','#c59acb'];
function currentSydneyDate(){
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
 const part=(type:string)=>parts.find(p=>p.type===type)?.value||'';
 return `${part('year')}-${part('month')}-${part('day')}`;
}
function Pie({label,metric,total,contributors}:{label:string;metric:Metric;total:number;contributors:Contributor[]}){
 const top=contributors.slice(0,9),others=contributors.slice(9).reduce((a,c)=>a+c.count,0);
 const pieces=others?[...top,{id:null,name:'Other contributors',count:others}]:top;
 let from=0;
 const gradient=pieces.map((item,index)=>{
  const start=from;from+=item.count/Math.max(total,1)*100;
  return `${colors[index%colors.length]} ${start}% ${from}%`;
 }).join(',');
 return <section className="op-analytics-card" aria-label={label}>
  <h4>{label}</h4>
  <div className="op-analytics-pie-body">
   <div className="op-analytics-donut" role="img" aria-label={`${label}: ${total} opportunities, by person`}
    style={{background:pieces.length?`conic-gradient(${gradient})`:'conic-gradient(#536372 0% 100%)'}}>
    <div><strong>{total}</strong><span>{metric}</span></div>
   </div>
   <div className="op-analytics-legend">
    {pieces.map((person,i)=><div className="op-analytics-legend-line" key={`${person.id}:${person.name}`} title={person.name}>
     <span className="op-analytics-legend-dot" style={{background:colors[i%colors.length]}}/>
     <span>{person.name}</span><strong>{person.count}</strong>
    </div>)}
    {!pieces.length&&<p className="op-analytics-empty">No activity in this period</p>}
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
 const people=useMemo(()=>{
  const all=new Map<string,{name:string,added:number,approved:number,quoted:number}>();
  for(const metric of metrics)for(const person of data?.contributors[metric]||[]){
   const key=person.id===null?'name:'+person.name:'id:'+person.id;
   const row=all.get(key)||{name:person.name,added:0,approved:0,quoted:0};
   row[metric]+=person.count;all.set(key,row);
  }
  return [...all.values()].sort((a,b)=>b.added+b.approved+b.quoted-(a.added+a.approved+a.quoted)||a.name.localeCompare(b.name));
 },[data]);
 const maxMonth=Math.max(1,...(data?.monthly||[]).flatMap(m=>metrics.map(k=>m[k])));
 const months=data?.monthly||[];
 return <div className="op-analytics" aria-label="Opportunity contribution analytics">
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
  {data&&<>
   <div className="op-analytics-period"><CalendarDays size={16}/><strong>{data.from} — {data.to}</strong><span>Australia/Sydney dates{loading?' · Refreshing…':''}</span></div>
   <div className="op-analytics-summary">{metrics.map(metric=><div key={metric}><span>{titles[metric]}</span><strong>{data.counts[metric]}</strong></div>)}</div>
   <div className="op-analytics-pies">{metrics.map(metric=><Pie key={metric} label={titles[metric]} metric={metric} total={data.counts[metric]} contributors={data.contributors[metric]}/>)}</div>
   <section className="op-analytics-table-panel"><h3><Users size={18}/> Contributor breakdown</h3><div className="op-analytics-table-scroll"><table><thead><tr><th>Person</th><th>Added</th><th>Approved</th><th>Quoted</th></tr></thead><tbody>{people.map(row=><tr key={row.name}><th scope="row">{row.name}</th><td>{row.added}</td><td>{row.approved}</td><td>{row.quoted}</td></tr>)}{!people.length&&<tr><td colSpan={4}>No recorded activity in this period.</td></tr>}</tbody></table></div></section>
   <section className="op-analytics-table-panel"><h3><BarChart3 size={18}/> Monthly activity</h3><div className="op-analytics-trend-legend"><span>Added</span><span>Approved</span><span>Quoted</span></div><div className="op-analytics-trend">{months.map(row=><div key={row.month} className="op-analytics-trend-row"><time>{row.month}</time><div className="op-analytics-bars">{metrics.map((key,index)=><div key={key} className="op-analytics-bar-track" title={`${titles[key]}: ${row[key]}`}><div style={{width:`${row[key]/maxMonth*100}%`,background:colors[index]}}/></div>)}</div><strong>{row.added} / {row.approved} / {row.quoted}</strong></div>)}</div></section>
  </>}
 </div>;
}
