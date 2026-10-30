import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
const read=(path)=>readFileSync(new URL('../'+path,import.meta.url),'utf8');
const opportunity=read('tenders_frontend/src/components/opportunities.tsx');
const app=read('tenders_frontend/src/components/tender-app.tsx');
const calendar=read('tenders_frontend/src/components/opportunity-calendar.tsx');
const types=read('tenders_frontend/src/lib/opportunity-types.ts');
const styles=read('tenders_frontend/src/tender-v35.css');
const breakdown=read('assets/estimate_areas.js');
const estimatorBundle=read('assets/'+read('assets/index.html').match(/\/assets\/(app\.[a-z0-9]{12}\.js)/)[1]);

test('calendar defaults to approved opportunities with Chase-up alternative',()=>{
 assert.match(app,/useState<'opportunities'\|'chase'>\('opportunities'\)/);
 assert.match(app,/Approved opportunity deadlines|Approved opportunities/);
 assert.match(app,/Project Chase-up/);
 assert.match(calendar,/opportunities\/calendar\?/);
 assert.match(calendar,/onOpen\(item\.id\)/);
});
test('four cards expose review, quote breakdown, combined closed counts and filters',()=>{
 assert.match(types,/review:'In Review'/);
 assert.match(opportunity,/needsQuote/);
 assert.match(opportunity,/result\?\.counts\.rejected/);
 assert.match(opportunity,/result\?\.counts\.expired/);
 assert.match(opportunity,/quoteFilter/);
 assert.match(opportunity,/closedFilter/);
 assert.match(opportunity,/Move to In Review/);
 assert.match(opportunity,/useState\('due_desc'\)/);
});
test('quoted colours, chase contrast and collapsed area totals are in deployable source',()=>{
 assert.match(styles,/calendar-mode-switch/);
 assert.match(styles,/op-status-review/);
 assert.match(read('tenders_frontend/src/globals.css'),/readable chase-up history/);
 assert.match(breakdown,/treeState='collapsed'/);
 for(const text of ['Total Material','Total Hours','Total Labour','Quoted Total']){
  assert.ok(breakdown.includes(text));assert.ok(estimatorBundle.includes(text));
 }
});
