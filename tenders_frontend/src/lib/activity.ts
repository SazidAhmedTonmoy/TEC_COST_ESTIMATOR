const projectKey=(name:string)=>name.normalize('NFKC').trim().toLocaleLowerCase();
/** Unique projects by deadline month; recorded chase events by their own dates. */
export function activityMonths(rows:{id?:string;project?:string;due:string}[],chases:{submissionId:string;date:string}[]=[]){
 const projects=new Map<string,Set<string>>(),chaseCounts=new Map<string,number>();
 const valid=(m:string)=>/^\d{4}-(0[1-9]|1[0-2])$/.test(m||'');
 rows.forEach((row,index)=>{const month=row.due?.slice(0,7);if(!valid(month))return;const set=projects.get(month)||new Set<string>();set.add(row.project?projectKey(row.project):String(row.id??index));projects.set(month,set)});
 const ids=new Set(rows.map(s=>s.id));
 for(const c of chases){const month=c.date?.slice(0,7);if(valid(month)&&ids.has(c.submissionId))chaseCounts.set(month,(chaseCounts.get(month)||0)+1)}
 const keys=[...new Set([...projects.keys(),...chaseCounts.keys()])].sort();if(!keys.length)return [];
 const [fy,fm]=keys[0].split('-').map(Number),[ly,lm]=keys.at(-1)!.split('-').map(Number);
 const result:{month:string;count:number;chases:number}[]=[];
 for(let index=fy*12+fm-1;index<=ly*12+lm-1;index++){const month=`${String(Math.floor(index/12)).padStart(4,'0')}-${String(index%12+1).padStart(2,'0')}`;result.push({month,count:projects.get(month)?.size||0,chases:chaseCounts.get(month)||0})}
 return result;
}

/** Builder awards grouped by submission deadline, not an inferred award date. */
export function awardActivityMonths(rows:{id?:string;project?:string;due:string;builderStatus:string}[]){
 const months=activityMonths(rows);
 return months.map(m=>({month:m.month,count:m.count,awards:rows.filter(s=>s.due?.startsWith(m.month)&&s.builderStatus==='Awarded').length}));
}
