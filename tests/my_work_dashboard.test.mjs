import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const root = new URL('../',import.meta.url);
const load = (path)=>readFileSync(new URL(path,root),'utf8');
test('Estimator Home retains original board and has My Work with both scopes',()=>{
 const html=load('assets/index.html');const js=load('assets/my_work.js');
 assert.match(html,/id="my-work-home"/);assert.match(html,/id="project-board"/);
 for(const marker of ['data-work-scope','needsApproval','needsQuote','dueSoon','followUpsDue','/api/tenders/opportunities/my-work','data-work-opportunity','data-work-chase'])assert.ok(js.includes(marker),marker);
 assert.match(js,/encodeURIComponent\(target\.dataset\.workOpportunity\)/);
});
test('Tender dashboard shows the same four metrics and opens precise records',()=>{
 const app=load('tenders_frontend/src/components/tender-app.tsx');
 const component=load('tenders_frontend/src/components/my-work-dashboard.tsx');
 for(const marker of ['Needs my approval','Approved, not quoted','Deadlines within 3 days','Follow-ups due','Next actions','My team','onOpenOpportunity','onOpenChase'])assert.ok(component.includes(marker),marker);
 assert.match(app,/<MyWorkDashboard/);assert.match(app,/new URLSearchParams\(location.search\)\.get\('open'\)/);
 assert.match(app,/new URLSearchParams\(location.search\)\.get\('submission'\)/);
});
