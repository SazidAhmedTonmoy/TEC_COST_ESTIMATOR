import {builderKey,cloneBuilderContacts,contactsForBuilder,replaceBuilderContacts,contactHasDetails,contactPhoneKey,matchSavedContact} from './builder-contacts';
import type {BuilderContact,BuilderContactGroup} from './builder-contacts';

export type DetectedContact=BuilderContact&{builder:string};
const unique=(values:string[],key:(value:string)=>string)=>[...new Map(values.map(v=>v.trim()).filter(Boolean).map(v=>[key(v),v])).values()];
const emailKey=(value:string)=>value.trim().toLowerCase();
const nameKey=(value:string)=>value.normalize('NFKC').trim().toLowerCase().replace(/\s+/g,' ');
export function validateDetectedContact(row:DetectedContact):string{
  if(!row.builder.trim()||!builderKey(row.builder))return 'Enter a builder name.';
  if(row.builder.length>500||row.name.length>200)return 'Builder or contact name is too long.';
  if(/@|^[a-z0-9.-]+\.(?:com|net|org|au|co|io|uk|nz)$/i.test(row.name.trim()))return 'This looks like an email address or fragment. Move it to Email addresses or correct the name.';
  if(row.phones.length>12||row.emails.length>12)return 'Choose up to 12 phone numbers and email addresses.';
  if(row.phones.some(v=>v.trim()&&(!/^[+0-9(). /-]{5,45}$/.test(v.trim())||!contactPhoneKey(v))))return 'Check the phone number.';
  if(row.emails.some(v=>v.trim()&&(v.length>254||!/^\S+@[^\s@]+\.[^\s@]+$/.test(v.trim()))))return 'Check the email address.';
  return '';
}
function compatibleMatch(person:BuilderContact,available:BuilderContact[]):BuilderContact|null{
  const candidates=[matchSavedContact(person,available,'name',person.name),...person.phones.map(v=>matchSavedContact(person,available,'phone',v)),...person.emails.map(v=>matchSavedContact(person,available,'email',v))].filter((p):p is BuilderContact=>!!p);
  if(!candidates.length)return null;
  const identities=new Set(candidates.map(p=>p.id||JSON.stringify(p)));
  return identities.size===1?candidates[0]:null;
}
/** Imports only into the unsaved Opportunity form. Never discards a selected person
 * or edits a different builder. Shared IDs and their revisions remain intact. */
export function mergeDetectedContacts(current:{builders:string[];builderContacts:BuilderContactGroup[]},rows:DetectedContact[],knownBuilders:string[],directory:BuilderContactGroup[]){
  const builders=[...current.builders];let builderContacts=current.builderContacts.map(g=>({builder:g.builder,contacts:cloneBuilderContacts(g.contacts)}));
  let added=0,reused=0;
  for(const row of rows){
    const error=validateDetectedContact(row);if(error)throw Error(error);
    const key=builderKey(row.builder);const builder=builders.find(v=>builderKey(v)===key)||knownBuilders.find(v=>builderKey(v)===key)||row.builder.trim();
    if(!builders.some(v=>builderKey(v)===key))builders.push(builder);
    if(builders.length>100||builders.join('\n').length>20000)throw Error('Choose up to 100 builders per opportunity.');
    const person:BuilderContact={name:row.name.trim(),phones:unique(row.phones,contactPhoneKey),emails:unique(row.emails,emailKey)};
    if(!contactHasDetails(person))continue;
    const selected=contactsForBuilder(builderContacts,builder);
    const saved=compatibleMatch(person,contactsForBuilder(directory,builder));
    const matches=selected.map((value,index)=>({value,index,match:compatibleMatch(person,[value])})).filter(candidate=>candidate.match);
    const savedIndex=saved?.id?selected.findIndex(v=>v.id===saved.id):-1;
    if(savedIndex>=0||matches.length===1){
      const at=savedIndex>=0?savedIndex:matches[0].index;
      const previous=selected[at],match=compatibleMatch(person,[previous]);
      // Keep existing draft edits. Add compatible missing fields without
      // rewriting a shared name or dropping its revision/old values.
      if(match){
        const phones=unique([...person.phones,...previous.phones],contactPhoneKey),emails=unique([...person.emails,...previous.emails],emailKey);
        if(phones.length>12||emails.length>12)throw Error('Contact has too many phone numbers or emails. Review this person manually.');
        selected[at]={...previous,name:previous.name||person.name,phones,emails};
        builderContacts=replaceBuilderContacts(builderContacts,builder,selected);
      }
      reused++;continue;
    }
    if(matches.length>1)throw Error('More than one selected person matches a detected contact. Review those people manually.');
    const next=saved||person;
    const duplicate=selected.some(v=>nameKey(v.name)===nameKey(next.name)&&JSON.stringify(v.phones.map(contactPhoneKey).sort())===JSON.stringify(next.phones.map(contactPhoneKey).sort())&&JSON.stringify(v.emails.map(emailKey).sort())===JSON.stringify(next.emails.map(emailKey).sort()));
    if(duplicate){reused++;continue;}
    const empty=selected.findIndex(v=>!v.id&&!contactHasDetails(v));
    if(empty>=0)selected[empty]=next;
    else{if(selected.length>=20)throw Error('Choose up to 20 contacts per builder. Remove unused people first.');selected.push(next)}
    builderContacts=replaceBuilderContacts(builderContacts,builder,selected);
    if(saved)reused++;else added++;
  }
  return {builders,builderContacts,added,reused};
}
