import type {Opportunity} from './opportunity-types';

export type OpportunityManagement={
  id:string;revision:number;project:string;status:Opportunity['status'];
  kind:'assign'|'access';origin:'card'|'details';teams:number[];users:number[];
};

/** A card offers initial assignment only; reassignment belongs in details. */
export function canAssignOpportunityFromCard(item:Pick<Opportunity,'deletedAt'|'permissions'|'assignedTeamIds'|'assignedUserIds'>):boolean{
  return !item.deletedAt&&item.permissions.assign===true&&
    !(item.assignedTeamIds||[]).length&&!(item.assignedUserIds||[]).length;
}

/** Keep the target and revision independent of a refreshed detail sheet. */
export function opportunityManagementDraft(item:Opportunity,kind:OpportunityManagement['kind'],origin:OpportunityManagement['origin']='details'):OpportunityManagement{
  return {id:item.id,revision:item.revision,project:item.project,status:item.status,kind,origin,
    teams:[...(kind==='assign'?item.assignedTeamIds:item.editorTeamIds)||[]],
    users:[...(kind==='assign'?item.assignedUserIds:item.editorUserIds)||[]]};
}

export function opportunityManagementPayload(draft:OpportunityManagement){
  return {id:draft.id,revision:draft.revision,...(draft.kind==='assign'?
    {assignedTeamIds:[...draft.teams],assignedUserIds:[...draft.users]}:
    {editorTeamIds:[...draft.teams],editorUserIds:[...draft.users]})};
}
