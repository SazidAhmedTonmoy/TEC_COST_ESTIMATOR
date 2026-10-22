/* Imported whitespace aliases must act as one displayed estimate section. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const workspace=fs.readFileSync('assets/estimate_workspace.js','utf8');
const lines=[
  {id:1,category_snapshot:'Cable  Tray',category_key:'Cable Tray',included_in_total:false,quoted_total:10},
  {id:2,category_snapshot:' \tCable\u00a0Tray ',category_key:'Cable Tray',included_in_total:false,quoted_total:20},
  {id:3,category_snapshot:'Power',category_key:'Power',included_in_total:true,quoted_total:30},
];
const nodes=new Map(),saved=[];
function node(id){if(!nodes.has(id))nodes.set(id,{innerHTML:'',classList:{contains:()=>false,toggle(){}},setAttribute(){}});return nodes.get(id);}
const ctx={state:{projectId:1,projectData:{project:{id:1,revision:2,currency:'AUD',can_edit:true},lines},view:'estimate'},
  $:node,$$:()=>[],escapeHtml:value=>String(value),fmtMoney:value=>`$${value}`,fmtNumber:value=>String(value),
  renderEstimateLine:line=>`<tr data-line="${line.id}"></tr>`,syncCategoryToggle(){},syncExpandEstimateAll(){},toast(){},
  estimateOperation:async(path,payload)=>saved.push({path,payload})};
vm.createContext(ctx);
vm.runInContext(workspace.slice(0,workspace.indexOf('async function estimateOperation(')),ctx);
vm.runInContext(workspace.slice(workspace.indexOf('function moveId('),workspace.indexOf('function clearDropHint(')),ctx);

(async()=>{
  // Legacy revision fallback has the same whitespace identity as calculated lines.
  for(const raw of ['Cable  Tray',' Cable\tTray ','Cable\u00a0Tray','Cable\u0085Tray']){
    assert.equal(ctx.estimateSectionName({category_snapshot:raw}),'Cable Tray');
  }
  assert.equal(ctx.estimateSectionName({category_snapshot:'\t\u00a0 '}),'Other');
  assert.equal(ctx.estimateSectionName({category_snapshot:'raw',category_key:'Authoritative'}),'Authoritative');
  assert.deepEqual(Array.from(ctx.scopeNames()),['Cable Tray','Power']);
  ctx.renderGroupedEstimate(lines);
  let markup=node('#estimate-lines').innerHTML;
  assert.equal((markup.match(/class="scope-divider/g)||[]).length,2);
  assert.equal((markup.match(/role="switch" aria-checked="false" data-scope="Cable Tray"/g)||[]).length,1);
  assert.ok(markup.includes('Optional cost'));
  assert.ok(markup.includes('Quoted Total <b>$30</b>'));
  assert.ok(markup.includes('data-line="1"')&&markup.includes('data-line="2"'));
  vm.runInContext("estimateViewState.collapsed.add(scopeKey('Cable Tray'));",ctx);
  ctx.renderGroupedEstimate(lines);
  markup=node('#estimate-lines').innerHTML;
  assert.ok(!markup.includes('data-line="1"')&&!markup.includes('data-line="2"'));
  assert.ok(markup.includes('data-line="3"'));
  await ctx.moveScope('Power','Cable Tray',false);
  assert.equal(saved[0].path,'/api/projects/1/reorder');
  assert.deepEqual(Array.from(saved[0].payload.ids),[3,1,2]);
  assert.deepEqual(Array.from(saved[0].payload.scope_order),['Power','Cable Tray']);
  assert.equal(lines[0].category_snapshot,'Cable  Tray');
  assert.equal(lines[1].category_snapshot,' \tCable\u00a0Tray ');
  console.log('Section key checks passed: one switch, totals, collapse and order cover all raw whitespace aliases.');
})().catch(error=>{console.error(error);process.exitCode=1});
