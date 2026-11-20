import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {canAssignOpportunityFromCard,opportunityManagementDraft,opportunityManagementPayload} from '../tenders_frontend/src/lib/opportunity-assignment.ts';
import {createDeadlineLoadLookup,deadlineLoadInitialState,deadlineLoadKey,deadlineLoadMessage,deadlineTeamGroups,deadlineTeamGroupMessage,validOpportunityDeadline} from '../tenders_frontend/src/lib/opportunity-deadline-load.ts';

const item=(fields={})=>({id:'opportunity-A',revision:7,project:'Project A',status:'pending',permissions:{assign:true,manage:true},assignedTeamIds:[],assignedUserIds:[],editorTeamIds:[],editorUserIds:[],...fields});
const wait=(ms=10)=>new Promise(resolve=>setTimeout(resolve,ms));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject};};
const response=(due,count,ok=true,teamGroups)=>({ok,json:async()=>({due,count,...(teamGroups===undefined?{}:{teamGroups})})});

test('card assignment is offered only for an authorised completely unassigned record',()=>{
  assert.equal(canAssignOpportunityFromCard(item()),true);
  for(const record of [
    item({permissions:{assign:false,manage:true}}),
    item({deletedAt:'2026-11-20'}),
    item({assignedTeamIds:[999]}),
    item({assignedUserIds:[999]}),
    item({assignedTeamIds:[1],assignedUserIds:[2]}),
  ])assert.equal(canAssignOpportunityFromCard(record),false);
  // Existing expiry/approval rules remain the server's responsibility.
  assert.equal(canAssignOpportunityFromCard(item({status:'expired'})),true);
});

test('assignment saves retain the clicked project and revision through unrelated refreshes',()=>{
  const original=item({assignedTeamIds:[2],assignedUserIds:[3]});
  const draft=opportunityManagementDraft(original,'assign','card');
  original.id='unrelated-project';original.revision=99;original.status='approved';
  original.assignedTeamIds.push(4);original.assignedUserIds.length=0;
  assert.equal(draft.id,'opportunity-A');assert.equal(draft.revision,7);assert.equal(draft.status,'pending');
  assert.deepEqual(opportunityManagementPayload(draft),{id:'opportunity-A',revision:7,assignedTeamIds:[2],assignedUserIds:[3]});
  const payload=opportunityManagementPayload(draft);payload.assignedTeamIds.push(8);
  assert.deepEqual(draft.teams,[2]);
});

test('detail assignment and editing-access drafts preserve separate fields and allow unassignment',()=>{
  const original=item({assignedTeamIds:[2],assignedUserIds:[3],editorTeamIds:[4],editorUserIds:[5]});
  const access=opportunityManagementDraft(original,'access');
  assert.equal(access.origin,'details');
  assert.deepEqual(opportunityManagementPayload(access),{id:'opportunity-A',revision:7,editorTeamIds:[4],editorUserIds:[5]});
  const assignment=opportunityManagementDraft(original,'assign');assignment.teams=[];assignment.users=[];
  assert.deepEqual(opportunityManagementPayload(assignment),{id:'opportunity-A',revision:7,assignedTeamIds:[],assignedUserIds:[]});
  assert.deepEqual(original.assignedTeamIds,[2]);
});

test('card footer buttons share dimensions and touch targets while assigned names stay plain text',()=>{
  const source=readFileSync(new URL('../tenders_frontend/src/components/opportunities.tsx',import.meta.url),'utf8');
  const footer=source.slice(source.indexOf('<div className="op-card-footer">'),source.indexOf('<div className="op-card-quoted">'));
  assert.equal((footer.match(/className="secondary-btn op-card-footer-action"/g)||[]).length,2);
  assert.match(footer,/Assign team/);assert.match(footer,/View details/);
  assert.match(footer,/:<span className="op-assignees">/);
  const css=readFileSync(new URL('../tenders_frontend/src/components/opportunity-planning.css',import.meta.url),'utf8');
  assert.match(css,/\.op-card-footer \.op-card-footer-action\{[^}]*width:108px;[^}]*height:35px;/);
  assert.match(css,/@media\(max-width:767px\),\(pointer:coarse\)\{[^}]*height:44px;min-height:44px/);
});

