/* No browser/runtime dependency: exercise real calendar generation. */
const assert = require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const elements={};
const ctx={console,Date,Set,document:{addEventListener:()=>{}},$:s=>elements[s]||(elements[s]={innerHTML:'',textContent:''}),
 state:{projects:[]},escapeHtml:s=>String(s),renderCalendarSummary:ps=>{ctx.monthProjects=ps;}};
vm.createContext(ctx);
for(const name of ['builders.js','workspace.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets',name),'utf8'),ctx);
vm.runInContext('workspaceState.month=new Date(2026,8,1);',ctx);
ctx.state.projects=[{id:1,name:'Saturday tender',client:'A\nB',status:'draft',submission_deadline:'2026-09-19'},
 {id:2,name:'Sunday tender',builders:['C'],status:'draft',submission_deadline:'2026-09-20'},
 {id:3,name:'Friday tender',builders:[],status:'submitted',submission_deadline:'2026-09-18'}];
vm.runInContext('renderCalendar()',ctx);
const html=elements['#calendar-grid'].innerHTML;
assert.equal((html.match(/calendar-weekday is-weekend/g)||[]).length,2);
assert.match(html,/is-weekend[^>]*>Sat<small>Weekend/);assert.match(html,/is-weekend[^>]*>Sun<small>Weekend/);
const days=[...html.matchAll(/<div class="calendar-day ([^"]*)"><time datetime="([^"]+)"[^>]*>/g)];
assert.equal(days.length,35);
for(const [,classes,key] of days){
 const [y,m,d]=key.split('-').map(Number),weekday=new Date(y,m-1,d).getDay();
 assert.equal(classes.includes('is-weekend'),weekday===6||weekday===0,key);
}
assert.equal(ctx.monthProjects.length,3,'Weekends must not remove deadlines or monthly totals');
assert.match(html,/data-project-brief="1"/);assert.match(html,/data-project-brief="2"/);
vm.runInContext('workspaceState.month=new Date(2027,1,1);renderCalendar()',ctx);
assert.equal([...elements['#calendar-grid'].innerHTML.matchAll(/class="calendar-day /g)].length,28);
assert.equal(ctx.monthProjects.length,0);
assert.equal(vm.runInContext("builderText({client:'Acme, Co\\nBeta'})",ctx),'Acme, Co, Beta');
assert.equal(vm.runInContext("projectBuilders({builders:['One','one','Two']}).length",ctx),2);
assert.equal(vm.runInContext("builderText({builders:[]},'No builder assigned')",ctx),'No builder assigned');
console.log('v2.3.5 calendar checks passed: Saturday/Sunday only, every displayed date, adjacent months, short-month layout, selectable weekend deadlines, optional builders.');
