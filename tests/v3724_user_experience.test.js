const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const ROOT=path.join(__dirname,'..');
const read=name=>fs.readFileSync(path.join(ROOT,'assets',name),'utf8');
const elements=new Map();
function element(key){if(!elements.has(key)){
 const classes=new Set();elements.set(key,{value:'',innerHTML:'',dataset:{},disabled:false,classList:{toggle(name,on){if(on===undefined){if(classes.has(name)){classes.delete(name);return false;}classes.add(name);return true;}if(on)classes.add(name);else classes.delete(name);return on;},contains(name){return classes.has(name);},add(name){classes.add(name);},remove(name){classes.delete(name);}},setAttribute(){},querySelectorAll(){return [];}});
 }return elements.get(key);}
const esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const boardCtx={console,Date,Map,Set,document:{addEventListener(){}},$:(s)=>element(s),$$:()=>[],
 state:{user:{id:1,role:'admin'},projects:[]},sydneyMonth:()=> '2026-11',escapeHtml:esc,fmtMoney:n=>String(n||0),
 projectOutcome:()=>'',teamNames:()=>'',builderText:()=>'',dateLabel:s=>s||'',isOverdue:()=>false,projectStatus:()=>'',inReviewQueue:()=>false};
vm.createContext(boardCtx);
for(const file of ['builders.js','workspace.js'])vm.runInContext(read(file),boardCtx);
boardCtx.state.projects=[
 {id:1,name:'November project',status:'in_progress',created_at:'2026-11-03',submission_deadline:'2026-11-20',currency:'AUD',totals:{quoted:100}},
 {id:2,name:'Backlog from October',status:'submitted',created_at:'2026-10-03',submission_deadline:'2026-10-20',currency:'AUD',totals:{quoted:200}}
];
vm.runInContext("workspaceState.boardMonth='2026-11';workspaceState.filter='month';renderProjectBoard()",boardCtx);
assert.match(element('#project-board').innerHTML,/November project/);
assert.doesNotMatch(element('#project-board').innerHTML,/Backlog from October/);
element('#project-search').value='backlog';
vm.runInContext('renderProjectBoard()',boardCtx);
assert.match(element('#project-board').innerHTML,/Backlog from October/,'Search must ignore current month and status');
assert.doesNotMatch(element('#project-board').innerHTML,/November project/);
assert.equal(element('#project-search-scope').classList.contains('hidden'),false);
element('#project-search').value='';
vm.runInContext('renderProjectBoard()',boardCtx);
assert.doesNotMatch(element('#project-board').innerHTML,/Backlog from October/,'Clearing search must restore normal filtering');

const estimateCtx={console,Date,Map,Set,document:{addEventListener(){}},$:(s)=>element(s),$$:()=>[],
 state:{projectId:3,projectData:{project:{id:3,currency:'AUD',can_edit:true},lines:[]},view:'estimate'},
 estimateViewState:{collapsed:new Set(),expanded:new Set(),query:'',bulkCollapsed:true},
 scopeKey:c=>`3:${c}`,estimateSectionName:l=>l.category_key||l.category_snapshot||'Other',escapeHtml:esc,
 fmtMoney:n=>String(n||0),fmtNumber:n=>String(n||0),renderEstimateLine:()=>'<tr><td>Assembly</td></tr>',
 scopeNames:()=>[],fitEstimateText:()=>{},syncCategoryToggle:()=>{},syncExpandEstimateAll:()=>{},
 restoreEstimateViewPreferences:()=>{},saveEstimateViewPreferences:()=>{}};
const lines=[{id:11,category_key:'Lighting',total_material:100,quoted_total:150},{id:12,category_key:'Power',total_material:50,quoted_total:80}];
estimateCtx.state.projectData.lines=lines;
vm.createContext(estimateCtx);
const estimateSrc=read('estimate_workspace.js');
vm.runInContext(estimateSrc.slice(estimateSrc.indexOf('function renderGroupedEstimate(lines){'),estimateSrc.indexOf('async function estimateOperation(')),estimateCtx);
estimateCtx.estimateViewState.collapsed.add('3:Lighting');estimateCtx.estimateViewState.collapsed.add('3:Power');
vm.runInContext('renderGroupedEstimate(state.projectData.lines)',estimateCtx);
assert.equal(element('#estimate-columns-heading').classList.contains('hidden'),true,'Shrink All hides item-level heading');
estimateCtx.estimateViewState.collapsed.delete('3:Lighting');
vm.runInContext('renderGroupedEstimate(state.projectData.lines)',estimateCtx);
assert.equal(element('#estimate-columns-heading').classList.contains('hidden'),false,'Expanding a scope restores the heading');

const revisionCtx={console,Date,Map,Set,document:{addEventListener(){}},$:(s)=>element(s),$$:()=>[],escapeHtml:esc,
 fmtMoney:(v,c)=>`${c||'AUD'} ${Number(v||0).toFixed(2)}`,fmtNumber:v=>String(v),
 productivityState:{revisionRows:[],revisionRequest:0,revisionProject:42,revisionSelectedId:null},
 api:async(url)=>{
  assert.match(url,/\/api\/projects\/42\/revisions\/10\?((compare=current)|(view=1))/);
  return {snapshot:{project:{currency:'AUD'},lines:[{name_snapshot:'Downlight',reference_name:'D1',notes:'DALI dimming',quantity:10,uom:'EA',quoted_total:200,category_snapshot:'Lighting'}],totals:{material:100,hours:1,labor:70,quoted:200}},
   comparison:{before_currency:'AUD',after_currency:'AUD',before_totals:{material:100,hours:1,labor:70,quoted:200},after_totals:{material:120,hours:2,labor:80,quoted:230},changes:[{name:'Downlight',kind:'Changed',fields:{quantity:{before:10,after:12},quoted_total:{before:200,after:230}}}],settings:{}}};
 }};
vm.createContext(revisionCtx);
const ps=read('productivity.js');
vm.runInContext(ps.slice(ps.indexOf('function revisionRow('),ps.indexOf('function renderImportPreview(')),revisionCtx);
(async()=>{
 vm.runInContext("renderRevisions([{id:10,label:'Original',author:'Author',currency:'AUD',created_at:'2026-11-01T10:00:00Z',quoted:200,can_delete:true,can_redeploy:true}])",revisionCtx);
 assert.match(element('#revision-list').innerHTML,/data-view-revision="10"/);
 assert.match(element('#revision-list').innerHTML,/data-compare-revision="10"/);
 assert.doesNotMatch(element('#revision-list').innerHTML,/View & compare/);
 await vm.runInContext('viewRevision(10)',revisionCtx);
 assert.match(element('#revision-comparison').innerHTML,/Read-only saved snapshot/);
 assert.match(element('#revision-comparison').innerHTML,/Remarks: DALI dimming/);
 vm.runInContext('showRevisionComparePicker(10)',revisionCtx);
 assert.match(element('#revision-comparison').innerHTML,/Show differences/);
 element('#revision-compare-target').value='current';
 await vm.runInContext('compareRevision(10)',revisionCtx);
 assert.match(element('#revision-diff-results').innerHTML,/Changed estimate items/);
 assert.match(element('#revision-diff-results').innerHTML,/Saved: Original/);
 console.log('v3.7.24 UX tests passed: global search, collapsed estimate headers, separate revision view and compare.');
})().catch(e=>{console.error(e);process.exitCode=1;});
