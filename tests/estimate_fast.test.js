const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync('assets/app.js','utf8'),workspace=fs.readFileSync('assets/estimate_workspace.js','utf8');
const base={project:{id:1,revision:1,can_edit:true},lines:[{id:1,revision:0,quantity:3},{id:2,revision:0,quantity:5}],totals:{quoted:99}};
const table={setAttribute(){},removeAttribute(){}},renders=[],ctx={state:{projectId:1,projectData:structuredClone(base)},estimateViewState:{busy:false},$:()=>table,toast(){},renderGroupedEstimate:lines=>renders.push(lines.map(l=>l.id)),renderProject(){},api:null};
vm.createContext(ctx);vm.runInContext(app.slice(app.indexOf('function mergeEstimateResponse('),app.indexOf('let toastTimer')),ctx);
let changed=ctx.mergeEstimateResponse({estimate_delta:true,project:{id:1,revision:2},lines:[{id:2,revision:1,quantity:7}],line_order:[2,1],totals:{quoted:101}},base);
assert.equal(changed.lines[0].quantity,7);assert.equal(changed.lines[1].quantity,3);assert.equal(base.lines[1].quantity,5);assert.equal(changed.totals.quoted,101);
changed=ctx.mergeEstimateResponse({estimate_order:true,project:{id:1,revision:2},line_order:[2,1],line_versions:[{id:2,revision:1,sort_order:0}]},base);
assert.equal(changed.lines[0].revision,1);assert.equal(changed.totals.quoted,99);
assert.throws(()=>ctx.mergeEstimateResponse({estimate_delta:true,project:{id:2},line_order:[],lines:[]},base),/Estimate changed/);
vm.runInContext(workspace.slice(workspace.indexOf('async function estimateOperation('),workspace.indexOf('function lineById')),ctx);
(async()=>{
 let reject;ctx.api=()=>new Promise((_,r)=>reject=r);
 const pending=ctx.estimateOperation('/api/projects/1/reorder',{ids:[2,1]},base.project);
 assert.deepEqual(renders[0],[2,1]);assert.equal(table.inert,true);
 reject(new Error('Save failed'));await assert.rejects(pending,/Save failed/);
 assert.deepEqual(renders.at(-1),[1,2]);assert.equal(table.inert,false);assert.equal(ctx.estimateViewState.busy,false);
 console.log('Estimate delta merge, order acknowledgement, immediate reorder and rollback checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
