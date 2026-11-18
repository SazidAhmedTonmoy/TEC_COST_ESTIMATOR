'use client';
import {useEffect,useMemo,useRef,useState,type FormEvent} from 'react';
import {Award,CalendarDays,Check,ChevronLeft,ChevronRight,Clock,ExternalLink,Search,UserRound,AlertTriangle,Pencil,LayoutGrid,Link2,Plus,Trash2,X} from 'lucide-react';
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from '@/components/ui/dialog';
import {safeOpportunityLink} from '@/lib/opportunity-display';
import type {AwardContact,Chase,Submission} from '@/lib/types';
import {awardedContacts,missingAwardContact,searchAwardContacts} from '@/lib/award-contacts';
import {AwardContactList} from './award-contact-list';
import './open-awarded.css';

type AwardContactFields={awardedDate:string;estStartDate:string;awardProjectLink:string;awardContacts:AwardContact[]};
type Props={submissions:Submission[];chases:Chase[];saving:boolean;onOpen:(s:Submission)=>void;onSave:(s:Submission,fields:AwardContactFields)=>Promise<boolean>};
export type AwardCalendarEvent={date:string;kind:'awarded'|'start';submission:Submission};
const fieldsFrom=(s:Submission):AwardContactFields=>({awardedDate:s.awardedDate||'',estStartDate:s.estStartDate||'',awardProjectLink:s.awardProjectLink||'',awardContacts:awardedContacts(s)});
const toDate=(s:string)=>s?new Date(s+'T12:00:00').toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'}):'Not recorded';
const projectUrl=(s:Submission)=>safeOpportunityLink(s.awardProjectLink||s.opportunityLink);
const isOpportunityLink=(s:Submission)=>!s.awardProjectLink&&Boolean(s.opportunityLink);
const savedDisplay=(): 'cards'|'calendar'=>{try{return sessionStorage.getItem('tec-open-awarded-view')==='calendar'?'calendar':'cards'}catch{return 'cards'}};
const savedMonth=()=>{try{const value=sessionStorage.getItem('tec-open-awarded-month')||'';return /^\d{4}-(0[1-9]|1[0-2])$/.test(value)?value:currentMonth()}catch{return currentMonth()}};
const isoDate=(s:string)=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(s))return false;const d=new Date(s+'T12:00:00Z');return !Number.isNaN(d.getTime())&&d.toISOString().slice(0,10)===s;};
/** Date-only value in the same Sydney timezone used by Tender due dates. */
export function sydneyCalendarDate(instant:Date=new Date()):string{
 const parts=new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(instant);
 const values=Object.fromEntries(parts.map(p=>[p.type,p.value]));
 return `${values.year}-${values.month}-${values.day}`;
}
const currentMonth=()=>sydneyCalendarDate().slice(0,7);
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
export function OpenAwarded({submissions,chases,saving,onOpen,onSave}:Props){
 const [query,setQuery]=useState('');
 const [onlyMissing,setOnlyMissing]=useState(false);
 const [view,setView]=useState<'cards'|'calendar'>(savedDisplay);
 const [month,setMonth]=useState(savedMonth);
 const [selectedDay,setSelectedDay]=useState('');
 const [focusedEvent,setFocusedEvent]=useState('');
 const selectedEventsRef=useRef<HTMLDivElement>(null);
 const [editing,setEditing]=useState<Submission|null>(null);
 const [draft,setDraft]=useState<AwardContactFields>({awardedDate:'',estStartDate:'',awardProjectLink:'',awardContacts:[]});
 const [today,setToday]=useState(sydneyCalendarDate);
 useEffect(()=>{try{sessionStorage.setItem('tec-open-awarded-view',view);sessionStorage.setItem('tec-open-awarded-month',month)}catch{/* Private-mode storage may be unavailable. */}},[view,month]);
 // Keep today's marker current if the page remains open across midnight in Sydney.
 useEffect(()=>{const update=()=>setToday(sydneyCalendarDate());const timer=window.setInterval(update,60_000);document.addEventListener('visibilitychange',update);return()=>{window.clearInterval(timer);document.removeEventListener('visibilitychange',update)};},[]);
 const latest=useMemo(()=>{
  const map=new Map<string,Chase>();
  for(const chase of chases){const prior=map.get(chase.submissionId);if(!prior||chase.date>prior.date||(chase.date===prior.date&&chase.createdAt>prior.createdAt))map.set(chase.submissionId,chase)}
  return map;
 },[chases]);
 const all=useMemo(()=>selectOpenAwarded(submissions),[submissions]);
 const missing=missingAwardContact;
 const visible=all.filter(s=>{
  if(onlyMissing&&!missing(s))return false;
  const text=[s.project,s.builder,s.region,s.submittedByTeam,searchAwardContacts(s),s.awardedDate,s.estStartDate,s.awardProjectLink,s.opportunityLink,latest.get(s.id)?.note].join(' ').toLocaleLowerCase();
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
 function changeContact(personIndex:number,updated:AwardContact){setDraft(old=>({...old,awardContacts:old.awardContacts.map((c,i)=>i===personIndex?updated:c)}));}
 function changeContactField(personIndex:number,field:'name'|'emails'|'phones',value:string|number,entryIndex?:number){
  const person=draft.awardContacts[personIndex];
  if(field==='name')changeContact(personIndex,{...person,name:String(value)});
  else changeContact(personIndex,{...person,[field]:person[field].map((entry,i)=>i===entryIndex?String(value):entry)});
 }
 function addContactField(personIndex:number,field:'emails'|'phones'){
  const person=draft.awardContacts[personIndex];
  if(person[field].length>=12)return;
  changeContact(personIndex,{...person,[field]:[...person[field],'']});
 }
 function removeContactField(personIndex:number,field:'emails'|'phones',entryIndex:number){
  const person=draft.awardContacts[personIndex];
  changeContact(personIndex,{...person,[field]:person[field].filter((_,i)=>i!==entryIndex)});
 }
 function addContact(){setDraft(old=>({...old,awardContacts:[...old.awardContacts,{name:'',emails:[''],phones:['']}]}));}
 function removeContact(index:number){
  if(!window.confirm('Remove this contact from the draft? The change is saved only when you select Save details.'))return;
  setDraft(old=>({...old,awardContacts:old.awardContacts.filter((_,i)=>i!==index)}));
 }
 function goMonth(delta:number){setMonth(previous=>shiftMonth(previous,delta));setSelectedDay('');setFocusedEvent('');}
 // Reveal the contact preview without leaving Calendar or losing the user's month.
 function revealCalendarEvent(date:string,event?:AwardCalendarEvent){
  setSelectedDay(date);
  setFocusedEvent(event?`${event.submission.id}:${event.kind}`:'');
  window.requestAnimationFrame(()=>selectedEventsRef.current?.scrollIntoView({behavior:'smooth',block:'start'}));
 }
 return <section className="oa-workspace">
   <div className="oa-heading"><div><span className="oa-eyebrow"><Award size={15}/> TENDER FOLLOW-UP</span><h2>Open-Awarded</h2><p>Builder-awarded projects with TEC quotations still marked Open. Keep the award, start date, project link and follow-up contact in one place.</p></div></div>
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
       <AwardContactList submission={s}/>
       {!s.awardedDate&&<button type="button" className="oa-date-warning" onClick={()=>edit(s)}><CalendarDays size={14}/> Awarded date not recorded — add date</button>}
       </div>
       <button type="button" className="oa-view-details" onClick={()=>onOpen(s)}>View project, contacts and chase history <ExternalLink size={14}/></button>
      </article>})}</div>
    </>:<div className="oa-calendar" aria-label="Open-Awarded monthly calendar">
      <div className="oa-calendar-toolbar"><div className="oa-calendar-nav"><button type="button" aria-label="Previous month" onClick={()=>goMonth(-1)}><ChevronLeft size={19}/></button><label className="oa-month-field"><span className="sr-only">Calendar month</span><input type="month" aria-label="Calendar month" value={month} onChange={e=>{if(e.target.value){setMonth(e.target.value);setSelectedDay('');setFocusedEvent('')}}}/></label><button type="button" aria-label="Next month" onClick={()=>goMonth(1)}><ChevronRight size={19}/></button><button type="button" className="oa-today" onClick={()=>{const date=sydneyCalendarDate();setToday(date);setMonth(date.slice(0,7));setSelectedDay(date);setFocusedEvent('')}}>Today</button></div><strong className="oa-calendar-title">{monthTitle(month)}</strong><div className="oa-calendar-legend"><span><i className="oa-legend-award"/> Awarded</span><span><i className="oa-legend-start"/> Estimated start</span></div></div>
      <div className="oa-calendar-weekdays">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(day=><span key={day}>{day}</span>)}</div>
      <div className="oa-calendar-grid">{days.map((date,i)=>date?<div key={date} className={'oa-calendar-day'+(selectedDay===date?' is-active':'')+(today===date?' is-today':'')}><button type="button" className="oa-calendar-date" onClick={()=>revealCalendarEvent(date)} aria-label={'Show events on '+toDate(date)+(today===date?' (today)':'')} aria-current={today===date?'date':undefined} aria-pressed={selectedDay===date}>{Number(date.slice(-2))}</button>{today===date&&<span className="oa-today-label" aria-hidden="true">Today</span>}{(eventsByDay.get(date)||[]).slice(0,3).map((event,index)=><button key={event.submission.id+event.kind+index} type="button" className={'oa-calendar-event '+(event.kind==='awarded'?'oa-event-award':'oa-event-start')} title={`${event.kind==='awarded'?'Awarded':'Estimated start'}: ${event.submission.project} — ${event.submission.builder}\nContact: ${searchAwardContacts(event.submission)||'Not recorded'}`} aria-label={`${event.kind==='awarded'?'Awarded':'Estimated start'}: ${event.submission.project}, ${event.submission.builder}. Show contact details`} onClick={()=>revealCalendarEvent(date,event)}><span>{event.kind==='awarded'?'Awarded':'Start'}</span> {event.submission.project}</button>)}{(eventsByDay.get(date)||[]).length>3&&<button type="button" className="oa-calendar-more" onClick={()=>revealCalendarEvent(date)}>+{(eventsByDay.get(date)||[]).length-3} more</button>}</div>:<div key={'pad-'+i} className="oa-calendar-day oa-calendar-pad" aria-hidden="true"/>)}</div>
      <div className="oa-calendar-footer" ref={selectedEventsRef}>
       <div className="oa-calendar-footer-intro">
        <strong>{selectedDay?`Events on ${toDate(selectedDay)}`:'Select a date or project to see contact details'}</strong>
        <p>{selectedDay?'Contact details for each awarded builder are shown below. Call or email directly, or open the project.':'Choose any Awarded or Estimated Start event to see the builder contact, phone number and email without leaving Calendar.'}</p>
       </div>
       {selectedDay&&<div className="oa-selected-events" aria-live="polite">{dayEvents.length?dayEvents.map((event,i)=>{
        const s=event.submission;
        const contactMissing=missing(s);
        return <article key={s.id+event.kind+i} className={'oa-selected-event'+(focusedEvent===`${s.id}:${event.kind}`?' is-focused':'')}>
         <div className="oa-selected-event-heading">
          <span className={'oa-selected-event-kind '+(event.kind==='awarded'?'oa-event-award':'oa-event-start')}>{event.kind==='awarded'?'Awarded':'Estimated start'}</span>
          <div className="oa-selected-event-project"><strong>{s.project}</strong><small>{s.builder}</small></div>
         </div>
         <div className="oa-selected-event-contact">
          <div className="oa-selected-event-contact-title"><UserRound size={15}/><span>Contact people</span></div>
          <AwardContactList submission={s}/>
         </div>
         <div className="oa-selected-event-actions">
          <button type="button" className="oa-selected-edit" onClick={()=>edit(s)}><Pencil size={14}/>{contactMissing?'Add contact':'Edit contact'}</button>
          <button type="button" className="oa-selected-open" onClick={()=>onOpen(s)}>View project <ExternalLink size={13}/></button>
         </div>
        </article>
       }):<p>No events recorded on this date.</p>}</div>}
       <p className="oa-calendar-missing">{visible.filter(s=>!s.awardedDate).length} missing award date · {visible.filter(s=>!s.estStartDate).length} missing estimated start date</p>
      </div>
    </div>}
   <Dialog open={Boolean(editing)} onOpenChange={v=>{if(!v)cancelEdit()}}><DialogContent className="tender-dialog oa-dialog"><DialogHeader><DialogTitle>Awarded project details</DialogTitle><DialogDescription>{editing?.project} — {editing?.builder}. Dates, project link and multiple contacts are saved for this builder submission.</DialogDescription></DialogHeader>
   {editing&&<form onSubmit={e=>void save(e)} className="oa-edit-form"><div className="oa-date-fields"><label>Awarded date<input type="date" value={draft.awardedDate} onChange={e=>setDraft({...draft,awardedDate:e.target.value})}/></label><label>Estimated start date<input type="date" value={draft.estStartDate} onChange={e=>setDraft({...draft,estStartDate:e.target.value})}/></label></div><label>Project link<input type="url" inputMode="url" maxLength={2048} placeholder={editing.opportunityLink||'https://example.com/project'} value={draft.awardProjectLink} onChange={e=>setDraft({...draft,awardProjectLink:e.target.value})}/></label>{safeOpportunityLink(editing.opportunityLink)&&<p className="oa-linked-hint"><Link2 size={14}/> {draft.awardProjectLink?'Manual link overrides the linked Opportunity URL.':'The Opportunity URL will be used automatically.'} <a href={safeOpportunityLink(editing.opportunityLink)} target="_blank" rel="noopener noreferrer">View Opportunity link <ExternalLink size={12}/></a>{draft.awardProjectLink&&<button type="button" onClick={()=>setDraft({...draft,awardProjectLink:''})}>Use Opportunity link</button>}</p>}<div className="oa-contact-editor"><div className="oa-contact-editor-heading"><h3>Contact people</h3><button type="button" className="oa-add-control" onClick={addContact} disabled={draft.awardContacts.length>=20}><Plus size={14}/> Add contact person</button></div>
    {draft.awardContacts.map((person,personIndex)=><section className="oa-edit-person" key={personIndex}><div className="oa-edit-person-heading"><strong>Contact {personIndex+1}</strong><button type="button" className="oa-remove-control" onClick={()=>removeContact(personIndex)}><Trash2 size={14}/> Remove person</button></div>
      <label>Contact person name<input type="text" maxLength={200} placeholder="Name of the person handling this project" value={person.name} onChange={e=>changeContactField(personIndex,'name',e.target.value)}/></label>
      <div className="oa-contact-entry-list"><div className="oa-contact-entry-heading"><strong>Phone numbers</strong><button type="button" className="oa-add-control" disabled={person.phones.length>=12} onClick={()=>addContactField(personIndex,'phones')}><Plus size={13}/> Add phone</button></div>
       {person.phones.map((phone,i)=><div className="oa-contact-entry" key={i}><input type="tel" maxLength={45} placeholder="e.g. 02 9616 2990" aria-label={`Phone ${i+1} for contact ${personIndex+1}`} value={phone} onChange={e=>changeContactField(personIndex,'phones',e.target.value,i)}/><button type="button" aria-label={`Remove phone ${i+1} from contact ${personIndex+1}`} onClick={()=>removeContactField(personIndex,'phones',i)}><X size={16}/></button></div>)}
      </div>
      <div className="oa-contact-entry-list"><div className="oa-contact-entry-heading"><strong>Email addresses</strong><button type="button" className="oa-add-control" disabled={person.emails.length>=12} onClick={()=>addContactField(personIndex,'emails')}><Plus size={13}/> Add email</button></div>
       {person.emails.map((email,i)=><div className="oa-contact-entry" key={i}><input type="email" maxLength={254} placeholder="e.g. project@builder.com.au" aria-label={`Email ${i+1} for contact ${personIndex+1}`} value={email} onChange={e=>changeContactField(personIndex,'emails',e.target.value,i)}/><button type="button" aria-label={`Remove email ${i+1} from contact ${personIndex+1}`} onClick={()=>removeContactField(personIndex,'emails',i)}><X size={16}/></button></div>)}
      </div>
    </section>)}
    {!draft.awardContacts.length&&<p className="oa-contact-no-people">No contacts yet. Select Add contact person to record the builder's team.</p>}
   </div><p className="form-hint">Dates are optional. Leave Project link blank to use the linked Opportunity URL. Add as many contact people, phone numbers and email addresses as needed. Each number opens your dialler, and each email opens Outlook.</p><div className="dialog-actions"><button type="button" className="secondary-btn" disabled={saving} onClick={cancelEdit}>Cancel</button><button type="submit" className="primary-btn" disabled={saving}>{saving?'Saving…':'Save details'}</button></div></form>}</DialogContent></Dialog>
 </section>;
}
