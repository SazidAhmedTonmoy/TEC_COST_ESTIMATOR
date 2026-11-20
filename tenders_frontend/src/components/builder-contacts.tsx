import {useId,useState} from 'react';
import {ExternalLink,Mail,Phone,Plus,Trash2,UserRound,X} from 'lucide-react';
import {contactHasDetails,exactContactMatches,matchSavedContact,savedContactLabel,selectSavedContact} from '@/lib/builder-contacts';
import type {BuilderContact,ContactLookupField} from '@/lib/builder-contacts';
import {outlookHref,phoneHref} from '@/lib/award-contacts';
import './builder-contacts.css';

type EditorProps={builder:string;contacts:BuilderContact[];onChange:(contacts:BuilderContact[])=>void;availableContacts?:BuilderContact[];disabled?:boolean;title?:string;allowRemove?:boolean;maxContacts?:number};
const MAX_PEOPLE=20,MAX_FIELDS=12;

export function BuilderContactEditor({builder,contacts,onChange,availableContacts=[],disabled=false,title='Contact people (optional)',allowRemove=true,maxContacts=MAX_PEOPLE}:EditorProps){
  const identity=useId(),[notice,setNotice]=useState('');
  const contactLimit=Math.max(1,Math.min(MAX_PEOPLE,maxContacts));
  const available=availableContacts.filter(contactHasDetails);
  const setPerson=(index:number,person:BuilderContact)=>onChange(contacts.map((value,i)=>i===index?person:value));
  function fillMatch(index:number,field:ContactLookupField,value:string){
    const others=new Set(contacts.filter((_,i)=>i!==index).map(person=>person.id).filter(Boolean));
    const choices=available.filter(person=>!person.id||!others.has(person.id));
    const match=matchSavedContact(contacts[index],choices,field,value);
    if(match){setPerson(index,match);setNotice('Saved contact details filled in.')}
    else if(!contacts[index].id&&exactContactMatches(choices,field,value).length>1)setNotice('More than one saved person matches. Choose the right person from Use a saved contact.');
  }
  function chooseSaved(index:string){
    if(index==='')return;const saved=available[Number(index)];if(!saved)return;
    const selected=selectSavedContact(contacts,saved,contactLimit);
    if(!selected){setNotice('Remove a person first, or choose a saved contact matching one of the unsaved people.');return}
    onChange(selected);setNotice('Saved contact details filled in.');
  }
  function fieldChanged(index:number,field:'phones'|'emails',at:number,value:string){
    const person=contacts[index],values=[...person[field]];values[at]=value;
    setPerson(index,{...person,[field]:values});setNotice('');
  }
  return <section className="bc-editor" aria-label={title+' for '+builder}>
    <div className="bc-editor-heading"><h3>{title}</h3><button type="button" className="bc-add" disabled={disabled||contacts.length>=contactLimit} onClick={()=>{onChange([...contacts,{name:'',phones:[],emails:[]}]);setNotice('')}}><Plus size={14}/>Add contact person</button></div>
    {available.length>0&&<label className="bc-saved-picker">Use a saved contact
      <select aria-label={'Use a saved contact for '+builder} disabled={disabled||contacts.length>=contactLimit&&!contacts.some(person=>!person.id)} value="" onChange={event=>chooseSaved(event.target.value)}>
        <option value="">Choose from {available.length} available contact{available.length===1?'':'s'}…</option>
        {available.map((person,index)=><option key={person.id||index} value={index} disabled={!!person.id&&contacts.some(selected=>selected.id===person.id)}>{savedContactLabel(person)}</option>)}
      </select>
    </label>}
    <p className="bc-help">Contacts are shared across Opportunities, Tender/Chase-up and Open-Awarded. Type a saved name, email or phone number to fill in matching details.</p>
    {!contacts.length&&<p className="bc-empty">No contact selected. You can add one now or later.</p>}
    {contacts.map((person,index)=>{
      const nameList=identity+'-name-'+index,phoneList=identity+'-phone-'+index,emailList=identity+'-email-'+index;
      return <section className="bc-person-editor" key={index} aria-label={'Contact '+(index+1)+' for '+builder}>
        <div className="bc-person-heading"><strong>Contact {index+1}{person.id&&<span className="bc-shared-label">Saved contact</span>}</strong>{allowRemove&&<button type="button" className="bc-remove" disabled={disabled} onClick={()=>{onChange(contacts.filter((_,i)=>i!==index));setNotice('')}}><Trash2 size={12}/>Remove person</button>}</div>
        <label className="bc-person-name">Contact person name<input aria-label={'Contact '+(index+1)+' name for '+builder} autoComplete="off" maxLength={200} list={nameList} value={person.name} disabled={disabled} onChange={event=>{setPerson(index,{...person,name:event.target.value});setNotice('')}} onBlur={event=>fillMatch(index,'name',event.target.value)} placeholder="Type a name or choose a saved contact"/></label>
        <datalist id={nameList}>{[...new Set(available.map(saved=>saved.name).filter(Boolean))].map(name=><option key={name} value={name}/>)}</datalist>
        {(['phones','emails'] as const).map(field=>{
          const phone=field==='phones',values=person[field].length?person[field]:[''],listId=phone?phoneList:emailList;
          const suggestions=[...new Set(available.flatMap(saved=>saved[field]).filter(Boolean))];
          return <div className="bc-fields" key={field}><div className="bc-field-heading"><strong>{phone?'Phone numbers':'Email addresses'}</strong><button type="button" className="bc-add" disabled={disabled||values.length>=MAX_FIELDS} onClick={()=>setPerson(index,{...person,[field]:[...values,'']})}><Plus size={12}/>{phone?'Add phone':'Add email'}</button></div>
            {values.map((value,at)=><div className="bc-field" key={at}><input aria-label={'Contact '+(index+1)+' '+(phone?'phone ':'email ')+(at+1)+' for '+builder} type={phone?'tel':'text'} inputMode={phone?'tel':'email'} autoComplete="off" maxLength={phone?45:254} list={listId} value={value} disabled={disabled} onChange={event=>fieldChanged(index,field,at,event.target.value)} onBlur={event=>fillMatch(index,phone?'phone':'email',event.target.value)} placeholder={phone?'Phone number':'Email address'}/><button type="button" disabled={disabled} aria-label={'Remove '+(phone?'phone ':'email ')+(at+1)+' from contact '+(index+1)} onClick={()=>setPerson(index,{...person,[field]:person[field].filter((_,i)=>i!==at)})}><X size={16}/></button></div>)}
            <datalist id={listId}>{suggestions.map(value=><option key={value} value={value}/>)}</datalist>
          </div>;
        })}
        {person.id&&<p className="bc-help">Changes to this saved contact apply wherever this person is used.</p>}
      </section>;
    })}
    {contacts.length>0&&allowRemove&&<p className="bc-help">Removing a person here keeps them available in the builder’s contact list.</p>}
    <span className="bc-notice" role="status" aria-live="polite">{notice}</span>
  </section>;
}

export function BuilderContactList({contacts,compact=false,emptyMessage='No contact selected.'}:{contacts:BuilderContact[];compact?:boolean;emptyMessage?:string}){
  const people=contacts.filter(contactHasDetails);
  return <div className={'bc-people'+(compact?' is-compact':'')}>
    {people.map((person,index)=><section className="bc-person" key={person.id||index}>
      <strong><UserRound size={14}/>{person.name||'Name not recorded'}</strong>
      <div className="bc-person-links">{person.phones.filter(Boolean).map((phone,i)=><a key={'p'+i} href={phoneHref(phone)} aria-label={'Call '+(person.name||'contact')+' on '+phone}><Phone size={14}/><span>{phone}</span></a>)}{person.emails.filter(Boolean).map((email,i)=><a key={'e'+i} href={outlookHref(email)} target="_blank" rel="noopener noreferrer" aria-label={'Compose Outlook email to '+email}><Mail size={14}/><span>{email}</span><ExternalLink size={12}/></a>)}</div>
    </section>)}
    {!people.length&&emptyMessage&&<p className="bc-empty">{emptyMessage}</p>}
  </div>;
}
