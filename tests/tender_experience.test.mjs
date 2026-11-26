import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = name => readFileSync(new URL('../'+name,import.meta.url),'utf8');
test('Dashboard removes permanent three-field filter bar, while keeping advanced filters',()=>{
 const app=source('tenders_frontend/src/components/tender-app.tsx');
 assert.ok(app.includes('dashboard-quick-actions'));
 assert.doesNotMatch(app, /<div className="dashboard-filters">/);
 assert.ok(app.includes("function filters(includeSearch=true)"));
 assert.ok(app.includes('New tender'));
});
test('Tender views remember search, filter, sorting and scroll when navigating',()=>{
 const app=source('tenders_frontend/src/components/tender-app.tsx');
 assert.ok(app.includes('viewSnapshots.current[view]'));
 assert.ok(app.includes('setQ(saved?.q'));
 assert.ok(app.includes('setPage(saved?.page'));
 assert.ok(app.includes('scrollTo({top:saved?.scrollTop'));
});
test('Both client entrypoints load versioned guide styles',()=>{
 for(const file of ['assets/index.html','tenders_frontend/index.html']){
  assert.match(source(file),/help_shared\.css\?v=3\.8\.13/);
 }
});
test('Estimate view preserves collapsed groups, expanded items and search by user and project',()=>{
 const js=source('assets/estimate_workspace.js');
 assert.ok(js.includes('function estimateViewPreferenceKey()'));
 assert.ok(js.includes('state.user?.id'));
 assert.ok(js.includes('state.projectId'));
 assert.ok(js.includes('sessionStorage.setItem(key'));
 assert.ok(js.includes('sessionStorage.getItem(key'));
 assert.ok(js.includes('collapsed:[...estimateViewState.collapsed]'));
 assert.ok(js.includes('expanded:[...estimateViewState.expanded]'));
 assert.ok(js.includes('query:estimateViewState.query'));
 assert.ok(js.includes('function renderGroupedEstimate(lines){\n  restoreEstimateViewPreferences();'));
});
