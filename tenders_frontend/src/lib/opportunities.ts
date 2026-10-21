import {apiFetch} from '../main';
export type Opportunity = {
 id:string; project:string; quoteNo:string; scope:string; category:string; budget:string;
 location:string; distance:string; notes:string; builders:string[]; region:string; deadline:string;
 teamId:number|null; teamName:string; editorUsers:number[]; editorTeams:number[];
 creatorId:number; creatorName:string; status:string; revision:number; createdAt:string; updatedAt:string;
 canManage:boolean; canEdit:boolean; canApprove:boolean; canReject:boolean;
};
export type OpportunityList = {items:Opportunity[]; total:number; page:number; counts:Record<string,number>;
 teams:{id:number;name:string;count:number}[]; users:{id:number;name:string;teamId:number|null}[];
 regions:string[]; builders:string[]; myTeamId:number|null};
export type OpportunityEvent = {id:number; action:string;actor_name:string;created_at:string;effective_at:string;details:Record<string,any>};
export const opportunityLabels:Record<string,string>={awaiting:'Awaiting approval',approved:'Approved',rejected:'Rejected',expired:'Expired',deleted:'Deleted'};
export const opportunityDate=(s:string)=>s?new Date(s.slice(0,10)+'T12:00:00').toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'}):'No deadline';
export async function opportunityRequest(path='',body?:unknown,signal?:AbortSignal){
 const r=await apiFetch('opportunities'+path,{method:body===undefined?'GET':'POST',...(body===undefined?{}:{body:JSON.stringify(body)}),signal});
 const data=await r.json();if(!r.ok)throw Error(data.error||'Unable to load opportunities');return data;
}
