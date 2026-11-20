import {builderKey,type BuilderContact,type BuilderContactGroup} from './builder-contacts';
import type {Submission} from './types';

/** Structured contacts are shared across Tender and Open-Awarded. The legacy
 * fields remain a fallback for older bootstrap responses and imports. */
export function submissionContacts(s:Pick<Submission,'contacts'|'contact'|'email'>):BuilderContact[]{
 if(Array.isArray(s.contacts))return s.contacts.map(person=>({...person,emails:[...person.emails],phones:[...person.phones]}));
 const name=s.contact||'',emails=(s.email||'').split(/[,;\n]+/).map(value=>value.trim()).filter(Boolean);
 return name||emails.length?[{name,emails,phones:[]}]:[];
}

/** Keep IDs while the builder field is being typed. Only a real change of
 * company at save time turns that company's people into independent copies. */
export function contactsForSubmissionBuilder(contacts:BuilderContact[],builder:string,directory:BuilderContactGroup[],originalBuilder='',originalContacts:BuilderContact[]=[]):BuilderContact[]{
 const owners=new Map<string,string>();
 for(const person of originalContacts)if(person.id)owners.set(person.id,builderKey(originalBuilder));
 for(const group of directory)for(const person of group.contacts)if(person.id)owners.set(person.id,builderKey(group.builder));
 const target=builderKey(builder);
 return contacts.map(person=>{
  const copy={...person,emails:[...person.emails],phones:[...person.phones]};
  if(person.id&&owners.has(person.id)&&owners.get(person.id)!==target){delete copy.id;delete copy.revision;}
  return copy;
 });
}
