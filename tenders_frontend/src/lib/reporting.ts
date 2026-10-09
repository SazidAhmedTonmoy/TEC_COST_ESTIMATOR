import type {Submission,Chase} from './types';
export const projectKey=(name:string)=>name.normalize('NFKC').trim().toLocaleLowerCase();
export function tenderSummary(rows:Submission[],chases:Chase[]=[]){
 const projects=new Map<string,number>();const ids=new Set(rows.map(s=>s.id));
 for(const s of rows){const key=projectKey(s.project);projects.set(key,Math.max(projects.get(key)||0,s.value||0));}
 return {projects:projects.size,submissions:rows.length,builders:new Set(rows.map(s=>s.builder)).size,value:[...projects.values()].reduce((a,b)=>a+b,0),chases:chases.filter(c=>ids.has(c.submissionId)).length};
}
export function compareValues(a:unknown,b:unknown,dir:'asc'|'desc'){
 const empty=(v:unknown)=>v==null||v==='';if(empty(a)||empty(b))return empty(a)===empty(b)?0:empty(a)?1:-1;
 const result=typeof a==='number'&&typeof b==='number'?a-b:String(a).localeCompare(String(b),'en',{numeric:true,sensitivity:'base'});
 return dir==='desc'?-result:result;
}
export function monthlySummary(rows:Submission[],chases:Chase[],month:string){
 const due=rows.filter(s=>s.due?.startsWith(month));const ids=new Set(rows.map(s=>s.id));
 return {...tenderSummary(due),chases:chases.filter(c=>ids.has(c.submissionId)&&c.date?.startsWith(month)).length};
}
