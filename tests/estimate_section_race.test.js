/* Delayed reads must never undo a successfully saved section inclusion. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync('assets/app.js','utf8'),workspace=fs.readFileSync('assets/estimate_workspace.js','utf8');
const base={project:{id:1,revision:1,can_edit:true,excluded_categories:'[]'},lines:[{id:11,revision:0,category_snapshot:'Lighting',included_in_total:true,quoted_total:100}],totals:{quoted:100}};
const saved={project:{...base.project,revision:2,excluded_categories:'["Lighting"]'},lines:[{...base.lines[0],included_in_total:false}],totals:{quoted:0}};

function setup(){
 const table={setAttribute(){},removeAttribute(){}},pending=[],reviews=[];
 const ctx={state:{projectId:1,projectData:structuredClone(base),projects:[structuredClone(base.project)],projectLoadRequest:0},
   estimateViewState:{busy:false},FormData:class{},AbortController,structuredClone,TypeError,SyntaxError,Error,setTimeout,clearTimeout,
   $:()=>table,toast(){},renderProject(){},renderProjectSelect(){},renderGroupedEstimate(){},showLogin(){},
   reviewOpenedProject:async project=>reviews.push(project.revision),
   fetch:(path,config)=>new Promise(resolve=>pending.push({path,config,finish:data=>resolve({status:200,ok:true,headers:{get:()=> 'application/json'},json:async()=>data})}))};
 vm.createContext(ctx);
 vm.runInContext(app.slice(app.indexOf('const pendingApiReads='),app.indexOf('let toastTimer')),ctx);
 vm.runInContext(app.slice(app.indexOf('async function loadProject('),app.indexOf('function renderProject()')),ctx);
 vm.runInContext(workspace.slice(workspace.indexOf('async function estimateOperation('),workspace.indexOf('function lineById')),ctx);
 return {ctx,pending,reviews};
}

(async()=>{
 // A previously requested refresh finishes after the successful Off response.
 {
  const {ctx,pending,reviews}=setup();
  const refresh=ctx.loadProject(1),generation=ctx.state.projectLoadRequest;
  const toggle=ctx.estimateOperation('/api/projects/1/sections/inclusion',{category:'Lighting',included:false},ctx.state.projectData.project);
  assert.equal(ctx.state.projectLoadRequest,generation+1);
  assert.equal(JSON.parse(pending[1].config.body)._known_lines,undefined);
  pending[1].finish(structuredClone(saved));await toggle;
  pending[0].finish(structuredClone(base));assert.equal(await refresh,false);
  assert.equal(ctx.state.projectData.project.revision,2);
  assert.equal(ctx.state.projectData.lines[0].included_in_total,false);
  assert.equal(ctx.state.projectData.totals.quoted,0);
  assert.equal(reviews.length,0);
 }
 // A read starts during the write, so request ordering alone cannot reject it.
 {
  const {ctx,pending}=setup();
  const toggle=ctx.estimateOperation('/api/projects/1/sections/inclusion',{category:'Lighting',included:false},ctx.state.projectData.project);
  const refresh=ctx.loadProject(1);
  pending[0].finish(structuredClone(saved));await toggle;
  pending[1].finish(structuredClone(base));assert.equal(await refresh,false);
  assert.equal(ctx.state.projectData.project.revision,2);
  assert.equal(ctx.state.projectData.lines[0].included_in_total,false);
  assert.equal(ctx.state.projectData.totals.quoted,0);
  // A genuinely newer response is still accepted normally.
  const latest=ctx.loadProject(1),newer={...structuredClone(saved),project:{...saved.project,revision:3}};
  pending[2].finish(newer);assert.equal((await latest).project.revision,3);
  assert.equal(ctx.state.projectData.project.revision,3);
 }
 console.log('Section race checks passed: earlier and in-flight stale GETs cannot overwrite saved totals; fresh revisions still load.');
})().catch(error=>{console.error(error);process.exitCode=1});
