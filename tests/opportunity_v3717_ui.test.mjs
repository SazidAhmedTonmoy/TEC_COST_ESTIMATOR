import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const root=new URL('../tenders_frontend/src/',import.meta.url);
const form=readFileSync(new URL('components/opportunities.tsx',root),'utf8');
const journey=readFileSync(new URL('components/opportunity-journey.tsx',root),'utf8');
const css=readFileSync(new URL('tender-v35.css',root),'utf8');

test('Opportunity form hides manual distance while preserving distance origin',()=>{
  assert.doesNotMatch(form,/>Distance \(km\)</);
  assert.match(form,/>Distance from<input/);
  assert.match(form,/distanceKm:null/);
});
test('Project details embed a read-only journey and actionable existing Estimator link',()=>{
  assert.match(form,/OpportunityJourneyView item=\{selected\}/);
  assert.match(journey,/\/\#\/estimate\//);
  assert.match(journey,/Link existing estimate/);
  assert.match(journey,/Open Chase-up/);
  for(const name of ['Opportunity created','Decision','Quotation','Project Chase-up','Final outcome'])assert.ok(journey.includes(name));
});
test('Estimator linking is revision-checked and optional',()=>{
  assert.match(form,/\/estimator-link/);
  assert.match(form,/estimatorProjectId:identifier/);
  assert.match(form,/estimator-projects\?/);
});
test('mobile journey avoids a wide horizontal grid',()=>{
  assert.match(css,/\.op-journey-facts\{grid-template-columns:1fr\}/);
  assert.match(css,/\.op-journey-next button\{width:100%\}/);
});
