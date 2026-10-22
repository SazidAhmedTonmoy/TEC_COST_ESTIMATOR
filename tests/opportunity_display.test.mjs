import assert from 'node:assert/strict';
import {test} from 'node:test';
import {canQuoteOpportunity,canRejectOpportunity,isOpportunityQuoted,opportunityDeadline,opportunityTimezone,opportunityLocalDate,nextOpportunityDayChange,safeOpportunityLink} from '../tenders_frontend/src/lib/opportunity-display.ts';

const regions=[
  {code:'NSW',origin:'Silverwater',timezone:'Australia/Sydney'},
  {code:'VIC',origin:'Melbourne',timezone:'Australia/Melbourne'},
  {code:'WA',origin:'Perth',timezone:'Australia/Perth'},
];
const deadline=(due,now,region='NSW',status='pending')=>opportunityDeadline({due,region,status},regions,Date.parse(now));

test('cards show calendar days remaining and due today/tomorrow immediately',()=>{
  assert.equal(deadline('2026-10-26','2026-10-21T08:00:00Z').label,'5 days left');
  assert.equal(deadline('2026-10-22','2026-10-21T08:00:00Z').label,'Due tomorrow');
  assert.equal(deadline('2026-10-21','2026-10-21T08:00:00Z').label,'Due today');
  assert.equal(deadline('2027-01-01','2026-12-30T13:00:00Z').days,1);
});

test('only active pending deadlines use inclusive three-day and seven-day colors',()=>{
  const now='2026-10-21T08:00:00Z';
  for(const due of ['2026-10-21','2026-10-22','2026-10-24'])assert.equal(deadline(due,now).tone,'urgent');
  for(const due of ['2026-10-25','2026-10-28'])assert.equal(deadline(due,now).tone,'warning');
  for(const due of ['2026-10-29','2027-01-01'])assert.equal(deadline(due,now).tone,'safe');
  assert.equal(deadline('2026-10-20',now).tone,'neutral');
  for(const status of ['approved','rejected','expired']){
    for(const due of ['2026-10-20','2026-10-21','2026-10-22','2026-10-24','2026-10-25','2026-10-28','2026-10-29','2027-01-01'])assert.equal(deadline(due,now,'NSW',status).tone,'neutral');
    assert.equal(deadline('',now,'NSW',status).tone,'neutral');
    assert.equal(deadline('invalid',now,'NSW',status).tone,'neutral');
  }
});

const actionable=(changes={})=>({status:'approved',due:'2026-10-22',region:'NSW',assignedTeamIds:[1],permissions:{approve:true,quote:true},...changes});

test('approved past-deadline records hide quote outcomes and Reject controls',()=>{
  const before=Date.parse('2026-10-22T12:59:59.999Z'),after=Date.parse('2026-10-22T13:00:00Z');
  const item=actionable();
  assert.equal(canQuoteOpportunity(item,regions,before),true);
  assert.equal(canRejectOpportunity(item,regions,before),false);
  assert.equal(canQuoteOpportunity(item,regions,after),false);
  assert.equal(canRejectOpportunity(item,regions,after),false);
  assert.equal(canQuoteOpportunity(actionable({region:'WA'}),regions,after),true);
  assert.equal(canRejectOpportunity(actionable({region:'WA'}),regions,after),false);
  assert.equal(canQuoteOpportunity(actionable({due:''}),regions,after),true);
  assert.equal(canRejectOpportunity(actionable({status:'expired'}),regions,before),true);
  assert.equal(canRejectOpportunity(actionable({status:'pending'}),regions,before),true);
  assert.equal(canRejectOpportunity(actionable({status:'rejected'}),regions,after),false);
});

test('quoted links, deleted records and missing permissions never expose quote or reject controls',()=>{
  const now=Date.parse('2026-10-23T08:00:00Z');
  for(const changes of [{quoteStatus:'quoted'},{submissionIds:['linked-quote']},{deletedAt:'2026-10-22T00:00:00Z'},{permissions:{approve:false,quote:false}}]){
    const item=actionable(changes);
    assert.equal(canQuoteOpportunity(item,regions,now),false);
    assert.equal(canRejectOpportunity(item,regions,now),false);
  }
  assert.equal(isOpportunityQuoted(actionable({submissionIds:['existing']})),true);
  assert.equal(isOpportunityQuoted(actionable({quoteStatus:'quoted'})),true);
  assert.equal(isOpportunityQuoted(actionable()),false);
  assert.equal(canQuoteOpportunity(actionable({permissions:{approve:true}}),regions,Date.parse('2026-10-21T08:00:00Z')),true);
});

