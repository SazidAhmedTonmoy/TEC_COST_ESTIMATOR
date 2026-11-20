/** Shared people are scoped to one builder; projects keep their selected people. */
export type BuilderContact={id?:string;revision?:number;canDelete?:boolean;name:string;phones:string[];emails:string[]};
export type BuilderContactGroup={builder:string;contacts:BuilderContact[]};
export type ContactLookupField='name'|'email'|'phone';

export const builderKey=(value:string)=>value.normalize('NFKC').toLocaleLowerCase().replace(/[^\p{L}\p{N}_]/gu,'');
const textKey=(value:string)=>value.normalize('NFKC').trim().toLocaleLowerCase().replace(/\s+/g,' ');
export function contactPhoneKey(value:string){
  const digits=value.replace(/\D/g,'');
  // Australian domestic and international forms identify the same number.
  return digits.startsWith('0061')&&digits.length===13?'0'+digits.slice(4):digits.startsWith('61')&&digits.length===11?'0'+digits.slice(2):digits;
}
export function cloneBuilderContact(person:BuilderContact):BuilderContact{
  return {...person,name:person.name||'',phones:[...(person.phones||[])],emails:[...(person.emails||[])]};
}
export const cloneBuilderContacts=(contacts:BuilderContact[]=[])=>contacts.map(cloneBuilderContact);
export function contactsForBuilder(groups:BuilderContactGroup[]|undefined,builder:string):BuilderContact[]{
  const key=builderKey(builder);if(!key)return [];
  const result:BuilderContact[]=[];
  for(const group of groups||[]){
    if(builderKey(group.builder)!==key)continue;
    for(const person of group.contacts||[]){
      if(person.id&&result.some(item=>item.id===person.id))continue;
      result.push(person);
    }
  }
  return result;
}
export function replaceBuilderContacts(groups:BuilderContactGroup[]|undefined,builder:string,contacts:BuilderContact[]):BuilderContactGroup[]{
  const key=builderKey(builder);
  return [...(groups||[]).filter(group=>builderKey(group.builder)!==key),{builder,contacts:cloneBuilderContacts(contacts)}];
}
export const contactHasDetails=(person:BuilderContact)=>!!(person.name.trim()||person.emails.some(value=>value.trim())||person.phones.some(value=>value.trim()));
function uniqueValues(values:string[],key:(value:string)=>string){
  const seen=new Set<string>();return values.map(value=>value.trim()).filter(value=>{if(!value)return false;const normalized=key(value)||'text:'+textKey(value);if(seen.has(normalized))return false;seen.add(normalized);return true});
}
const overlaps=(left:string[],right:string[],key:(value:string)=>string)=>left.some(value=>right.some(other=>key(value)&&key(value)===key(other)));
export function exactContactMatches(available:BuilderContact[],field:ContactLookupField,value:string):BuilderContact[]{
  const key=field==='phone'?contactPhoneKey:textKey,query=key(value);if(!query)return [];
  return available.filter(person=>(field==='name'?[person.name]:field==='phone'?person.phones:person.emails).some(item=>key(item)===query));
}
/** Never guess between same-name people or overwrite conflicting typed details. */
export function matchSavedContact(draft:BuilderContact,available:BuilderContact[],field:ContactLookupField,value:string):BuilderContact|null{
  if(draft.id||!value.trim())return null;
  const matches=exactContactMatches(available,field,value);
  if(matches.length!==1)return null;
  const saved=matches[0];
  if(draft.name.trim()&&saved.name.trim()&&textKey(draft.name)!==textKey(saved.name))return null;
  const emails=draft.emails.filter(value=>value.trim()),phones=draft.phones.filter(value=>value.trim());
  if(emails.length&&saved.emails.length&&!overlaps(emails,saved.emails,textKey))return null;
  if(phones.length&&saved.phones.length&&!overlaps(phones,saved.phones,contactPhoneKey))return null;
  return {...cloneBuilderContact(saved),name:draft.name.trim()||saved.name,
    emails:uniqueValues([...emails,...saved.emails],textKey),phones:uniqueValues([...phones,...saved.phones],contactPhoneKey)};
}
/** Explicit selection resolves a matching draft before adding another person. */
export function selectSavedContact(contacts:BuilderContact[],saved:BuilderContact,maxContacts=20):BuilderContact[]|null{
  if(saved.id&&contacts.some(person=>person.id===saved.id))return cloneBuilderContacts(contacts);
  const matching=contacts.map(person=>[matchSavedContact(person,[saved],'name',person.name),...person.emails.map(email=>matchSavedContact(person,[saved],'email',email)),...person.phones.map(phone=>matchSavedContact(person,[saved],'phone',phone))].find(Boolean));
  const candidates=matching.flatMap((person,at)=>person?[at]:[]);
  if(candidates.length===1){const at=candidates[0];return contacts.map((person,index)=>index===at?matching[at]!:cloneBuilderContact(person))}
  const empty=contacts.findIndex(person=>!person.id&&!contactHasDetails(person));
  if(empty>=0)return contacts.map((person,index)=>index===empty?cloneBuilderContact(saved):cloneBuilderContact(person));
  if(contacts.length<maxContacts)return [...cloneBuilderContacts(contacts),cloneBuilderContact(saved)];
  return null;
}
export function savedContactLabel(person:BuilderContact){
  const identity=person.name.trim()||person.emails[0]||person.phones[0]||'Unnamed contact';
  const details=[person.name.trim()?person.emails[0]:'',person.phones[0]].filter(Boolean);
  return [identity,...details].join(' · ');
}

function phoneSearchVariants(value:string){
  const digits=value.replace(/\D/g,''),domestic=contactPhoneKey(value);
  const variants=new Set([digits,domestic]);
  if(/^0\d{9}$/.test(domestic)){
    const international='61'+domestic.slice(1);
    variants.add(international);variants.add('+'+international);variants.add('00'+international);
  }
  return [...variants].filter(Boolean);
}

/** Search every saved person, including numbers typed without their formatting. */
export function builderContactSearchText(builder:string,contacts:BuilderContact[]):string{
  return textKey([builder,...contacts.flatMap(person=>[
    person.name,...person.emails,...person.phones,...person.phones.flatMap(phoneSearchVariants),
  ])].join(' '));
}

export function matchesBuilderContactQuery(builder:string,contacts:BuilderContact[],query:string):boolean{
  const text=builderContactSearchText(builder,contacts),words=textKey(query).split(' ').filter(Boolean);
  const phoneWord=(word:string)=>/^[+\d()./-]+$/.test(word);
  for(let index=0;index<words.length;index++){
    if(!phoneWord(words[index])){if(!text.includes(words[index]))return false;continue}
    const run=[words[index]];
    while(index+1<words.length&&phoneWord(words[index+1]))run.push(words[++index]);
    const value=run.join(' '),number=contactPhoneKey(value);
    // Keep numeric company names (e.g. "24 7") searchable too. Requiring one
    // contiguous phone sequence avoids matching pieces of unrelated numbers.
    if(!text.includes(value)&&(!number||!text.includes(number)))return false;
  }
  return true;
}