test('only full valid calendar dates trigger a lookup, including leap-year boundaries',()=>{
  for(const due of ['2026-12-09','2028-02-29','2000-02-29'])assert.equal(validOpportunityDeadline(due),true,due);
  for(const due of ['', '2026-2-9','2026-02-29','1900-02-29','2026-04-31','2026-13-01','0000-01-01','2026-12-09T00:00:00Z']){
    assert.equal(validOpportunityDeadline(due),false,due);
    assert.equal(deadlineLoadInitialState(due).status,'idle');
  }
  assert.notEqual(deadlineLoadKey('2026-12-09','A'),deadlineLoadKey('2026-12-09','B'));
});

test('deadline warning reports singular/plural counts and stays silent for no conflict',()=>{
  assert.equal(deadlineLoadMessage(1),'1 other project has this closing date.');
  assert.equal(deadlineLoadMessage(12),'12 other projects have this closing date.');
  for(const count of [0,null,-1,1.2])assert.equal(deadlineLoadMessage(count),'');
});

test('team breakdown names each assignment combination once and labels missing team assignments',()=>{
  const groups=deadlineTeamGroups([
    {teamNames:['TEC BD team'],count:2},
    {teamNames:['TEC AU team','TEC BD team'],count:1},
    {teamNames:['Former team'],count:1},
    {teamNames:[],count:1},
  ],5);
  assert.deepEqual(groups.map(deadlineTeamGroupMessage),[
    'TEC BD team: 2',
    'TEC AU team + TEC BD team: 1',
    'Former team: 1',
    'No team assigned: 1',
  ]);
  assert.equal(groups.reduce((total,group)=>total+group.count,0),5);
  assert.deepEqual(deadlineTeamGroups([],0),[]);
  assert.equal(deadlineTeamGroups(undefined,3),null);
});

test('malformed, duplicated or incomplete team counts cannot become a misleading breakdown',()=>{
  for(const groups of [
    null,{},'TEC BD team',[],
    [{teamNames:['TEC BD team'],count:0}],
    [{teamNames:['TEC BD team'],count:1.5}],
    [{teamNames:['TEC BD team'],count:'2'}],
    [{teamNames:['TEC BD team'],count:3}],
    [{teamNames:['TEC BD team'],count:1}],
    [{teamNames:'TEC BD team',count:2}],
    [{teamNames:[''],count:2}],
    [{teamNames:[42],count:2}],
    [{teamNames:['TEC BD team',' TEC BD team '],count:2}],
    [{teamNames:['TEC AU team','TEC BD team'],count:1},{teamNames:['TEC BD team','TEC AU team'],count:1}],
    [{teamNames:[],count:1},{teamNames:[],count:1}],
  ])assert.throws(()=>deadlineTeamGroups(groups,2));
});

test('lookup sends the chosen date and excludes the edited record without list filters',async()=>{
  const states=[],paths=[];
  const lookup=createDeadlineLoadLookup(async(path)=>{paths.push(path);return response('2026-12-09',21);},state=>states.push(state),0);
  lookup.check('2026-12-09','opportunity A/&');await wait();
  const url=new URL(paths[0],'https://example.test/');
  assert.equal(url.pathname,'/opportunities/deadline-load');
  assert.deepEqual([...url.searchParams], [['due','2026-12-09'],['excludeId','opportunity A/&']]);
  assert.equal(states.at(-1).count,21);assert.equal(states.at(-1).status,'ready');
  assert.equal(states.at(-1).teamGroups,null); // Compatible with a total-only server response.
  lookup.cancel();
});

