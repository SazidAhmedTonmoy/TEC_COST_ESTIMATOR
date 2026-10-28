export type OpportunityStatus = 'pending' | 'approved' | 'rejected' | 'expired';
export type OpportunityTeam = {id:number; name:string};
export type OpportunityUser = {id:number; name:string; teamId?:number|null; role?:string};
export type OpportunityRegion = {code:string; origin:string; timezone?:string};
export type Opportunity = {
  id:string; project:string; builders:string[]; region:string; location:string;
  due:string; workingScope:string; remarks:string; link?:string;
  value:number|null; distanceKm:number|null; distanceOrigin:string;
  category?:string; budget?:string; addedDate?:string; sourceData?:Record<string,unknown>;sourceStatus?:OpportunityStatus;
  status:OpportunityStatus; assignedTeamIds:number[]; assignedUserIds:number[];
  editorTeamIds:number[]; editorUserIds:number[]; createdBy:number; createdByName:string;
  createdAt:string; updatedAt?:string; updatedByName?:string; approvedByName?:string; rejectedByName?:string;
  decisionReason?:string; decisionByName?:string; decisionAt?:string; deletedAt?:string;
  quoteStatus?:'quoted'|'not_quoted'; submissionIds?:string[]; quotedValue?:number;
  quoteNote?:string; quoteNo?:string; submittedDate?:string; quotedAt?:string;
  quotedBy?:number; quotedByName?:string; quotedBuilders?:string[]; submittedByTeamId?:number|null;
  revision:number; permissions:{edit:boolean; manage:boolean; approve:boolean; quote?:boolean};
};
export type OpportunityActivity = {
  id:number; action:string; actorId:number; actorName:string; createdAt:string;
  details:Record<string,unknown>;
};
export type OpportunityDetail = {opportunity:Opportunity; activity:OpportunityActivity[];activityTotal?:number;hasMoreActivity?:boolean;nextActivityCursor?:number|null};
export type OpportunityList = {
  items:Opportunity[]; latestOpportunity?:Opportunity|null; total:number; page:number; pageSize:number;
  counts:Record<OpportunityStatus|'all',number>; regions:OpportunityRegion[];
  teams:OpportunityTeam[]; users:OpportunityUser[]; builders:string[];
  teamCounts:{id:number; name:string; count:number}[]; canApprove:boolean;
};
export type TenderNotification = {
  id:string; kind:string; title:string; message:string; createdAt:string; read:boolean;
  opportunityId?:string; submissionId?:string; due?:string;
};
export type NotificationList = {
  items:TenderNotification[]; unread:number; unreadCount:number; total:number;
  page?:number; pageSize?:number;
};
export const opportunityStatusLabels:Record<OpportunityStatus,string> = {
  pending:'Awaiting approval', approved:'Approved', rejected:'Rejected', expired:'Expired',
};
export function opportunityDate(value?:string) {
  if (!value) return 'No deadline';
  return new Date(value.slice(0,10)+'T12:00:00').toLocaleDateString('en-AU', {day:'numeric',month:'short',year:'numeric'});
}
