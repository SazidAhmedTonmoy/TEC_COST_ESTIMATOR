'use client';
import {useMemo,useState,type FormEvent} from 'react';
import {Award,CalendarDays,Check,Clock,ExternalLink,Mail,Phone,Search,UserRound,AlertTriangle,Pencil,RefreshCw} from 'lucide-react';
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from '@/components/ui/dialog';
import type {Chase,Submission} from '@/lib/types';
import './open-awarded.css';

type AwardContactFields={awardedDate:string;awardContactName:string;awardContactEmail:string;awardContactPhone:string};
type Props={submissions:Submission[];chases:Chase[];saving:boolean;onOpen:(s:Submission)=>void;onSave:(s:Submission,fields:AwardContactFields)=>Promise<boolean>;onRefresh:()=>Promise<unknown>};
const fieldsFrom=(s:Submission):AwardContactFields=>({awardedDate:s.awardedDate||'',awardContactName:s.awardContactName||'',awardContactEmail:s.awardContactEmail||'',awardContactPhone:s.awardContactPhone||''});
const toDate=(s:string)=>s?new Date(s+'T12:00:00').toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'}):'Not recorded';
const phoneHref=(phone:string)=>'tel:'+phone.replace(/[^\d+]/g,'').replace(/(?!^)\+/g,'');
const outlookHref=(email:string)=>'https://outlook.office.com/mail/deeplink/compose?to='+encodeURIComponent(email);

