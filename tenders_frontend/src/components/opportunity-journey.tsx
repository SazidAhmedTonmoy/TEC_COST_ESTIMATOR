import {ArrowUpRight,Check,ChevronRight,Clock,FileText,GitBranch,Link2,MessageSquareText,Target} from 'lucide-react';
import type {Opportunity,OpportunityJourney} from '@/lib/opportunity-types';
import {opportunityStatusLabels} from '@/lib/opportunity-types';

const aud = new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD',minimumFractionDigits:2,maximumFractionDigits:2});
const shortDate=(value?:string)=>{
  if(!value)return '';
  const date=new Date(value.length===10?value+'T12:00:00':value);
  return Number.isNaN(date.getTime())?value:date.toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'});
};

type Props={item:Opportunity; journey:OpportunityJourney; onChase:(id:string)=>void; onChooseEstimator:()=>void; onCreateEstimate:()=>void};

export default function OpportunityJourneyView({item,journey,onChase,onChooseEstimator,onCreateEstimate}:Props){
 const quoted=journey.quotation.status==='quoted';
 const finished=journey.outcome.completed;
 const decisionsDone=['approved','rejected','expired'].includes(item.status);
 const stopped=['rejected','expired'].includes(item.status);
 const records=[
  {name:'Opportunity created',done:true,active:false,detail:`Registered ${shortDate(journey.created.at)}${journey.created.by?' · '+journey.created.by:''}`},
  {name:'Decision',done:decisionsDone,active:['pending','review'].includes(item.status),detail:opportunityStatusLabels[item.status]||item.status},
  {name:'Quotation',done:quoted,active:item.status==='approved'&&!quoted,detail:quoted?(journey.quotation.linkedTenderName?'Tender linked · ':'Quoted · ')+(journey.quotation.value==null?'Value not recorded':aud.format(journey.quotation.value)):journey.quotation.status==='not_quoted'?'Not quoted':'Not recorded'},
  {name:'Project Chase-up',done:journey.chaseUp.started&&finished,active:journey.chaseUp.started&&!finished,detail:journey.chaseUp.started?`${journey.quotation.submissionCount} submission(s) · ${journey.chaseUp.updates} update(s)`:'Not started'},
  {name:'Final outcome',done:finished,active:false,detail:journey.outcome.label},
 ];
 return <section className="op-journey" aria-label="Project journey">
   <header className="op-journey-header"><div><span className="op-journey-eyebrow">PROJECT WORKFLOW</span><h3>Project journey</h3></div><span className="op-journey-current">{journey.position}</span></header>
   <ol className="op-journey-steps">{records.map((step,index)=>{
    const state=step.done?'done':step.active?'active':stopped?'stopped':'upcoming';
    return <li className={'op-journey-step op-journey-'+state} key={step.name} aria-current={step.active?'step':undefined}>
      <span className="op-journey-node" aria-hidden="true">{step.done?<Check size={13}/>:index+1}</span>
      <div className="op-journey-step-text"><strong>{step.name}</strong><small>{step.detail}</small></div>
    </li>;
   })}</ol>
   <div className="op-journey-facts">
     <div><span><FileText size={14}/>Estimator project</span>{journey.estimatorProject?.available?<a href={'/#/estimate/'+journey.estimatorProject.id} target="_blank" rel="noopener noreferrer">{journey.estimatorProject.name}<ArrowUpRight size={13}/></a>:<b>{journey.estimatorProject?'Previous link unavailable':'Not linked'}</b>}
       {item.permissions.createEstimate&&<button type="button" className="primary-btn op-journey-create-estimate" onClick={onCreateEstimate}>Create Estimate</button>}
       {item.permissions.edit&&<button type="button" className="op-journey-small-link" onClick={onChooseEstimator}>{journey.estimatorProject?'Change / unlink':'Link existing estimate'}</button>}
       {item.status==='approved'&&!journey.estimatorProject&&!(item.assignedTeamIds||[]).length&&<small className="op-help">Assign an approved team before creating an estimate.</small>}</div>
     <div><span><Link2 size={14}/>Tender project</span><b>{journey.quotation.linkedTenderName||'Not linked'}</b></div>
     <div><span><FileText size={14}/>Electrical quote</span><b>{journey.quotation.value==null?'Not recorded':aud.format(journey.quotation.value)}</b></div>
     <div><span><MessageSquareText size={14}/>Follow-up status</span><b>{!journey.chaseUp.started?'Not started':journey.chaseUp.overdueReminders?`${journey.chaseUp.overdueReminders} reminder(s) overdue`:journey.chaseUp.nextFollowUp?`Next: ${shortDate(journey.chaseUp.nextFollowUp.due)}`:journey.chaseUp.updates?'No next follow-up scheduled':'Ready for first follow-up'}</b></div>
   </div>
   {journey.chaseUp.latest&&<p className="op-journey-latest"><Clock size={14}/><span><strong>Latest update · {shortDate(journey.chaseUp.latest.date)}</strong> — {journey.chaseUp.latest.note}</span></p>}
   <div className="op-journey-next"><Target size={18} aria-hidden="true"/><div><strong>Next action: {journey.nextAction.title}</strong><p>{journey.nextAction.description}</p></div>{journey.nextAction.submissionId&&<button className="secondary-btn" onClick={()=>onChase(journey.nextAction.submissionId!)}>Open Chase-up<ChevronRight size={15}/></button>}</div>
   <div className="op-journey-footnote"><GitBranch size={13}/>Summary uses existing opportunity, Tender and Estimator records. Detailed edits stay in their respective workspaces.</div>
 </section>;
}