test('quote submission dates use the project region calendar',()=>{
  const now=Date.parse('2026-10-21T13:00:00Z');
  assert.equal(opportunityLocalDate('NSW',regions,now),'2026-10-22');
  assert.equal(opportunityLocalDate('VIC',regions,now),'2026-10-22');
  assert.equal(opportunityLocalDate('WA',regions,now),'2026-10-21');
});

test('NSW/VIC cross midnight independently of UTC or the browser timezone',()=>{
  for(const region of ['NSW','VIC']){
    assert.equal(deadline('2026-10-22','2026-10-21T12:59:59.999Z',region).days,1);
    assert.equal(deadline('2026-10-22','2026-10-21T13:00:00.000Z',region).days,0);
  }
  assert.equal(deadline('2026-10-22','2026-10-21T13:00:00Z','WA').days,1);
  assert.equal(opportunityTimezone('VIC'), 'Australia/Melbourne');
  assert.equal(opportunityTimezone('WA',regions), 'Australia/Perth');
  assert.equal(opportunityTimezone('NSW',[{code:'NSW',origin:'',timezone:'Not/AZone'}]),'Australia/Sydney');
});

test('calendar day counts survive daylight saving start, end and leap years',()=>{
  assert.equal(deadline('2026-10-05','2026-10-03T14:00:00Z').days,1);
  assert.equal(deadline('2026-04-06','2026-04-04T13:00:00Z').days,1);
  assert.equal(deadline('2028-03-01','2028-02-27T13:00:00Z').days,2);
  assert.equal(deadline('2028-02-29','2028-02-27T13:00:00Z').days,1);
});

test('past deadline wording respects the recorded decision',()=>{
  const now='2026-10-21T08:00:00Z';
  assert.equal(deadline('2026-10-20',now,'NSW','expired').label,'Expired 1 day ago');
  assert.equal(deadline('2026-10-19',now,'NSW','expired').label,'Expired 2 days ago');
  for(const status of ['pending','approved','rejected']){
    assert.equal(deadline('2026-10-20',now,'NSW',status).label,'Deadline passed 1 day ago');
    assert.doesNotMatch(deadline('2026-10-20',now,'NSW',status).label,/expired/i);
  }
});

test('blank and invalid deadlines do not produce NaN or an invented expiry',()=>{
  const now='2026-10-21T08:00:00Z';
  assert.equal(deadline('',now).label,'No deadline');
  for(const due of ['invalid','2026-02-29','2026-13-01','2026-10-00','2026-10-21T00:00:00Z']){
    assert.equal(deadline(due,now).label,'Deadline unavailable');
    assert.equal(deadline(due,now).days,null);
  }
});

test('the one client timer targets the next regional midnight including DST',()=>{
  const next=(zones,now)=>new Date(nextOpportunityDayChange(zones,Date.parse(now))).toISOString();
  assert.equal(next(['Australia/Sydney','Australia/Melbourne','Australia/Perth'],'2026-10-21T12:00:00Z'),'2026-10-21T13:00:00.000Z');
  assert.equal(next(['Australia/Sydney'],'2026-10-03T14:00:00Z'),'2026-10-04T13:00:00.000Z');
  assert.equal(next(['Australia/Melbourne'],'2026-04-04T13:00:00Z'),'2026-04-05T14:00:00.000Z');
  assert.equal(next(['Asia/Kathmandu'],'2026-10-21T08:00:00Z'),'2026-10-21T18:15:00.000Z');
  assert.equal(next(['UTC'],'2026-10-21T00:00:00Z'),'2026-10-22T00:00:00.000Z');
  assert.equal(next([],'2026-10-21T12:59:59.999Z'),'2026-10-21T13:00:00.000Z');
});

test('safe links preserve HTTP(S) paths, queries and fragments',()=>{
  assert.equal(safeOpportunityLink('https://example.com/tender/42?token=a%2Fb#plans'),'https://example.com/tender/42?token=a%2Fb#plans');
  assert.equal(safeOpportunityLink('http://example.com/project'),'http://example.com/project');
  assert.equal(safeOpportunityLink('https://EXAMPLE.com'),'https://example.com/');
});

test('unsafe and malformed stored links never become clickable',()=>{
  for(const value of [undefined,null,'','javascript:alert(1)','data:text/html,test','file:///tmp/test','mailto:a@example.com','//example.com','example.com/project','https://user:secret@example.com','https://example.com/a b','https://example.com/a\nb','https://example.com\\bad','https://example.com/'+ 'a'.repeat(2048)]){
    assert.equal(safeOpportunityLink(value),'',String(value));
  }
});
