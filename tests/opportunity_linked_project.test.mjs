import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {hasOpportunityProjectLink,opportunityProjectTarget} from '../tenders_frontend/src/lib/opportunity-linked-project.ts';

const detail=(opportunity={},journey={})=>({
  opportunity:{id:'opportunity-1',project:'Opportunity title',submissionIds:[],...opportunity},
  journey:{estimatorProject:null,nextAction:{submissionId:null},quotation:{submissionCount:0,missingSubmissions:false},...journey},
});

test('the explicitly linked Estimator opens before the Tender project without relying on their names',()=>{
  const record=detail({estimatorProjectId:42,submissionIds:['tender-1']},{
    estimatorProject:{id:42,name:'Different Estimator title',available:true},
    nextAction:{submissionId:'tender-1'},quotation:{submissionCount:1,missingSubmissions:false},
  });
  assert.deepEqual(opportunityProjectTarget(record),{kind:'estimator',id:42,href:'/#/estimate/42'});
});

test('an unavailable or mismatched explicit Estimator never silently opens the Tender instead',()=>{
  for(const estimatorProject of [null,{id:42,name:'Removed estimate',available:false},{id:43,name:'Another estimate',available:true}]){
    const target=opportunityProjectTarget(detail({estimatorProjectId:42,submissionIds:['live-tender']},{
      estimatorProject,nextAction:{submissionId:'live-tender'},quotation:{submissionCount:1,missingSubmissions:false},
    }));
    assert.equal(target.kind,'unavailable');assert.match(target.message,/Estimator project/);
  }
  for(const id of ['42','javascript:alert(1)',0,-1,1.5,Number.MAX_SAFE_INTEGER+1]){
    assert.equal(opportunityProjectTarget(detail({estimatorProjectId:id},{estimatorProject:{id,name:'Malformed link',available:true}})).kind,'unavailable');
  }
});

test('Tender fallback uses the live linked submission rather than the first stale recorded ID',()=>{
  const target=opportunityProjectTarget(detail({submissionIds:['deleted-tender','live-tender']},{
    nextAction:{submissionId:'live-tender'},quotation:{submissionCount:1,missingSubmissions:false},
  }));
  assert.deepEqual(target,{kind:'tender',submissionId:'live-tender'});
});

test('missing, deleted, inconsistent and unlinked records do not invent a project target',()=>{
  const live={nextAction:{submissionId:'tender-1'},quotation:{submissionCount:1,missingSubmissions:false}};
  for(const record of [
    detail(),
    detail({submissionIds:['tender-1']},{quotation:{submissionCount:0,missingSubmissions:true}}),
    detail({submissionIds:['other-tender']},live),
    detail({submissionIds:['tender-1'],deletedAt:'2026-11-20'},live),
    {opportunity:{id:'opportunity-1',project:'Same project name',submissionIds:['tender-1']}},
  ])assert.equal(opportunityProjectTarget(record).kind,'unavailable');
});

test('opening a linked project is available without link-edit permission',()=>{
  const readOnly={permissions:{edit:false,quote:false,approve:false},status:'pending'};
  assert.equal(hasOpportunityProjectLink({...readOnly,estimatorProjectId:42}),true);
  assert.equal(hasOpportunityProjectLink({...readOnly,submissionIds:['tender-1']}),true);
  assert.equal(hasOpportunityProjectLink({...readOnly,quoteStatus:'quoted'}),true);
  assert.equal(hasOpportunityProjectLink(readOnly),false);
  assert.equal(hasOpportunityProjectLink({...readOnly,estimatorProjectId:42,deletedAt:'2026-11-20'}),false);
});

test('card actions share sizing while both detailed link-management controls remain available',()=>{
  const source=readFileSync(new URL('../tenders_frontend/src/components/opportunities.tsx',import.meta.url),'utf8');
  const cards=source.slice(source.indexOf('<div className="op-cards"'),source.indexOf('<Sheet open='));
  assert.match(cards,/Open Linked Project/);assert.match(cards,/Open Project Chase-up/);
  assert.equal((cards.match(/className="[^"]*op-card-project-action[^"]*"/g)||[]).length,2);
  assert.doesNotMatch(cards,/Change linked project/);
  assert.match(source.slice(source.indexOf('<Sheet open=')),/Change linked project/);
  const journey=readFileSync(new URL('../tenders_frontend/src/components/opportunity-journey.tsx',import.meta.url),'utf8');
  assert.match(journey,/Change \/ unlink/);
  const css=readFileSync(new URL('../tenders_frontend/src/components/opportunity-linked-project.css',import.meta.url),'utf8');
  assert.match(css,/\.op-card \.op-card-project-action\{[^}]*width:100%;[^}]*min-height:38px;/);
});
