import {useEffect,useMemo,useRef,useState,type FormEvent} from 'react';
import {Pencil,Plus,Search,Trash2} from 'lucide-react';
import {toast} from 'sonner';
import {apiFetch} from '../main';
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from './ui/dialog';
import {BuilderContactEditor,BuilderContactList} from './builder-contacts';
import {matchesBuilderContactQuery,type BuilderContact} from '@/lib/builder-contacts';
import {notifyBuilderContactsChanged} from '@/hooks/use-builder-contacts';
import './builder-directory.css';

type Props={builder:string;contacts:BuilderContact[];loading?:boolean;error?:string;onRetry:()=>void;onSaved:()=>Promise<void>};

/** The directory contains every person saved for a builder, including people
 * who are not currently selected on an active quotation. */
export function BuilderContactsPanel({builder,contacts,loading,error,onRetry,onSaved}:Props){
 const [query,setQuery]=useState(''),[limit,setLimit]=useState(20);
 const [draft,setDraft]=useState<BuilderContact[]|null>(null),[saving,setSaving]=useState(false),[saveError,setSaveError]=useState('');
 const [deleting,setDeleting]=useState(''),[deleteError,setDeleteError]=useState('');
 const baseline=useRef('');
 const pending=useRef(false);
 const visible=useMemo(()=>{
  return contacts.filter(person=>matchesBuilderContactQuery('',[person],query));
 },[contacts,query]);
 const dirty=()=>draft!==null&&JSON.stringify(draft)!==baseline.current;
 useEffect(()=>{
  const warn=(event:BeforeUnloadEvent)=>{if(saving||dirty()){event.preventDefault();event.returnValue=''}};
  window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);
 },[draft,saving]);
 function edit(person?:BuilderContact){
  const next=[person?{...person,emails:[...person.emails],phones:[...person.phones]}:{name:'',emails:[''],phones:['']}];
  baseline.current=JSON.stringify(next);setDraft(next);setSaveError('');onRetry();
 }
 function close(){if(saving)return;if(dirty()&&!window.confirm('Discard unsaved contact changes?'))return;setDraft(null);}
 async function save(event:FormEvent){
  event.preventDefault();if(!draft||pending.current)return;
  if(!draft.some(person=>person.name.trim()||person.emails.some(value=>value.trim())||person.phones.some(value=>value.trim()))){setSaveError('Enter a name, email address or phone number.');return}
  pending.current=true;setSaving(true);setSaveError('');
  try{
   const response=await apiFetch('builder-contacts',{method:'POST',body:JSON.stringify({builder,contacts:draft})});
   const result=await response.json();if(!response.ok)throw Error(result.error||'Unable to save the contact.');
   setDraft(null);notifyBuilderContactsChanged();await onSaved();toast.success('Builder contact saved');
  }catch(reason){setSaveError((reason as Error).message||'Unable to confirm the save. Refresh the directory before trying again.');}
  finally{pending.current=false;setSaving(false);}
 }
 async function deleteContact(person:BuilderContact){
  if(!person.id||!person.canDelete||pending.current)return;
  const name=person.name||person.emails[0]||person.phones[0]||'this contact';
  if(!window.confirm(`Delete "${name}" from ${builder}? This removes this shared contact from Opportunities, Tender/Chase-up, Open-Awarded and the builder directory.`))return;
  pending.current=true;setSaving(true);setDeleting(person.id);setDeleteError('');
  try{
   const response=await apiFetch('builder-contacts',{method:'DELETE',body:JSON.stringify({id:person.id,revision:person.revision})});
   const result=await response.json();if(!response.ok)throw Error(result.error||'Unable to delete the contact.');
   notifyBuilderContactsChanged();await onSaved();toast.success('Shared contact deleted');
  }catch(reason){
   const message=(reason as Error).message||'Unable to confirm deletion. Refresh contacts before trying again.';
   setDeleteError(message);toast.error(message);onRetry();
  }finally{pending.current=false;setSaving(false);setDeleting('');}
 }
 return <section className="group-section builder-directory" aria-label={'Contacts for '+builder}>
  <div className="register-heading"><h3>All builder contacts <span className="count-pill">{contacts.length}</span></h3><button type="button" className="secondary-btn" disabled={saving} onClick={()=>edit()}><Plus size={14}/>Add contact</button></div>
  <p className="form-hint">Available across Opportunities, Tender/Chase-up and Open-Awarded.</p>
  {loading&&<p className="muted" role="status">Loading contacts…</p>}
  {error&&<div className="builder-directory-error" role="alert"><span>{error}</span><button type="button" className="text-btn" onClick={onRetry}>Retry</button></div>}
  {deleteError&&<p className="builder-directory-error" role="alert">{deleteError}</p>}
  {contacts.length>8&&<div className="inline-search builder-directory-search"><Search size={16}/><input type="search" aria-label={'Search contacts for '+builder} placeholder="Search name, phone or email…" value={query} onChange={event=>{setQuery(event.target.value);setLimit(20)}}/></div>}
  <div className="builder-directory-list">{visible.slice(0,limit).map((person,index)=><div className="builder-directory-person" key={person.id||index}>
   <BuilderContactList contacts={[person]} compact/>
   <div className="builder-directory-actions"><button type="button" className="text-btn" disabled={saving} onClick={()=>edit(person)} aria-label={'Edit contact '+(person.name||person.emails[0]||person.phones[0]||String(index+1))}><Pencil size={14}/>Edit</button>
    {person.id&&person.canDelete===true&&<button type="button" className="text-btn builder-contact-delete" disabled={saving} onClick={()=>void deleteContact(person)} aria-label={'Delete contact '+(person.name||person.emails[0]||person.phones[0]||String(index+1))}><Trash2 size={14}/>{deleting===person.id?'Deleting…':'Delete'}</button>}
   </div>
  </div>)}</div>
  {!loading&&!error&&!visible.length&&<p className="muted">{query?'No contacts match your search.':'No contacts recorded yet. Add one here or while editing an Opportunity or Tender.'}</p>}
  {visible.length>limit&&<button type="button" className="secondary-btn" onClick={()=>setLimit(value=>value+20)}>Show more contacts</button>}
  <Dialog open={draft!==null} onOpenChange={open=>{if(!open)close()}}><DialogContent className="tender-dialog"><DialogHeader><DialogTitle>{draft?.[0]?.id?'Edit builder contact':'Add builder contact'}</DialogTitle><DialogDescription>{builder}. Changes to this person are shared wherever their contact is used.</DialogDescription></DialogHeader>
   {draft&&<form className="builder-directory-form" onSubmit={event=>void save(event)}>
    <BuilderContactEditor builder={builder} contacts={draft} availableContacts={contacts} onChange={setDraft} disabled={saving} allowRemove={false} maxContacts={1}/>
    {saveError&&<p className="builder-directory-error" role="alert">{saveError}</p>}
    <div className="dialog-actions"><button type="button" className="secondary-btn" disabled={saving} onClick={close}>Cancel</button><button type="submit" className="primary-btn" disabled={saving}>{saving?'Saving…':'Save contact'}</button></div>
   </form>}
  </DialogContent></Dialog>
 </section>;
}
