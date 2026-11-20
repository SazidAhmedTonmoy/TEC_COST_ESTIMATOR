import type {Submission,Chase} from './types';
export const projectKey=(name:string)=>name.normalize('NFKC').trim().replace(/\s+/g,' ').toLowerCase();
export function groupProjects(rows:Submission[]){
 const groups=new Map<string,{name:string;rows:Submission[]}>();
 for(const row of rows){const key=projectKey(row.project);const group=groups.get(key)||{name:row.project.trim(),rows:[]};group.rows.push(row);groups.set(key,group)}
 return [...groups.values()];
}
export const boundedPage=(page:number,total:number,size=20)=>Math.max(1,Math.min(page,Math.max(1,Math.ceil(total/size))));
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

/** Sort complete project groups, then each builder submission within its group.
 * The first row supplies the group's lowest/highest meaningful sort value;
 * compareValues keeps missing values last in both directions. */
export function sortGroupedSubmissions(rows:Submission[],valueFor:(row:Submission)=>unknown,direction:'asc'|'desc',priorityFor:(row:Submission)=>number=()=>0):Submission[]{
 const primary=(a:Submission,b:Submission)=>priorityFor(b)-priorityFor(a)||compareValues(valueFor(a),valueFor(b),direction);
 const within=(a:Submission,b:Submission)=>primary(a,b)||compareValues(a.builder,b.builder,'asc')||a.id.localeCompare(b.id);
 const groups=groupProjects(rows).map(group=>({...group,rows:[...group.rows].sort(within)}));
 groups.sort((a,b)=>{
  const aKey=projectKey(a.name),bKey=projectKey(b.name);
  return primary(a.rows[0],b.rows[0])||compareValues(aKey,bKey,'asc')||(aKey<bKey?-1:aKey>bKey?1:0);
 });
 return groups.flatMap(group=>group.rows);
}

/** A page targets the usual row count but never cuts through one project.
 * An unusually large project receives a page of its own, with every builder. */
export function paginateProjectRows(rows:Submission[],targetSize=20):Submission[][]{
 const size=Number.isFinite(targetSize)?Math.max(1,Math.floor(targetSize)):20;
 const pages:Submission[][]=[];
 let current:Submission[]=[];
 for(const group of groupProjects(rows)){
  if(current.length&&current.length+group.rows.length>size){pages.push(current);current=[];}
  current.push(...group.rows);
  if(current.length>=size){pages.push(current);current=[];}
 }
 if(current.length)pages.push(current);
 return pages;
}
