import type {Submission} from './types';
const normalize=(value:string)=>value.normalize('NFKC').toLowerCase().trim().replace(/\s+/g,' ');
const aliases:Record<string,string>={'closed':'close','no feedback':'nil','no pricing feedback':'nil','builder awarded':'awarded','tec won':'won'};
const terms=new Set(['open','won','lost','close','hold','awarded','unsuccessful','in progress','builder withdrawn','suspended','competitive','high','mid-range','lower','mix','nil','not recorded']);
export function matchesTender(s:Submission,index:string,query:string){
 const q=normalize(query);if(!q)return true;
 const category=(term:string)=>{
  const target=aliases[term]||term;
  if(!terms.has(target))return null;
  const values=[s.status,s.builderStatus,s.pricing].map(v=>normalize(v||'not recorded'));
  return values.includes(target);
 };
 const exact=category(q);if(exact!==null)return exact;
 return q.split(' ').every(word=>category(word)??index.includes(word));
}
