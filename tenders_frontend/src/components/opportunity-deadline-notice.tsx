import {useEffect,useMemo,useState} from 'react';
import {TriangleAlert} from 'lucide-react';
import {apiFetch} from '../main';
import {createDeadlineLoadLookup,deadlineLoadInitialState,deadlineLoadKey,deadlineLoadMessage,deadlineTeamGroupMessage} from '@/lib/opportunity-deadline-load';

export function OpportunityDeadlineNotice({due,excludeId}:{due:string;excludeId?:string}){
  const [state,setState]=useState(()=>deadlineLoadInitialState(due,excludeId));
  const lookup=useMemo(()=>createDeadlineLoadLookup(apiFetch,setState),[]);
  useEffect(()=>{lookup.check(due,excludeId);return()=>lookup.cancel();},[lookup,due,excludeId]);
  // A date change renders before its effect runs; never show the previous count.
  const current=state.key===deadlineLoadKey(due,excludeId)?state:deadlineLoadInitialState(due,excludeId);
  const message=current.status==='ready'?deadlineLoadMessage(current.count):'';
  return <span id="op-deadline-load" className={'op-deadline-load'+(message?' op-deadline-load-warning':'')} role="status" aria-live="polite" aria-atomic="true">
    {message?<><TriangleAlert size={15} aria-hidden="true"/><span className="op-deadline-load-content"><span>{message}</span>{!!current.teamGroups?.length&&<span className="op-deadline-teams" role="group" aria-label="Projects by assigned team">{current.teamGroups.map(group=><span key={JSON.stringify(group.teamNames)}>{deadlineTeamGroupMessage(group)}</span>)}</span>}</span></>:current.status==='loading'?'Checking other closing dates…':current.status==='error'?'Could not check other closing dates. You can still save.':null}
  </span>;
}
