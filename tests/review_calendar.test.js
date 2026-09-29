/* Review entries must not duplicate submission-month counts or money. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const elements={};const el=s=>elements[s]||(elements[s]={value:'',innerHTML:'',dataset:{},classList:{toggle(){},remove(){},add(){}}});
const ctx={console,Date,Map,Set,document:{addEventListener(){}},$:el,$$:()=>[],state:{user:{id:1,role:'admin'},projects:[]},escapeHtml:s=>String(s),fmtMoney:n=>String(n||0),fmtNumber:n=>String(n||0)};
vm.createContext(ctx);for(const file of ['builders.js','workspace.js','v23.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets',file),'utf8'),ctx);
const p={id:1,name:'Review project',status:'in_review',review_deadline:'2026-10-05',submission_deadline:'2026-09-30',currency:'AUD',totals:{quoted:900,material:500,labor:400,hours:4},line_count:2,teams:[]};ctx.state.projects=[p];
vm.runInContext('workspaceState.month=new Date(2026,8,1);renderCalendar()',ctx);
assert.match(el('#calendar-summary').innerHTML,/Projects due this month<\/span><strong>1</);assert.match(el('#calendar-summary').innerHTML,/AUD 900/);assert.equal(el('#calendar-review-agenda').innerHTML,'');
vm.runInContext('workspaceState.month=new Date(2026,9,1);renderCalendar()',ctx);
assert.match(el('#calendar-grid').innerHTML,/data-event-kind="review"/);assert.match(el('#calendar-grid').innerHTML,/calendar-event is-review/);
assert.match(el('#calendar-review-agenda').innerHTML,/Review project/);assert.match(el('#calendar-summary').innerHTML,/Projects due this month<\/span><strong>0</);assert.doesNotMatch(el('#calendar-summary').innerHTML,/AUD 900/);
p.submission_deadline=p.review_deadline;vm.runInContext('renderCalendar()',ctx);
assert.equal((el('#calendar-grid').innerHTML.match(/data-project-brief="1"/g)||[]).length,1);assert.match(el('#calendar-grid').innerHTML,/Submission · Review due/);assert.match(el('#calendar-summary').innerHTML,/Projects due this month<\/span><strong>1</);
p.status='submitted';p.review_deadline=null;vm.runInContext('renderCalendar();renderSchedule()',ctx);
assert.doesNotMatch(el('#calendar-grid').innerHTML,/is-review|calendar-review-stamp|data-event-kind="review"/);assert.match(el('#calendar-grid').innerHTML,/data-event-kind="submission"/);assert.equal(el('#calendar-review-agenda').innerHTML,'');assert.doesNotMatch(el('#deadline-agenda').innerHTML,/Review project/);
p.status='in_review';p.review_deadline='2026-10-06';vm.runInContext('renderCalendar();renderSchedule()',ctx);assert.match(el('#deadline-agenda').innerHTML,/Review by/);assert.equal((el('#calendar-grid').innerHTML.match(/data-project-brief="1"/g)||[]).length,2);assert.match(el('#calendar-summary').innerHTML,/Projects due this month<\/span><strong>1</);
console.log('Review calendar passed: cross-month and same-day entries, counts/totals unchanged, stamps/reminders clear on submission.');
