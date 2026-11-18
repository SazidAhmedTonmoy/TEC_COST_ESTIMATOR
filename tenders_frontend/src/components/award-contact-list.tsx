import {AlertTriangle,ExternalLink,Mail,Phone,UserRound} from 'lucide-react';
import {awardedContacts,missingAwardContact,outlookHref,phoneHref} from '@/lib/award-contacts';
import type {Submission} from '@/lib/types';
/** Shared presentation for Open-Awarded cards, calendar and the Tender detail drawer. */
export function AwardContactList({submission,compact=false,showWarning=true}:{submission:Submission;compact?:boolean;showWarning?:boolean}){
 const contacts=awardedContacts(submission);
 return <div className={'oa-contact-people'+(compact?' is-compact':'')}>
  {contacts.map((person,index)=><section className="oa-contact-person" key={index} aria-label={'Contact '+(index+1)}>
    <strong className="oa-person"><UserRound size={14}/>{person.name||'Name not recorded'}</strong>
    <div className="oa-contact-links">
     {person.phones.map((phone,i)=><a key={'p'+i} href={phoneHref(phone)} aria-label={'Call '+(person.name||'contact')+' on '+phone}><Phone size={14}/><span>{phone}</span></a>)}
     {person.emails.map((email,i)=><a key={'e'+i} href={outlookHref(email)} target="_blank" rel="noopener noreferrer" aria-label={'Compose Outlook email to '+email}><Mail size={14}/><span>{email}</span><ExternalLink size={12}/></a>)}
    </div>
    {showWarning&&(!person.name||!person.phones.length||!person.emails.length)&&<p className="oa-contact-warning" role="note"><AlertTriangle size={13}/> Missing {['name',!person.phones.length?'phone number':'',!person.emails.length?'email address':''].filter(Boolean).join(', ').replace(/^, /,'')} for this contact.</p>}
   </section>)}
  {showWarning&&!contacts.length&&<p className="oa-contact-warning" role="note"><AlertTriangle size={14}/> No awarded-project contacts recorded — add a contact person.</p>}
  {!showWarning&&missingAwardContact(submission)&&!contacts.length&&<span className="oa-contact-unrecorded">No contact recorded</span>}
 </div>;
}