/** TEC Open AND builder Awarded: never infer awards from chase-up or due dates. */
export function selectOpenAwarded(rows:Submission[]){
 return rows.filter(s=>s.status==='Open'&&s.builderStatus==='Awarded').sort((a,b)=>
   (b.awardedDate||'').localeCompare(a.awardedDate||'')||a.project.localeCompare(b.project)||a.builder.localeCompare(b.builder));
}
export function OpenAwarded({submissions,chases,saving,onOpen,onSave,onRefresh}:Props){
 const [query,setQuery]=useState('');
 const [onlyMissing,setOnlyMissing]=useState(false);
 const [editing,setEditing]=useState<Submission|null>(null);
 const [draft,setDraft]=useState<AwardContactFields>({awardedDate:'',awardContactName:'',awardContactEmail:'',awardContactPhone:''});
 const [refreshing,setRefreshing]=useState(false);
 const latest=useMemo(()=>{
  const map=new Map<string,Chase>();
  for(const chase of chases){const prior=map.get(chase.submissionId);if(!prior||chase.date>prior.date||(chase.date===prior.date&&chase.createdAt>prior.createdAt))map.set(chase.submissionId,chase)}
  return map;
 },[chases]);
 const all=useMemo(()=>selectOpenAwarded(submissions),[submissions]);
 const missing=(s:Submission)=>!s.awardContactName||!s.awardContactEmail||!s.awardContactPhone;
 const visible=all.filter(s=>{
  if(onlyMissing&&!missing(s))return false;
  const text=[s.project,s.builder,s.region,s.submittedByTeam,s.awardContactName,s.awardContactEmail,s.awardContactPhone,latest.get(s.id)?.note].join(' ').toLocaleLowerCase();
  return query.trim().toLocaleLowerCase().split(/\s+/).every(word=>text.includes(word));
 });
 function hasUnsavedDraft(){return Boolean(editing&&JSON.stringify(draft)!==JSON.stringify(fieldsFrom(editing)));}
 function cancelEdit(){if(saving)return;if(hasUnsavedDraft()&&!window.confirm('Discard unsaved awarded-project contact changes?'))return;setEditing(null);}
 function edit(s:Submission){setEditing(s);setDraft(fieldsFrom(s));}
 async function save(e:FormEvent){e.preventDefault();if(!editing)return;if(await onSave(editing,draft))setEditing(null);}
 async function reload(){if(refreshing)return;setRefreshing(true);try{await onRefresh()}finally{setRefreshing(false)}}
 return <section className="oa-workspace">
   <div className="oa-heading"><div><span className="oa-eyebrow"><Award size={15}/> TENDER FOLLOW-UP</span><h2>Open-Awarded</h2><p>Builder-awarded projects with TEC quotations still marked Open. Contact the awarded builder and record the latest follow-up.</p></div><button type="button" className="secondary-btn" disabled={refreshing} onClick={()=>void reload()}><RefreshCw size={16} className={refreshing?'oa-spin':''}/>Refresh</button></div>
   <div className="oa-toolbar"><div className="oa-search"><Search size={17}/><input type="search" aria-label="Search Open-Awarded projects" placeholder="Search project, builder, contact or chase-up…" value={query} onChange={e=>setQuery(e.target.value)}/></div><label className="oa-missing-only"><input type="checkbox" checked={onlyMissing} onChange={e=>setOnlyMissing(e.target.checked)}/> Missing contacts only</label><span className="oa-count">{visible.length} of {all.length} projects</span></div>
   <div className="oa-sort-caption"><CalendarDays size={14}/> Recently awarded first <span>· Projects without a recorded award date appear last</span></div>
   {visible.length===0?<div className="oa-empty"><Award size={26}/><h3>{all.length?'No matching projects':'No Open-Awarded projects yet'}</h3><p>{all.length?'Try clearing the search or the missing-contacts filter.':'Projects appear here when TEC status is Open and the builder outcome is Awarded.'}</p>{all.length>0&&<button type="button" className="secondary-btn" onClick={()=>{setQuery('');setOnlyMissing(false)}}>Clear filters</button>}</div>:
   <div className="oa-grid">{visible.map(s=>{const chase=latest.get(s.id);const hasContact=!missing(s);return <article className="oa-card" key={s.id} onClick={e=>{if(!(e.target as HTMLElement).closest("a, button, input"))onOpen(s)}}>
     <button type="button" className="oa-card-main" onClick={()=>onOpen(s)} aria-label={'Open all details for '+s.project+' — '+s.builder}>
       <div className="oa-card-eyebrow"><span className="oa-award-tag"><Check size={12}/> Builder awarded</span><span className="oa-open-tag">TEC · Open</span></div>
       <h3>{s.project}</h3><div className="oa-builder">{s.builder}</div>
       <div className="oa-card-facts"><span><small>Awarded date</small><strong className={!s.awardedDate?'oa-not-recorded':''}>{toDate(s.awardedDate||'')}</strong></span><span><small>Submitted value (AUD)</small><strong>{s.value==null?'Not recorded':new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD',maximumFractionDigits:2}).format(s.value)}</strong></span></div>
       <div className="oa-latest"><span><Clock size={14}/> Last chase-up {chase?.date?toDate(chase.date):''}</span><p>{chase?.note||'No chase-up recorded yet.'}</p>{chase?.author&&<small>Recorded by {chase.author}</small>}</div>
     </button>
     <div className="oa-card-contact"><div className="oa-contact-heading"><strong><UserRound size={16}/> Awarded-project contact</strong><button type="button" className="oa-edit-btn" onClick={()=>edit(s)}><Pencil size={14}/>{hasContact?'Edit':'Add contact'}</button></div>
     {s.awardContactName?<div className="oa-person">{s.awardContactName}</div>:null}
     <div className="oa-contact-links">{s.awardContactPhone&&<a href={phoneHref(s.awardContactPhone)} aria-label={'Call '+s.awardContactName+' on '+s.awardContactPhone}><Phone size={15}/>{s.awardContactPhone}</a>}{s.awardContactEmail&&<a href={outlookHref(s.awardContactEmail)} target="_blank" rel="noopener noreferrer" aria-label={'Compose Outlook email to '+s.awardContactEmail}><Mail size={15}/>{s.awardContactEmail}<ExternalLink size={12}/></a>}</div>
     {!hasContact&&<p className="oa-contact-warning" role="note"><AlertTriangle size={14}/> Add {['contact name','email','phone'].filter((_,i)=>![s.awardContactName,s.awardContactEmail,s.awardContactPhone][i]).join(', ')} to contact the builder.</p>}
     {!s.awardedDate&&<button type="button" className="oa-date-warning" onClick={()=>edit(s)}><CalendarDays size={14}/> Awarded date not recorded — add date</button>}
     </div>
     <button type="button" className="oa-view-details" onClick={()=>onOpen(s)}>View project, contacts and chase history <ExternalLink size={14}/></button>
    </article>})}</div>}
   <Dialog open={Boolean(editing)} onOpenChange={v=>{if(!v)cancelEdit()}}><DialogContent className="tender-dialog oa-dialog"><DialogHeader><DialogTitle>Awarded project details</DialogTitle><DialogDescription>{editing?.project} — {editing?.builder}. These details are separate from the original tender contact.</DialogDescription></DialogHeader>
   {editing&&<form onSubmit={e=>void save(e)} className="oa-edit-form"><label>Awarded date<input type="date" value={draft.awardedDate} onChange={e=>setDraft({...draft,awardedDate:e.target.value})}/></label><label>Contact person name<input type="text" maxLength={200} placeholder="Name of the person handling the award" value={draft.awardContactName} onChange={e=>setDraft({...draft,awardContactName:e.target.value})}/></label><label>Contact email<input type="email" maxLength={254} placeholder="person@builder.com.au" value={draft.awardContactEmail} onChange={e=>setDraft({...draft,awardContactEmail:e.target.value})}/></label><label>Contact phone number<input type="tel" maxLength={45} placeholder="+61 …" value={draft.awardContactPhone} onChange={e=>setDraft({...draft,awardContactPhone:e.target.value})}/></label><p className="form-hint">You can save partial details. Missing fields will remain highlighted on the card. Email links open Outlook on the web; phone links use your device dialler.</p><div className="dialog-actions"><button type="button" className="secondary-btn" disabled={saving} onClick={cancelEdit}>Cancel</button><button type="submit" className="primary-btn" disabled={saving}>{saving?'Saving…':'Save details'}</button></div></form>}</DialogContent></Dialog>
 </section>
}
