export type DeadlineTeamGroup={teamNames:string[];count:number};
export type DeadlineLoadState={key:string;due:string;status:'idle'|'loading'|'ready'|'error';count:number|null;teamGroups:DeadlineTeamGroup[]|null};
type FetchDeadline=(path:string,options:{signal:AbortSignal})=>Promise<Pick<Response,'ok'|'json'>>;

export const deadlineLoadKey=(due:string,excludeId='')=>JSON.stringify([due,excludeId]);
export function validOpportunityDeadline(due:string):boolean{
  if(!/^\d{4}-\d{2}-\d{2}$/.test(due)||due.startsWith('0000'))return false;
  const time=Date.parse(due+'T00:00:00Z');
  return Number.isFinite(time)&&new Date(time).toISOString().slice(0,10)===due;
}
export function deadlineLoadInitialState(due:string,excludeId=''):DeadlineLoadState{
  return {key:deadlineLoadKey(due,excludeId),due,status:validOpportunityDeadline(due)?'loading':'idle',count:null,teamGroups:null};
}
export function deadlineLoadMessage(count:number|null):string{
  return count&&Number.isSafeInteger(count)&&count>0?`${count} other project${count===1?'':'s'} ${count===1?'has':'have'} this closing date.`:'';
}

export function deadlineTeamGroupMessage(group:DeadlineTeamGroup):string{
  return `${group.teamNames.length?group.teamNames.join(' + '):'No team assigned'}: ${group.count}`;
}

/** Older servers can return the total alone; supplied groups must reconcile. */
export function deadlineTeamGroups(value:unknown,total:number):DeadlineTeamGroup[]|null{
  if(value===undefined)return null;
  if(!Array.isArray(value))throw Error('Invalid deadline team groups');
  const groups:DeadlineTeamGroup[]=[],seen=new Set<string>();let counted=0;
  for(const raw of value){
    if(!raw||typeof raw!=='object'||Array.isArray(raw)||!Array.isArray(raw.teamNames)||
      !raw.teamNames.every((name:unknown)=>typeof name==='string'&&name.trim())||
      !Number.isSafeInteger(raw.count)||raw.count<=0)throw Error('Invalid deadline team group');
    const teamNames=raw.teamNames.map((name:string)=>name.trim());
    const key=JSON.stringify([...teamNames].sort());
    if(new Set(teamNames).size!==teamNames.length||seen.has(key))throw Error('Duplicate deadline team group');
    seen.add(key);counted+=raw.count;
    if(!Number.isSafeInteger(counted)||counted>total)throw Error('Invalid deadline team count');
    groups.push({teamNames,count:raw.count});
  }
  if(counted!==total)throw Error('Incomplete deadline team count');
  return groups;
}

/** Cancel timers and ignore superseded responses, even if fetch ignores abort. */
export function createDeadlineLoadLookup(fetchDeadline:FetchDeadline,changed:(state:DeadlineLoadState)=>void,delay=300){
  let timer:ReturnType<typeof setTimeout>|undefined;
  let request:AbortController|null=null;
  let generation=0;
  const cancel=()=>{generation++;if(timer!==undefined)clearTimeout(timer);timer=undefined;request?.abort();request=null;};
  const check=(due:string,excludeId='')=>{
    cancel();const version=generation;const initial=deadlineLoadInitialState(due,excludeId);changed(initial);
    if(initial.status==='idle')return;
    const controller=new AbortController();request=controller;
    const current=()=>version===generation&&!controller.signal.aborted;
    timer=setTimeout(async()=>{
      timer=undefined;
      try{
        const params=new URLSearchParams({due});if(excludeId)params.set('excludeId',excludeId);
        const response=await fetchDeadline('opportunities/deadline-load?'+params,{signal:controller.signal});
        const data=await response.json();
        if(!current())return;
        if(!response.ok||data?.due!==due||!Number.isSafeInteger(data?.count)||data.count<0)throw Error('Deadline lookup unavailable');
        const teamGroups=deadlineTeamGroups(data.teamGroups,data.count);
        changed({...initial,status:'ready',count:data.count,teamGroups});
      }catch{
        if(current())changed({...initial,status:'error'});
      }finally{if(current())request=null;}
    },delay);
  };
  return {check,cancel};
}
