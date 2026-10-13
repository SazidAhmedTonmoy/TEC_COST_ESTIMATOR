import type {Submission,Chase,Reminder} from './types';
const normalize=(value:string)=>value.normalize('NFKC').toLowerCase().trim().replace(/\s+/g,' ');
// The latest submission update duplicates a chase comment. Exclude both it
// and historical chase notes on Dashboard and Project Chase-up only.
export function tenderSearchText(s:Submission,chases:Chase[],reminders:Reminder[],view:string,labels:string[]=[]){
 const excludeComments=view==='dashboard'||view==='chase-up'||view==='search';
 const fields: (keyof Submission)[]=['project','quoteNo','builder','value','status','builderStatus','pricing','region','location','contact','email','month','due','statusUpdated','submittedByTeam','remarks','createdByName','importedByName','updatedByName'];
 const chaseValues=chases.flatMap(c=>[c.date,c.method,c.author,...(excludeComments?[]:[c.note])]);
 return normalize([...fields.map(k=>s[k]),...(excludeComments?[]:[s.latest]),...labels,...chaseValues,...reminders.flatMap(r=>[r.due,r.note])].join(' '));
}
const aliases:Record<string,string>={'closed':'close','no pricing feedback':'no feedback','builder awarded':'awarded','tec won':'won'};
const terms=new Set(['open','won','lost','close','hold','awarded','unsuccessful','in progress','builder withdrawn','suspended','competitive','high','mid-range','lower','mix','nil','not recorded','no feedback']);
export function matchesTender(s:Submission,index:string,query:string){
 const q=normalize(query);if(!q)return true;
 const category=(term:string)=>{
  const target=aliases[term]||term;
  if(!terms.has(target))return null;
  if(target==='no feedback')return ['','no feedback','not recorded','not specified'].includes(normalize(s.pricing||''));
  const values=[s.status,s.builderStatus,s.pricing].map(v=>normalize(v||'not recorded'));
  return values.includes(target);
 };
 const exact=category(q);if(exact!==null)return exact;
 return q.split(' ').every(word=>category(word)??index.includes(word));
}
