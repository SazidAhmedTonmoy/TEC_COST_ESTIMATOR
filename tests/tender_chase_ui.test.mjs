import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const app=readFileSync(new URL('../tenders_frontend/src/components/tender-app.tsx',import.meta.url),'utf8');
const styles=readFileSync(new URL('../tenders_frontend/src/tender-v35.css',import.meta.url),'utf8');
const server=readFileSync(new URL('../conest_app/tender_http.py',import.meta.url),'utf8');

test('Chase-up list displays the first fourteen days and readiness states',()=>{
 assert.match(app,/Recently Submitted/);
 assert.match(app,/Ready for First Chase-Up/);
 assert.match(app,/latestChaseLabel\(s,cc,now\.slice\(0,10\)\)/);
 assert.match(app,/submittedDate/);
});
test('Recurring schedule checkbox and stop rules are integrated with the form',()=>{
 assert.match(app,/type="checkbox" checked=\{repeat14\}/);
 assert.match(app,/repeatEvery14Days:repeat14/);
 assert.match(app,/Repeat automatically every 14 days until Closed or Lost/);
 assert.match(app,/!chaseAllowed\(s\)\?null/);
});
test('Selecting a Chase-up Calendar date reveals the lower agenda',()=>{
 assert.match(app,/function selectCalendarDate\(date:string\)/);
 assert.match(app,/setDay\(date\)/);
 assert.match(app,/agendaRef\.current\?\.scrollIntoView/);
 assert.match(app,/ref=\{agendaRef\} className="panel agenda"/);
 assert.match(styles,/\.calendar-day\.is-selected/);
});
test('Schedule author or admin can request delete with confirmation',()=>{
 assert.match(app,/session\.user\.role==='admin'\|\|r\.createdBy===session\.user\.id/);
 assert.match(app,/confirm\(`Delete the/);
 assert.match(app,/method:'DELETE'/);
 assert.match(server,/path=='\/api\/tenders\/reminders' and h\.command=='DELETE'/);
});
