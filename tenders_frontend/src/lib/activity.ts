/** One pass over submissions; zero-fill gaps without adding undated records. */
export function activityMonths(rows:{due:string}[]){
 const counts=new Map<string,number>();
 for(const row of rows){const month=row.due?.slice(0,7);if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(month||''))continue;counts.set(month,(counts.get(month)||0)+1)}
 const keys=[...counts.keys()].sort();if(!keys.length)return [];
 const [fy,fm]=keys[0].split('-').map(Number),[ly,lm]=keys[keys.length-1].split('-').map(Number);
 const result:{month:string;count:number}[]=[];
 for(let index=fy*12+fm-1;index<=ly*12+lm-1;index++){const month=`${String(Math.floor(index/12)).padStart(4,'0')}-${String(index%12+1).padStart(2,'0')}`;result.push({month,count:counts.get(month)||0})}
 return result;
}
