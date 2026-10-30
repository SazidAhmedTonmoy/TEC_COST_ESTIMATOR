import {useEffect,useMemo,useState} from 'react';
import type {CSSProperties} from 'react';
import {CalendarDays,ChevronLeft,ChevronRight,RefreshCw,Clock} from 'lucide-react';
import {apiFetch} from '../main';
import {calendarTeamAppearance,teamCalendarColor,calendarTeamPalette} from '../lib/calendar-team-colors';

type CalendarOpportunity={id:string;project:string;due:string;region:string;builders:string[];quoted:boolean;assignedTeamIds:number[]};
type CalendarResponse={month:string;items:CalendarOpportunity[];total:number;quoted:number;teams:{id:number;name:string}[]};
const label=(date:string)=>new Date(date+'T12:00:00').toLocaleDateString('en-AU',{weekday:'short',day:'numeric',month:'short',year:'numeric'});
const sydDate=()=>{const parts=new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());const get=(key:string)=>parts.find(p=>p.type===key)?.value||'';return `${get('year')}-${get('month')}-${get('day')}`};
const plusDate=(iso:string,n:number)=>{const d=new Date(iso+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)};
const monthsInRange=(first:string,last:string)=>{const result:string[]=[];let cursor=first.slice(0,7);while(cursor<=last.slice(0,7)&&result.length<3){result.push(cursor);const d=new Date(cursor+'-01T12:00:00Z');d.setUTCMonth(d.getUTCMonth()+1);cursor=d.toISOString().slice(0,7)}return result};

