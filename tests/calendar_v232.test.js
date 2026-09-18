/* Optional Node checks: node tests/calendar_v232.test.js. No runtime JS dependency. */
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const elements={'#calendar-summary':{innerHTML:''},'#calendar-agenda':{innerHTML:''}};
const projects=[['AUD',100,60,200],['AUD',20,30,80],['USD',7,9,19]].map(([currency,material,labor,quoted],i)=>({
 id:i+1,name:`Fixture ${i}`,client:'',currency,totals:{material,labor,quoted,direct:999999,hours:2},line_count:1,status:'draft',award_status:'',
 teams:[],owner_name:'Test',created_at:'2026-09-01',submission_deadline:'2026-09-18'}));
const ctx={document:{addEventListener:()=>{}},$:(s)=>elements[s],state:{projects},workspaceState:{month:new Date('2026-09-01T00:00:00')},
 statusNames:{draft:'Not started',in_progress:'In progress',submitted:'Submitted',completed:'Completed'},
 escapeHtml:s=>String(s),fmtMoney:(n,c)=>new Intl.NumberFormat('en-AU',{style:'currency',currency:c||'AUD'}).format(n||0),
 fmtNumber:n=>String(n),localDateKey:()=> '2026-09-01',dateLabel:s=>s,teamNames:()=>'',projectStatus:()=>'',console};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/v23.js'),'utf8'),ctx);
vm.runInContext('renderCalendarSummary(state.projects)',ctx);
const html=elements['#calendar-summary'].innerHTML, table=elements['#calendar-agenda'].innerHTML;
assert.match(html,/Total material cost/);assert.match(html,/Total labour price/);
assert.match(html,/AUD \$120\.00/);assert.match(html,/AUD \$90\.00/);
assert.match(html,/USD USD\s*7\.00/);assert.match(html,/USD USD\s*9\.00/);
assert.doesNotMatch(html,/999,999|Cost before overhead/);
assert.match(table,/Material cost/);assert.match(table,/Labour price/);assert.match(table,/AUD \$120\.00/);
ctx.state.projects=[];vm.runInContext('renderCalendarSummary([])',ctx);assert.match(elements['#calendar-agenda'].innerHTML,/No project deadlines/);
console.log('Calendar checks passed: material/labour engine keys, mixed currencies, no direct-cost card, table totals and empty month.');
