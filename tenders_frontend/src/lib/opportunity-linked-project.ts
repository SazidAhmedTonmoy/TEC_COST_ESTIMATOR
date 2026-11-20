import type {Opportunity,OpportunityDetail} from './opportunity-types';

type ProjectLinks=Pick<Opportunity,'estimatorProjectId'|'submissionIds'|'quoteStatus'|'linkedAt'|'deletedAt'>;
export type OpportunityProjectTarget=
  |{kind:'estimator';id:number;href:string}
  |{kind:'tender';submissionId:string}
  |{kind:'unavailable';message:string};
const validEstimateId=(value:unknown):value is number=>typeof value==='number'&&Number.isSafeInteger(value)&&value>0;

/** Navigation is available independently of permission to change a link. */
export function hasOpportunityProjectLink(item:ProjectLinks):boolean{
  return !item.deletedAt&&(validEstimateId(item.estimatorProjectId)||Boolean(item.linkedAt)||item.quoteStatus==='quoted'||Boolean(item.submissionIds?.some(id=>typeof id==='string'&&id.trim())));
}

/** Resolve only the links in a freshly loaded detail response, never a name match. */
export function opportunityProjectTarget(detail:Pick<OpportunityDetail,'opportunity'|'journey'>):OpportunityProjectTarget{
  const item=detail.opportunity,journey=detail.journey;
  if(item.deletedAt)return {kind:'unavailable',message:'This opportunity has been deleted. Its linked project cannot be opened from this card.'};
  const estimate=journey?.estimatorProject;
  if(item.estimatorProjectId!=null||estimate){
    if(validEstimateId(item.estimatorProjectId)&&estimate?.available===true&&estimate.id===item.estimatorProjectId)return {kind:'estimator',id:estimate.id,href:'/#/estimate/'+estimate.id};
    return {kind:'unavailable',message:'The linked Estimator project is no longer available. Open View details to change or remove the link.'};
  }
  const submissionId=journey?.nextAction.submissionId;
  if(submissionId&&item.submissionIds?.includes(submissionId)&&journey!.quotation.submissionCount>0&&!journey!.quotation.missingSubmissions)return {kind:'tender',submissionId};
  return {kind:'unavailable',message:'No available project is linked to this opportunity. Open View details to review its links.'};
}