export function ApprovedOpportunityCalendar({month,setMonth,onOpen}:{month:string;setMonth:(month:string)=>void;onOpen:(id:string)=>void}){
  const [data,setData]=useState<CalendarResponse|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[day,setDay]=useState('');
  const [displayMode,setDisplayMode]=useState<'month'|'agenda'>('month'),[agendaDays,setAgendaDays]=useState<7|30>(7);
  const [agendaData,setAgendaData]=useState<CalendarOpportunity[]>([]),[agendaLoading,setAgendaLoading]=useState(false),[agendaError,setAgendaError]=useState('');
  const today=sydDate(),end=plusDate(today,agendaDays-1);
  useEffect(()=>{
    if(displayMode!=='agenda')return;
    const controller=new AbortController();setAgendaLoading(true);setAgendaError('');setAgendaData([]);
    Promise.all(monthsInRange(today,end).map(async m=>{
      const response=await apiFetch('opportunities/calendar?'+new URLSearchParams({month:m}),{signal:controller.signal});
      const result=await response.json();if(!response.ok)throw Error(result.error||'Agenda unavailable');return result as CalendarResponse;
    })).then(months=>{if(!controller.signal.aborted){const seen=new Set<string>();setAgendaData(months.flatMap(m=>m.items).filter(item=>item.due>=today&&item.due<=end).filter(item=>{if(seen.has(item.id))return false;seen.add(item.id);return true}).sort((a,b)=>a.due.localeCompare(b.due)||a.project.localeCompare(b.project)))}})
    .catch(e=>{if(!controller.signal.aborted)setAgendaError((e as Error).message)}).finally(()=>{if(!controller.signal.aborted)setAgendaLoading(false)});
    return()=>controller.abort();
  },[displayMode,agendaDays,today,end]);
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
  const visibleRows=displayMode==='agenda'?agendaData:rows;
  // Use the complete team directory, ordered by immutable ID, to keep a team's
  // colour stable when the user changes months or views a different deadline.
  const teams=useMemo(()=>data?.teams||[],[data]);
  const palette=useMemo(()=>calendarTeamPalette(teams),[teams]);
  const needsQuoteTeams=useMemo(()=>{
    const used=new Set(visibleRows.filter(item=>!item.quoted).map(item=>calendarTeamAppearance(item.assignedTeamIds,teams,palette).key));
    const present=teams.filter(team=>used.has(String(team.id))).map(team=>({key:String(team.id),name:team.name,color:teamCalendarColor(team.id,palette)}));
    if(used.has('unassigned'))present.push({key:'unassigned',name:'Unassigned',color:teamCalendarColor(null,palette)});
    return present;
  },[visibleRows,teams,palette]);
  function needsQuoteAppearance(event:CalendarOpportunity){
    const appearance=calendarTeamAppearance(event.assignedTeamIds,teams,palette);
    const color=appearance.color;
    const style={
      '--team-calendar-bg':color.lightBg,'--team-calendar-fg':color.lightFg,
      '--team-calendar-dark-bg':color.darkBg,'--team-calendar-dark-fg':color.darkFg,
      '--team-calendar-accent':color.accent,
    } as CSSProperties;
    return {...appearance,style};
  }
  const byDay=useMemo(()=>{
    const map=new Map<string,CalendarOpportunity[]>();
    for(const item of rows){if(!map.has(item.due))map.set(item.due,[]);map.get(item.due)!.push(item)}
    return map;
  },[rows]);
  function shift(n:number){const date=new Date(Date.UTC(year,part-1+n,1));setMonth(date.toISOString().slice(0,7))}
  const agenda=day?byDay.get(day)||[]:rows;
  const agendaGroups=agendaData.reduce<Record<string,CalendarOpportunity[]>>((groups,item)=>{(groups[item.due]??=[]).push(item);return groups},{})
  const dueInDays=(date:string)=>Math.round((Date.parse(date+'T12:00:00Z')-Date.parse(today+'T12:00:00Z'))/86400000);
  return <section className="approved-calendar" aria-label="Approved opportunity deadlines">
    <div className="calendar-display-switch" role="group" aria-label="Approved opportunity calendar layout">
      <button type="button" className="secondary-btn" aria-pressed={displayMode==='month'} onClick={()=>setDisplayMode('month')}><CalendarDays size={16}/>Month</button>
      <button type="button" className="secondary-btn" aria-pressed={displayMode==='agenda'} onClick={()=>setDisplayMode('agenda')}><Clock size={16}/>Agenda</button>
      {displayMode==='agenda'&&<div className="agenda-range" role="group" aria-label="Agenda timeframe"><button className="secondary-btn" aria-pressed={agendaDays===7} onClick={()=>setAgendaDays(7)}>Next 7 days</button><button className="secondary-btn" aria-pressed={agendaDays===30} onClick={()=>setAgendaDays(30)}>Next 30 days</button></div>}
    </div>
    {displayMode==='month'&&<div className="calendar-toolbar"><div>
      <button className="icon-btn" aria-label="Previous month" onClick={()=>shift(-1)}><ChevronLeft size={19}/></button>
      <h2>{first.toLocaleDateString('en-AU',{timeZone:'UTC',month:'long',year:'numeric'})}</h2>
      <button className="icon-btn" aria-label="Next month" onClick={()=>shift(1)}><ChevronRight size={19}/></button>
      <button className="secondary-btn" onClick={()=>{const parts=new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit'}).formatToParts(new Date());setMonth((parts.find(part=>part.type==='year')?.value||'2026')+'-'+(parts.find(part=>part.type==='month')?.value||'01'))}}>Today</button>
      <input type="month" aria-label="Choose opportunity month" value={month} onChange={e=>{if(e.target.value)setMonth(e.target.value)}}/>
    </div></div>}
    <div className="calendar-legend team-calendar-legend" aria-label="Calendar team colours">
      {needsQuoteTeams.map(team=><span key={team.key} title={'Needs quote · '+team.name}><i className="legend-dot" style={{background:team.color.accent}}/>Needs quote · {team.name}</span>)}
      <span><i className="legend-dot" style={{background:'#18a785'}}/>Quoted / linked</span>
      <span>{visibleRows.length} approved deadlines {displayMode==='month'?'this month':`in the next ${agendaDays} days`}</span>
    </div>
    <div className="calendar-summary"><div><span>Approved deadlines</span><strong>{visibleRows.length}</strong></div><div><span>Need to quote</span><strong>{visibleRows.filter(item=>!item.quoted).length}</strong></div><div><span>Already quoted</span><strong>{visibleRows.filter(item=>item.quoted).length}</strong></div><div><span>Builders represented</span><strong>{new Set(visibleRows.flatMap(item=>item.builders)).size}</strong></div></div>
    {error&&<div role="alert" className="error-banner">{error}</div>}
    {(displayMode==='month'?loading:agendaLoading)&&<p role="status" className="calendar-help"><RefreshCw size={15}/> Loading approved opportunities…</p>}
    {agendaError&&displayMode==='agenda'&&<div role="alert" className="error-banner">{agendaError}</div>}
    {displayMode==='month'&&<><section className="panel calendar-panel"><div className="calendar-grid week-labels">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(text=><span key={text}>{text}</span>)}</div>
    <div className="calendar-grid">{Array.from({length:Math.ceil((offset+days)/7)*7},(_,i)=>{
      const number=i-offset+1;if(number<1||number>days)return <div key={i} className="calendar-day outside"/>;
      const date=month+'-'+String(number).padStart(2,'0'),events=byDay.get(date)||[];
      return <div key={date} className={'calendar-day'+(day===date?' is-selected':'')}><button className="day-number" onClick={()=>setDay(day===date?'':date)}>{number}</button>{events.slice(0,3).map(event=>{
        const appearance=event.quoted?null:needsQuoteAppearance(event);
        return <button key={event.id} className={'calendar-event opportunity-calendar-event '+(event.quoted?'is-quoted':'needs-quote team-coded')} style={appearance?.style} title={event.project+' · '+(event.quoted?'Quoted / linked':'Needs quote · '+appearance?.label)} aria-label={event.project+', '+(event.quoted?'already quoted or linked':'needs quote, '+appearance?.label)} onClick={()=>onOpen(event.id)}><span>{event.project}</span></button>;
      })}{events.length>3&&<button className="more-events" onClick={()=>setDay(date)}>+{events.length-3} more</button>}</div>;
    })}</div></section>
    <section className="panel agenda"><div className="panel-heading"><h2>{day?label(day):'Approved deadline agenda'}</h2>{day&&<button className="text-btn" onClick={()=>setDay('')}>Show full month</button>}</div>{agenda.map(item=>{
      const appearance=item.quoted?null:needsQuoteAppearance(item);
      return <div key={item.id} className="agenda-row"><div className="agenda-date">{label(item.due)}</div><span className={'calendar-quote-state '+(item.quoted?'is-quoted':'needs-quote team-coded')} style={appearance?.style}>{item.quoted?'Quoted':'Need quote · '+appearance?.label}</span><button className="project-name" onClick={()=>onOpen(item.id)}>{item.project}<span className="sub-line">{item.builders.join(' · ')||'Builder not specified'} · {item.region}</span></button></div>;
    })}{!agenda.length&&<div className="empty-state"><CalendarDays/><h3>No approved opportunities for this period</h3><p>Choose another month or switch to the Chase-up calendar.</p></div>}</section></>}
    {displayMode==='agenda'&&<section className="panel opportunity-rolling-agenda" aria-label={`Approved deadlines in the next ${agendaDays} days`}>
      <div className="panel-heading"><div><h2>Upcoming approved deadlines</h2><p>{label(today)} – {label(end)} · {agendaData.length} opportunities</p></div></div>
      {Object.entries(agendaGroups).sort(([a],[b])=>a.localeCompare(b)).map(([date,items])=><div key={date} className="calendar-agenda-day"><h3>{label(date)} <span className={'agenda-urgency '+(dueInDays(date)<=3?'urgent':dueInDays(date)<=7?'soon':'upcoming')}>{dueInDays(date)===0?'Due today':dueInDays(date)===1?'Due tomorrow':`In ${dueInDays(date)} days`}</span><small>{items.length} project{items.length===1?'':'s'}</small></h3>{items.map(item=>{const appearance=item.quoted?null:needsQuoteAppearance(item);return <div key={item.id} className="calendar-agenda-entry"><span className={'calendar-quote-state '+(item.quoted?'is-quoted':'needs-quote team-coded')} style={appearance?.style}>{item.quoted?'Quoted / linked':'Need quote · '+appearance?.label}</span><div><b>{item.project}</b><small>{item.builders.join(' · ')||'Builder not specified'} · {item.region}</small></div><button className="secondary-btn" onClick={()=>onOpen(item.id)}>Open opportunity</button></div>})}</div>)}
      {!agendaLoading&&!agendaError&&agendaData.length===0&&<div className="empty-state"><CalendarDays/><h3>No approved deadlines coming up</h3><p>Choose 30 days or return to the month calendar.</p></div>}
    </section>}
  </section>;
}
