import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {opportunityDeadline} from '../tenders_frontend/src/lib/opportunity-display.ts';

const regions=[{code:'NSW',origin:'Silverwater',timezone:'Australia/Sydney'},{code:'VIC',origin:'Melbourne',timezone:'Australia/Melbourne'}];
const now=Date.parse('2026-11-02T04:00:00Z');
const deadline=(data)=>opportunityDeadline({status:'approved',region:'NSW',due:'2026-10-30',...data},regions,now);

test('quoted or linked Approved opportunities show neutral Submitted, not overdue urgency',()=>{
  for(const fields of [{quoteStatus:'quoted'},{submissionIds:['quote-23']},{linkedAt:'2026-10-29T12:00:00Z'}]){
    const result=deadline(fields);
    assert.equal(result.label,'Submitted');
    assert.equal(result.tone,'neutral');
    assert.equal(result.days,null);
  }
});

test('submitted badge remains neutral before the deadline and with no deadline',()=>{
  assert.equal(deadline({due:'2026-12-01',quoteStatus:'quoted'}).label,'Submitted');
  assert.equal(deadline({due:'',linkedAt:'2026-10-30T09:00:00Z'}).label,'Submitted');
  assert.equal(deadline({due:'',linkedAt:'2026-10-30T09:00:00Z'}).tone,'neutral');
});

test('unquoted Approved opportunity deadlines keep their urgency and regional day counts',()=>{
  assert.match(deadline({}).label,/Deadline passed/);
  assert.equal(deadline({}).tone,'urgent');
  assert.equal(deadline({due:'2026-11-05'}).tone,'urgent');
  assert.equal(deadline({due:'2026-11-08'}).tone,'warning');
  assert.equal(deadline({due:'2026-11-20'}).tone,'safe');
  assert.equal(deadline({status:'rejected',quoteStatus:'quoted'}).label,'Deadline passed 3 days ago');
  assert.equal(deadline({status:'expired',linkedAt:'2026-10-29T09:00:00Z'}).tone,'neutral');
});

test('card and detail panel both use the same submitted/neutral deadline component',()=>{
  const source=readFileSync(new URL('../tenders_frontend/src/components/opportunities.tsx',import.meta.url),'utf8');
  assert.match(source,/<DeadlineBadge item=\{item\}/);
  assert.match(source,/<DeadlineBadge item=\{selected\}/);
  assert.match(source,/op-deadline-['"]?\+deadline\.tone/);
});

test('both monthly Tender calendars highlight today and label the active date accessibly',()=>{
  const approved=readFileSync(new URL('../tenders_frontend/src/components/opportunity-calendar.tsx',import.meta.url),'utf8');
  const chase=readFileSync(new URL('../tenders_frontend/src/components/tender-app.tsx',import.meta.url),'utf8');
  const css=readFileSync(new URL('../tenders_frontend/src/globals.css',import.meta.url),'utf8');
  assert.match(approved,/date===today\?' is-today'/);
  assert.match(approved,/aria-current=\{date===today\?'date'/);
  assert.match(chase,/dt===now\.slice\(0,10\)\?'is-today /);
  assert.match(chase,/aria-current=\{dt===now\.slice\(0,10\)\?'date'/);
  assert.match(css,/\.calendar-panel \.calendar-day\.is-today\{/);
  assert.match(css,/\.calendar-panel \.calendar-day\.is-today \.day-number/);
});
