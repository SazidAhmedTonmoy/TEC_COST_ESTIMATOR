'use client';
import {useEffect,useMemo,useState,type FormEvent} from 'react';
import {Award,CalendarDays,Check,ChevronLeft,ChevronRight,Clock,ExternalLink,Mail,Phone,Search,UserRound,AlertTriangle,Pencil,RefreshCw,LayoutGrid,Link2} from 'lucide-react';
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from '@/components/ui/dialog';
import {safeOpportunityLink} from '@/lib/opportunity-display';
import type {Chase,Submission} from '@/lib/types';
import './open-awarded.css';

type AwardContactFields={awardedDate:string;estStartDate:string;awardProjectLink:string;awardContactName:string;awardContactEmail:string;awardContactPhone:string};
type Props={submissions:Submission[];chases:Chase[];saving:boolean;onOpen:(s:Submission)=>void;onSave:(s:Submission,fields:AwardContactFields)=>Promise<boolean>;onRefresh:()=>Promise<unknown>};
export type AwardCalendarEvent={date:string;kind:'awarded'|'start';submission:Submission};
const fieldsFrom=(s:Submission):AwardContactFields=>({awardedDate:s.awardedDate||'',estStartDate:s.estStartDate||'',awardProjectLink:s.awardProjectLink||'',awardContactName:s.awardContactName||'',awardContactEmail:s.awardContactEmail||'',awardContactPhone:s.awardContactPhone||''});
const toDate=(s:string)=>s?new Date(s+'T12:00:00').toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'}):'Not recorded';
const phoneHref=(phone:string)=>'tel:'+phone.replace(/[^\d+]/g,'').replace(/(?!^)\+/g,'');
const outlookHref=(email:string)=>'https://outlook.office.com/mail/deeplink/compose?to='+encodeURIComponent(email);
const projectUrl=(s:Submission)=>safeOpportunityLink(s.awardProjectLink||s.opportunityLink);
const isOpportunityLink=(s:Submission)=>!s.awardProjectLink&&Boolean(s.opportunityLink);
const savedDisplay=(): 'cards'|'calendar'=>{try{return sessionStorage.getItem('tec-open-awarded-view')==='calendar'?'calendar':'cards'}catch{return 'cards'}};
const savedMonth=()=>{try{const value=sessionStorage.getItem('tec-open-awarded-month')||'';return /^\d{4}-(0[1-9]|1[0-2])$/.test(value)?value:currentMonth()}catch{return currentMonth()}};
const isoDate=(s:string)=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(s))return false;const d=new Date(s+'T12:00:00Z');return !Number.isNaN(d.getTime())&&d.toISOString().slice(0,10)===s;};
const currentMonth=()=>{
 const parts=new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit'}).formatToParts(new Date());
 const values=Object.fromEntries(parts.map(p=>[p.type,p.value]));return `${values.year}-${values.month}`;
};
const shiftMonth=(month:string,change:number)=>{
 const [year,number]=month.split('-').map(Number);
 return new Date(Date.UTC(year,number-1+change,1)).toISOString().slice(0,7);
};
const monthTitle=(month:string)=>new Date(month+'-01T12:00:00Z').toLocaleDateString('en-AU',{timeZone:'UTC',month:'long',year:'numeric'});
/** Dates are treated as calendar days, not timestamps; no timezone shifts. */
export function awardCalendarEvents(rows:Submission[]):AwardCalendarEvent[]{
 return rows.flatMap(submission=>[
  ...(isoDate(submission.awardedDate||'')?[{date:submission.awardedDate!,kind:'awarded' as const,submission}]:[]),
  ...(isoDate(submission.estStartDate||'')?[{date:submission.estStartDate!,kind:'start' as const,submission}]:[]),
 ]).sort((a,b)=>a.date.localeCompare(b.date)||a.kind.localeCompare(b.kind)||a.submission.project.localeCompare(b.submission.project));
}
export function awardMonthCells(month:string):(string|null)[]{
 if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(month))return [];
 const [year,number]=month.split('-').map(Number);
 const first=new Date(Date.UTC(year,number-1,1));
 const days=new Date(Date.UTC(year,number,0)).getUTCDate();
 const mondayOffset=(first.getUTCDay()+6)%7;
 const slots=Math.ceil((mondayOffset+days)/7)*7;
 return Array.from({length:slots},(_,i)=>{
  const day=i-mondayOffset+1;
  return day>0&&day<=days?`${month}-${String(day).padStart(2,'0')}`:null;
 });
}
/** TEC Open AND builder Awarded; never infer an award from a chase-up or due date. */
export function selectOpenAwarded(rows:Submission[]){
 return rows.filter(s=>s.status==='Open'&&s.builderStatus==='Awarded').sort((a,b)=>
   (b.awardedDate||'').localeCompare(a.awardedDate||'')||a.project.localeCompare(b.project)||a.builder.localeCompare(b.builder));
}
export function OpenAwarded({submissions,chases,saving,onOpen,onSave,onRefresh}:Props){
 const [query,setQuery]=useState('');
 const [onlyMissing,setOnlyMissing]=useState(false);
 const [view,setView]=useState<'cards'|'calendar'>(savedDisplay);
 const [month,setMonth]=useState(savedMonth);
 const [selectedDay,setSelectedDay]=useState('');
 const [editing,setEditing]=useState<Submission|null>(null);
 const [draft,setDraft]=useState<AwardContactFields>({awardedDate:'',estStartDate:'',awardProjectLink:'',awardContactName:'',awardContactEmail:'',awardContactPhone:''});
 const [refreshing,setRefreshing]=useState(false);
 useEffect(()=>{try{sessionStorage.setItem('tec-open-awarded-view',view);sessionStorage.setItem('tec-open-awarded-month',month)}catch{/* Private-mode storage may be unavailable. */}},[view,month]);
 const latest=useMemo(()=>{
  const map=new Map<string,Chase>();
  for(const chase of chases){const prior=map.get(chase.submissionId);if(!prior||chase.date>prior.date||(chase.date===prior.date&&chase.createdAt>prior.createdAt))map.set(chase.submissionId,chase)}
  return map;
 },[chases]);
 const all=useMemo(()=>selectOpenAwarded(submissions),[submissions]);
 const missing=(s:Submission)=>!s.awardContactName||!s.awardContactEmail||!s.awardContactPhone;
 const visible=all.filter(s=>{
  if(onlyMissing&&!missing(s))return false;
  const text=[s.project,s.builder,s.region,s.submittedByTeam,s.awardContactName,s.awardContactEmail,s.awardContactPhone,s.awardedDate,s.estStartDate,s.awardProjectLink,s.opportunityLink,latest.get(s.id)?.note].join(' ').toLocaleLowerCase();
  return query.trim().toLocaleLowerCase().split(/\s+/).every(word=>text.includes(word));
 });
 const events=useMemo(()=>awardCalendarEvents(visible),[all,onlyMissing,query,latest]);
 const eventsByDay=useMemo(()=>{
  const days=new Map<string,AwardCalendarEvent[]>();
  for(const event of events){const list=days.get(event.date)||[];list.push(event);days.set(event.date,list)}
  return days;
 },[events]);
 const days=useMemo(()=>awardMonthCells(month),[month]);
 const dayEvents=selectedDay?eventsByDay.get(selectedDay)||[]:[];
 function hasUnsavedDraft(){return Boolean(editing&&JSON.stringify(draft)!==JSON.stringify(fieldsFrom(editing)));}
 function cancelEdit(){if(saving)return;if(hasUnsavedDraft()&&!window.confirm('Discard unsaved awarded-project details?'))return;setEditing(null);}
 function edit(s:Submission){setEditing(s);setDraft(fieldsFrom(s));}
 async function save(e:FormEvent){e.preventDefault();if(!editing)return;if(await onSave(editing,draft))setEditing(null);}
 async function reload(){if(refreshing)return;setRefreshing(true);try{await onRefresh()}finally{setRefreshing(false)}}
 function goMonth(delta:number){setMonth(previous=>shiftMonth(previous,delta));setSelectedDay('');}
 return <section className="oa-workspace">
   <div className="oa-heading"><div><span className="oa-eyebrow"><Award size={15}/> TENDER FOLLOW-UP</span><h2>Open-Awarded</h2><p>Builder-awarded projects with TEC quotations still marked Open. Keep the award, start date, project link and follow-up contact in one place.</p></div><button type="button" className="secondary-btn" disabled={refreshing} onClick={()=>void reload()}><RefreshCw size={16} className={refreshing?'oa-spin':''}/>Refresh</button></div>
   <div className="oa-toolbar"><div className="oa-search"><Search size={17}/><input type="search" aria-label="Search Open-Awarded projects" placeholder="Search project, builder, contact or chase-up…" value={query} onChange={e=>setQuery(e.target.value)}/></div><label className="oa-missing-only"><input type="checkbox" checked={onlyMissing} onChange={e=>setOnlyMissing(e.target.checked)}/> Missing contacts only</label><span className="oa-count">{visible.length} of {all.length} projects</span><div className="oa-view-switch" role="group" aria-label="Open-Awarded display"><button type="button" className={view==='cards'?'is-selected':''} aria-pressed={view==='cards'} onClick={()=>setView('cards')}><LayoutGrid size={15}/> Cards</button><button type="button" className={view==='calendar'?'is-selected':''} aria-pressed={view==='calendar'} onClick={()=>setView('calendar')}><CalendarDays size={15}/> Calendar</button></div></div>
   {visible.length===0?<div className="oa-empty"><Award size={26}/><h3>{all.length?'No matching projects':'No Open-Awarded projects yet'}</h3><p>{all.length?'Try clearing the search or the missing-contacts filter.':'Projects appear here when TEC status is Open and the builder outcome is Awarded.'}</p>{all.length>0&&<button type="button" className="secondary-btn" onClick={()=>{setQuery('');setOnlyMissing(false)}}>Clear filters</button>}</div>:
   view==='cards'?<>
     <div className="oa-sort-caption"><CalendarDays size={14}/> Recently awarded first <span>· Projects without a recorded award date appear last</span></div>
     <div className="oa-grid">{visible.map(s=>{const chase=latest.get(s.id);const hasContact=!missing(s);const link=projectUrl(s);return <article className="oa-card" key={s.id} onClick={event=>{if(!(event.target as HTMLElement).closest("a, button, input"))onOpen(s)}}>
       <button type="button" className="oa-card-main" onClick={()=>onOpen(s)} aria-label={'Open all details for '+s.project+' — '+s.builder}>
         <div className="oa-card-eyebrow"><span className="oa-award-tag"><Check size={12}/> Builder awarded</span><span className="oa-open-tag">TEC · Open</span></div>
         <h3>{s.project}</h3><div className="oa-builder">{s.builder}</div>
         <div className="oa-card-facts"><span><small>Awarded date</small><strong className={!s.awardedDate?'oa-not-recorded':''}>{toDate(s.awardedDate||'')}</strong></span><span><small>Est. start date</small><strong className={!s.estStartDate?'oa-not-recorded':''}>{toDate(s.estStartDate||'')}</strong></span><span className="oa-value-fact"><small>Submitted value (AUD)</small><strong>{s.value==null?'Not recorded':new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD',maximumFractionDigits:2}).format(s.value)}</strong></span></div>
         <div className="oa-latest"><span><Clock size={14}/> Last chase-up {chase?.date?toDate(chase.date):''}</span><p>{chase?.note||'No chase-up recorded yet.'}</p>{chase?.author&&<small>Recorded by {chase.author}</small>}</div>
       </button>
       <div className="oa-project-link"><strong><Link2 size={15}/> Project link</strong>{link?<a href={link} target="_blank" rel="noopener noreferrer" title={link}>Open project <ExternalLink size={13}/>{isOpportunityLink(s)&&<small>{s.opportunityLinkSource==='exact-match'?'Matched Opportunity':'Linked Opportunity'}</small>}</a>:<button type="button" className="oa-link-missing" onClick={()=>edit(s)}><AlertTriangle size={13}/> Add project link</button>}</div>
       <div className="oa-card-contact"><div className="oa-contact-heading"><strong><UserRound size={16}/> Awarded-project contact</strong><button type="button" className="oa-edit-btn" onClick={()=>edit(s)}><Pencil size={14}/>{hasContact?'Edit':'Add contact'}</button></div>
       {s.awardContactName?<div className="oa-person">{s.awardContactName}</div>:null}
       <div className="oa-contact-links">{s.awardContactPhone&&<a href={phoneHref(s.awardContactPhone)} aria-label={'Call '+s.awardContactName+' on '+s.awardContactPhone}><Phone size={15}/>{s.awardContactPhone}</a>}{s.awardContactEmail&&<a href={outlookHref(s.awardContactEmail)} target="_blank" rel="noopener noreferrer" aria-label={'Compose Outlook email to '+s.awardContactEmail}><Mail size={15}/>{s.awardContactEmail}<ExternalLink size={12}/></a>}</div>
       {!hasContact&&<p className="oa-contact-warning" role="note"><AlertTriangle size={14}/> Add {['contact name','email','phone'].filter((_,i)=>![s.awardContactName,s.awardContactEmail,s.awardContactPhone][i]).join(', ')} to contact the builder.</p>}
       {!s.awardedDate&&<button type="button" className="oa-date-warning" onClick={()=>edit(s)}><CalendarDays size={14}/> Awarded date not recorded — add date</button>}
       </div>
       <button type="button" className="oa-view-details" onClick={()=>onOpen(s)}>View project, contacts and chase history <ExternalLink size={14}/></button>
      </article>})}</div>
    </>:<div className="oa-calendar" aria-label="Open-Awarded monthly calendar">
      <div className="oa-calendar-toolbar"><div className="oa-calendar-nav"><button type="button" aria-label="Previous month" onClick={()=>goMonth(-1)}><ChevronLeft size={19}/></button><label className="oa-month-field"><span className="sr-only">Calendar month</span><input type="month" aria-label="Calendar month" value={month} onChange={e=>{if(e.target.value){setMonth(e.target.value);setSelectedDay('')}}}/></label><button type="button" aria-label="Next month" onClick={()=>goMonth(1)}><ChevronRight size={19}/></button><button type="button" className="oa-today" onClick={()=>{setMonth(currentMonth());setSelectedDay('')}}>Today</button></div><strong className="oa-calendar-title">{monthTitle(month)}</strong><div className="oa-calendar-legend"><span><i className="oa-legend-award"/> Awarded</span><span><i className="oa-legend-start"/> Estimated start</span></div></div>
      <div className="oa-calendar-weekdays">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(day=><span key={day}>{day}</span>)}</div>
      <div className="oa-calendar-grid">{days.map((date,i)=>date?<div key={date} className={'oa-calendar-day'+(selectedDay===date?' is-active':'')}><button type="button" className="oa-calendar-date" onClick={()=>setSelectedDay(date)} aria-label={'Show events on '+toDate(date)} aria-pressed={selectedDay===date}>{Number(date.slice(-2))}</button>{(eventsByDay.get(date)||[]).slice(0,3).map((event,index)=><button key={event.submission.id+event.kind+index} type="button" className={'oa-calendar-event '+(event.kind==='awarded'?'oa-event-award':'oa-event-start')} title={`${event.kind==='awarded'?'Awarded':'Estimated start'}: ${event.submission.project} — ${event.submission.builder}`} aria-label={`${event.kind==='awarded'?'Awarded':'Estimated start'}: ${event.submission.project}, ${event.submission.builder}. Open details`} onClick={()=>onOpen(event.submission)}><span>{event.kind==='awarded'?'Awarded':'Start'}</span> {event.submission.project}</button>)}{(eventsByDay.get(date)||[]).length>3&&<button type="button" className="oa-calendar-more" onClick={()=>setSelectedDay(date)}>+{(eventsByDay.get(date)||[]).length-3} more</button>}</div>:<div key={'pad-'+i} className="oa-calendar-day oa-calendar-pad" aria-hidden="true"/>)}</div>
      <div className="oa-calendar-footer"><div><strong>{selectedDay?`Events on ${toDate(selectedDay)}`:'Select a day to see all events'}</strong><p>Awarded dates and estimated starts are shown separately. Dates not recorded are not added to the calendar.</p></div>{selectedDay&&<div className="oa-selected-events">{dayEvents.length?dayEvents.map((event,i)=><button key={event.submission.id+event.kind+i} type="button" onClick={()=>onOpen(event.submission)}><span className={event.kind==='awarded'?'oa-event-award':'oa-event-start'}>{event.kind==='awarded'?'Awarded':'Est. start'}</span><strong>{event.submission.project}</strong><small>{event.submission.builder}</small><ExternalLink size={13}/></button>):<p>No events recorded on this date.</p>}</div>}<p className="oa-calendar-missing">{visible.filter(s=>!s.awardedDate).length} missing award date · {visible.filter(s=>!s.estStartDate).length} missing estimated start date</p></div>
    </div>}
   <Dialog open={Boolean(editing)} onOpenChange={v=>{if(!v)cancelEdit()}}><DialogContent className="tender-dialog oa-dialog"><DialogHeader><DialogTitle>Awarded project details</DialogTitle><DialogDescription>{editing?.project} — {editing?.builder}. Dates, project link and contact are saved for this builder submission.</DialogDescription></DialogHeader>
   {editing&&<form onSubmit={e=>void save(e)} className="oa-edit-form"><div className="oa-date-fields"><label>Awarded date<input type="date" value={draft.awardedDate} onChange={e=>setDraft({...draft,awardedDate:e.target.value})}/></label><label>Estimated start date<input type="date" value={draft.estStartDate} onChange={e=>setDraft({...draft,estStartDate:e.target.value})}/></label></div><label>Project link<input type="url" inputMode="url" maxLength={2048} placeholder={editing.opportunityLink||'https://example.com/project'} value={draft.awardProjectLink} onChange={e=>setDraft({...draft,awardProjectLink:e.target.value})}/></label>{safeOpportunityLink(editing.opportunityLink)&&<p className="oa-linked-hint"><Link2 size={14}/> {draft.awardProjectLink?'Manual link overrides the linked Opportunity URL.':'The Opportunity URL will be used automatically.'} <a href={safeOpportunityLink(editing.opportunityLink)} target="_blank" rel="noopener noreferrer">View Opportunity link <ExternalLink size={12}/></a>{draft.awardProjectLink&&<button type="button" onClick={()=>setDraft({...draft,awardProjectLink:''})}>Use Opportunity link</button>}</p>}<label>Contact person name<input type="text" maxLength={200} placeholder="Name of the person handling the award" value={draft.awardContactName} onChange={e=>setDraft({...draft,awardContactName:e.target.value})}/></label><label>Contact email<input type="email" maxLength={254} placeholder="person@builder.com.au" value={draft.awardContactEmail} onChange={e=>setDraft({...draft,awardContactEmail:e.target.value})}/></label><label>Contact phone number<input type="tel" maxLength={45} placeholder="+61 …" value={draft.awardContactPhone} onChange={e=>setDraft({...draft,awardContactPhone:e.target.value})}/></label><p className="form-hint">Dates are optional. Leave Project link blank to use the linked Opportunity URL where available. Missing fields remain visible on the card; phone links use your dialler and email uses Outlook on the web.</p><div className="dialog-actions"><button type="button" className="secondary-btn" disabled={saving} onClick={cancelEdit}>Cancel</button><button type="submit" className="primary-btn" disabled={saving}>{saving?'Saving…':'Save details'}</button></div></form>}</DialogContent></Dialog>
 </section>;
}
