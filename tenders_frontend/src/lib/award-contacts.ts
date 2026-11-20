import type {AwardContact,Submission} from './types';
/** Older records still use one name/email/phone. Do not mutate those records. */
export function awardedContacts(s:Pick<Submission,'awardContacts'|'awardContactName'|'awardContactEmail'|'awardContactPhone'>):AwardContact[]{
 if(Array.isArray(s.awardContacts))return s.awardContacts.map(person=>({...person,name:person.name||'',emails:[...(person.emails||[])],phones:[...(person.phones||[])]}));
 const name=s.awardContactName||'',email=s.awardContactEmail||'',phone=s.awardContactPhone||'';
 return name||email||phone?[{name,emails:email?email.split(/[,;\n]+/).map(v=>v.trim()).filter(Boolean):[],phones:phone?phone.split(/(?:\s{2,}|[;\n]+)/).map(v=>v.trim()).filter(Boolean):[]}]:[];
}
export function missingAwardContact(s:Submission):boolean{
 const contacts=awardedContacts(s);
 return !contacts.length||contacts.some(c=>!c.name.trim()||!c.emails.length||!c.phones.length);
}
export function searchAwardContacts(s:Submission):string{
 return awardedContacts(s).flatMap(c=>[c.name,...c.emails,...c.phones]).join(' ');
}
export const phoneHref=(phone:string)=>'tel:'+phone.replace(/[^\d+]/g,'').replace(/(?!^)\+/g,'');
export const outlookHref=(email:string)=>'https://outlook.office.com/mail/deeplink/compose?to='+encodeURIComponent(email);
