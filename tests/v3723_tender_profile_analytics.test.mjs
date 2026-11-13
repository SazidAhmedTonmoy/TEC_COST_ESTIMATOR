import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const tender=readFileSync('tenders_frontend/src/components/tender-app.tsx','utf8');
const profile=readFileSync('tenders_frontend/src/components/tender-profile.tsx','utf8');
const css=readFileSync('tenders_frontend/src/tender-profile.css','utf8');
const opportunities=readFileSync('tenders_frontend/src/components/opportunities.tsx','utf8');
const analytics=readFileSync('conest_app/opportunity_analytics.py','utf8');

test('Tender Profile stays within the Tender workspace and preserves Opportunities navigation',()=>{
 assert.match(tender,/import TenderProfile from '\.\/tender-profile'/);
 assert.match(tender,/onClick=\{\(\)=>go\('profile'\)\}/);
 assert.match(tender,/<TenderProfile user=\{session\.user\}/);
 assert.match(tender,/\['reminders','Reminders',Bell\],\['opportunities','Opportunities',FolderKanban\]/);
 assert.doesNotMatch(tender,/href="\/\?workspace=tenders#\/profile"/);
 assert.match(tender,/className="workspace-tab is-active" href="\/tenders\/"/);
 assert.match(css,/#f4cf38/);
});

test('Tender-native profile saves against the same account endpoint and rotates CSRF correctly',()=>{
 assert.match(profile,/request\('\/api\/auth\/profile'/);
 assert.match(profile,/method:'PATCH'/);
 assert.match(profile,/session\.csrf=result\.csrf_token/);
 assert.match(profile,/profile photo/i);
 assert.match(profile,/My homepage/);
 assert.match(profile,/Discard unsaved profile changes|beforeunload/);
});

test('Opportunity analytics is visible and readable to any active signed-in account',()=>{
 assert.match(opportunities,/<button aria-pressed=\{analyticsView\} onClick=\{\(\)=>setAnalyticsView\(true\)\}/);
 assert.match(opportunities,/\{analyticsView&&<OpportunityAnalytics\/>\}/);
 assert.doesNotMatch(opportunities,/session\.user\.role==='admin'&&<OpportunityAnalytics/);
 assert.match(analytics,/op\._actor\(user, users\)/);
 assert.doesNotMatch(analytics,/if actor\['role'\] != 'admin'/);
});