test('rapid date changes debounce to the latest selection and blank dates clear immediately',async()=>{
  const states=[],paths=[];
  const lookup=createDeadlineLoadLookup(async(path)=>{paths.push(path);return response('2026-12-10',2,true,[{teamNames:['TEC BD team'],count:2}]);},state=>states.push(state),20);
  lookup.check('2026-12-09');lookup.check('2026-12-10');await wait(35);
  assert.equal(paths.length,1);assert.match(paths[0],/due=2026-12-10/);
  assert.equal(states.at(-1).count,2);
  assert.deepEqual(states.at(-1).teamGroups,[{teamNames:['TEC BD team'],count:2}]);
  lookup.check('');assert.equal(states.at(-1).status,'idle');assert.equal(states.at(-1).count,null);
  assert.equal(states.at(-1).teamGroups,null);
  await wait(25);assert.equal(paths.length,1);lookup.cancel();
});

test('a late previous-date response cannot replace the current warning even when fetch ignores abort',async()=>{
  const states=[],requests=[];
  const lookup=createDeadlineLoadLookup((path,{signal})=>{const pending=deferred();requests.push({path,signal,...pending});return pending.promise;},state=>states.push(state),0);
  lookup.check('2026-12-09');await wait();lookup.check('2026-12-10');await wait();
  assert.equal(requests[0].signal.aborted,true);
  requests[1].resolve(response('2026-12-10',3,true,[{teamNames:['TEC AU team'],count:3}]));await wait();
  requests[0].resolve(response('2026-12-09',99,true,[{teamNames:['Old date team'],count:99}]));await wait();
  assert.equal(states.at(-1).due,'2026-12-10');assert.equal(states.at(-1).count,3);
  assert.deepEqual(states.at(-1).teamGroups,[{teamNames:['TEC AU team'],count:3}]);
  assert.equal(states.some(state=>state.teamGroups?.some(group=>group.teamNames.includes('Old date team'))),false);
  assert.equal(states.some(state=>state.count===99),false);lookup.cancel();
});

test('a delayed body from another edited record is ignored even on the same closing date',async()=>{
  const states=[],firstBody=deferred();let calls=0;
  const lookup=createDeadlineLoadLookup(async()=>++calls===1?{ok:true,json:()=>firstBody.promise}:response('2026-12-09',4,true,[{teamNames:[],count:4}]),state=>states.push(state),0);
  lookup.check('2026-12-09','A');await wait();lookup.check('2026-12-09','B');await wait();
  firstBody.resolve({due:'2026-12-09',count:90,teamGroups:[{teamNames:['Old record team'],count:90}]});await wait();
  assert.equal(states.at(-1).key,deadlineLoadKey('2026-12-09','B'));
  assert.equal(states.at(-1).count,4);assert.equal(states.some(state=>state.count===90),false);
  assert.deepEqual(states.at(-1).teamGroups,[{teamNames:[],count:4}]);lookup.cancel();
});

test('lookup failures and malformed responses are unknown rather than a false zero count',async()=>{
  for(const result of [response('2026-12-09',0,false),response('2026-12-10',3),response('2026-12-09',-1),response('2026-12-09',1.5),response('2026-12-09','2'),response('2026-12-09',3,true,[]),response('2026-12-09',2,true,[{teamNames:['Wrong count team'],count:3}]),{ok:true,json:async()=>{throw Error('Invalid JSON');}}]){
    const states=[];const lookup=createDeadlineLoadLookup(async()=>result,state=>states.push(state),0);
    lookup.check('2026-12-09');await wait();
    assert.equal(states.at(-1).status,'error');assert.equal(states.at(-1).count,null);assert.equal(states.at(-1).teamGroups,null);lookup.cancel();
  }
});

test('closing the form cancels in-flight work without updating its former state',async()=>{
  const pending=deferred(),states=[];
  const lookup=createDeadlineLoadLookup(()=>pending.promise,state=>states.push(state),0);
  lookup.check('2026-12-09');await wait();lookup.cancel();const before=states.length;
  pending.resolve(response('2026-12-09',25));await wait();assert.equal(states.length,before);
});
