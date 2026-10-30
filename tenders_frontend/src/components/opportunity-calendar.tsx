import {useEffect,useMemo,useState} from 'react';
import {CalendarDays,ChevronLeft,ChevronRight,RefreshCw} from 'lucide-react';
import {apiFetch} from '../main';

type CalendarOpportunity={id:string;project:string;due:string;region:string;builders:string[];quoted:boolean};
type CalendarResponse={month:string;items:CalendarOpportunity[];total:number;quoted:number};
const label=(date:string)=>new Date(date+'T12:00:00').toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'});

export function ApprovedOpportunityCalendar({month,setMonth,onOpen}:{month:string;setMonth:(month:string)=>void;onOpen:(id:string)=>void}){
  const [data,setData]=useState<CalendarResponse|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[day,setDay]=useState('');
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('');setDay('');
    apiFetch('opportunities/calendar?'+new URLSearchParams({month}),{signal:controller.signal})
      .then(async response=>{const result=await response.json();if(!response.ok)throw Error(result.error||'Calendar unavailable');return result as CalendarResponse})
      .then(result=>{if(!controller.signal.aborted)setData(result)})
      .catch(error=>{if(!controller.signal.aborted)setError((error as Error).message)})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false)});
    return()=>controller.abort();
  },[month]);
  const [year,part]=month.split('-').map(Number);
  const first=new Date(Date.UTC(year,part-1,1));
  const days=new Date(Date.UTC(year,part,0)).getUTCDate();
  const offset=(first.getUTCDay()+6)%7;
  const rows=useMemo(()=>data?.items||[],[data]);
  const byDay=useMemo(()=>{
    const map=new Map<string,CalendarOpportunity[]>();
    for(const item of rows){if(!map.has(item.due))map.set(item.due,[]);map.get(item.due)!.push(item)}
    return map;
  },[rows]);
  function shift(n:number){const date=new Date(Date.UTC(year,part-1+n,1));setMonth(date.toISOString().slice(0,7))}
  const agenda=day?byDay.get(day)||[]:rows;
  return <section className="approved-calendar" aria-label="Approved opportunity deadlines">
    <div className="calendar-toolbar"><div>
      <button className="icon-btn" aria-label="Previous month" onClick={()=>shift(-1)}><ChevronLeft size={19}/></button>
      <h2>{first.toLocaleDateString('en-AU',{timeZone:'UTC',month:'long',year:'numeric'})}</h2>
      <button className="icon-btn" aria-label="Next month" onClick={()=>shift(1)}><ChevronRight size={19}/></button>
      <button className="secondary-btn" onClick={()=>{const parts=new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit'}).formatToParts(new Date());setMonth((parts.find(part=>part.type==='year')?.value||'2026')+'-'+(parts.find(part=>part.type==='month')?.value||'01'))}}>Today</button>
      <input type="month" aria-label="Choose opportunity month" value={month} onChange={e=>{if(e.target.value)setMonth(e.target.value)}}/>
    </div></div>
    <div className="calendar-legend"><span><i className="legend-dot" style={{background:'#d2a512'}}/>Needs quote</span><span><i className="legend-dot" style={{background:'#18a785'}}/>Quoted / linked</span><span>{rows.length} approved deadlines this month</span></div>
    <div className="calendar-summary"><div><span>Approved deadlines</span><strong>{rows.length}</strong></div><div><span>Need to quote</span><strong>{rows.filter(item=>!item.quoted).length}</strong></div><div><span>Already quoted</span><strong>{rows.filter(item=>item.quoted).length}</strong></div><div><span>Builders represented</span><strong>{new Set(rows.flatMap(item=>item.builders)).size}</strong></div></div>
    {error&&<div role="alert" className="error-banner">{error}</div>}
    {loading&&<p role="status" className="calendar-help"><RefreshCw size={15}/> Loading approved opportunities…</p>}
    <section className="panel calendar-panel"><div className="calendar-grid week-labels">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(text=><span key={text}>{text}</span>)}</div>
    <div className="calendar-grid">{Array.from({length:Math.ceil((offset+days)/7)*7},(_,i)=>{
      const number=i-offset+1;if(number<1||number>days)return <div key={i} className="calendar-day outside"/>;
      const date=month+'-'+String(number).padStart(2,'0'),events=byDay.get(date)||[];
      return <div key={date} className={'calendar-day'+(day===date?' is-selected':'')}><button className="day-number" onClick={()=>setDay(day===date?'':date)}>{number}</button>{events.slice(0,3).map(event=><button key={event.id} className={'calendar-event opportunity-calendar-event '+(event.quoted?'is-quoted':'needs-quote')} title={event.project} onClick={()=>onOpen(event.id)}><span>{event.project}</span></button>)}{events.length>3&&<button className="more-events" onClick={()=>setDay(date)}>+{events.length-3} more</button>}</div>;
    })}</div></section>
    <section className="panel agenda"><div className="panel-heading"><h2>{day?label(day):'Approved deadline agenda'}</h2>{day&&<button className="text-btn" onClick={()=>setDay('')}>Show full month</button>}</div>{agenda.map(item=><div key={item.id} className="agenda-row"><div className="agenda-date">{label(item.due)}</div><span className={'calendar-quote-state '+(item.quoted?'is-quoted':'needs-quote')}>{item.quoted?'Quoted':'Need quote'}</span><button className="project-name" onClick={()=>onOpen(item.id)}>{item.project}<span className="sub-line">{item.builders.join(' · ')||'Builder not specified'} · {item.region}</span></button></div>)}{!agenda.length&&<div className="empty-state"><CalendarDays/><h3>No approved opportunities for this period</h3><p>Choose another month or switch to the Chase-up calendar.</p></div>}</section>
  </section>;
}
