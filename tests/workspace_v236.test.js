const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const elements={};
const element=s=>elements[s]||(elements[s]={value:'',innerHTML:'',dataset:{},classList:{toggle(){},remove(){},add(){}}});
const ctx={console,Date,Map,Set,document:{addEventListener(){}},$:element,$$:()=>[],
 state:{user:{id:1,role:'admin'},projects:[]},escapeHtml:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),fmtMoney:n=>String(n||0),projectOutcome:()=>''};
vm.createContext(ctx);
for(const file of ['builders.js','workspace.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets',file),'utf8'),ctx);
ctx.state.projects=[{id:1,name:'New <project>',status:'draft',needs_admin_review:true,submission_deadline:'2026-09-22',currency:'AUD',can_edit:true}, {id:2,name:'Finished',status:'submitted',submission_deadline:'2026-09-20',currency:'AUD',can_edit:true}];
vm.runInContext("workspaceState.filter='draft';renderProjectBoard()",ctx);
assert.match(element('#project-board').innerHTML,/Newly added/);
assert.match(element('#project-board').innerHTML,/New &lt;project>/);
assert.doesNotMatch(element('#project-board').innerHTML,/Finished/);
for(const view of ['cards','list']){
 vm.runInContext(`workspaceState.boardView='${view}';renderProjectBoard()`,ctx);
 assert.equal(element('#project-board').dataset.view,view);
 assert.match(element('#project-board').innerHTML,/href="#\/estimate\/1"/);
}
element('#project-search').value='no match';vm.runInContext('renderProjectBoard()',ctx);
assert.match(element('#project-board').innerHTML,/No matching projects/);
vm.runInContext("workspaceState.reminderRows=[{project_id:1,key:'1:due',days:1,read:false}];renderSchedule()",ctx);
assert.equal((element('#deadline-agenda').innerHTML.match(/data-project-brief="1"/g)||[]).length,1);
assert.match(element('#deadline-agenda').innerHTML,/Due in 1 day</);
assert.match(element('#deadline-agenda').innerHTML,/Mark seen/);
assert.doesNotMatch(element('#deadline-agenda').innerHTML,/Finished/);
vm.runInContext('workspaceState.reminderRows[0].read=true;renderSchedule()',ctx);
assert.doesNotMatch(element('#deadline-agenda').innerHTML,/Mark seen/);
assert.match(element('#deadline-agenda').innerHTML,/New &lt;project>/);
console.log('v2.3.6 workspace checks passed: status visibility, views, search, links, escaping and merged reminders.');

element('#project-search').value='';
vm.runInContext("workspaceState.filter='all';workspaceState.boardSort='name';renderProjectBoard()",ctx);
assert.ok(element('#project-board').innerHTML.indexOf('Finished')<element('#project-board').innerHTML.indexOf('New &lt;project>'));
vm.runInContext("workspaceState.boardSort='name-desc';renderProjectBoard()",ctx);
assert.ok(element('#project-board').innerHTML.indexOf('Finished')>element('#project-board').innerHTML.indexOf('New &lt;project>'));
ctx.state.projects[1].submission_deadline='';
vm.runInContext("workspaceState.boardSort='deadline';renderProjectBoard()",ctx);
assert.ok(element('#project-board').innerHTML.indexOf('Finished')>element('#project-board').innerHTML.indexOf('New &lt;project>'));
console.log('Sort checks passed, including undated projects last.');

ctx.state.projects[0].totals={quoted:100};ctx.state.projects[1].totals={quoted:500};
vm.runInContext("workspaceState.boardSort='cost-high';renderProjectBoard()",ctx);
assert.ok(element('#project-board').innerHTML.indexOf('Finished')<element('#project-board').innerHTML.indexOf('New &lt;project>'));
vm.runInContext("workspaceState.boardSort='cost-low';renderProjectBoard()",ctx);
assert.ok(element('#project-board').innerHTML.indexOf('Finished')>element('#project-board').innerHTML.indexOf('New &lt;project>'));
console.log('Total-cost ordering checks passed.');
