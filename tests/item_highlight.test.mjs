import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function createContext(canEdit=true){
 const source=readFileSync(new URL('../assets/estimate_workspace.js',import.meta.url),'utf8');
 const core=source.slice(source.indexOf('// 0 = clear, 1 = yellow'),source.indexOf('function scopeKey(category)'));
 const classes=new Set(),attrs=new Map(),errors=[];
 const row={classList:{toggle:(key,enabled)=>enabled?classes.add(key):classes.delete(key)}};
 const button={dataset:{lineId:'120'},disabled:false,setAttribute:(key,val)=>attrs.set(key,val),closest:()=>row,title:''};
 const state={view:'estimate',projectId:11,projectData:{project:{id:11,can_edit:canEdit},lines:[{id:120,highlight_level:0}]}};
 let remoteLevel=0,calls=0;
 const api=async(path,opts={})=>{
   calls++;
   if(path.endsWith('/highlights'))return {highlights:[{id:120,level:remoteLevel}]};
   assert.equal(path,'/api/projects/11/lines/120/highlight');
   assert.equal(opts.method,'PATCH');
   if(opts.body.expected_level!==remoteLevel){const error=new Error('Changed elsewhere');error.status=409;throw error;}
   remoteLevel=opts.body.level;
   return {id:120,level:remoteLevel};
 };
 const context={state,api,Set,Number,String,document:{hidden:false},toast:(message)=>errors.push(message),
  $:selector=>selector.includes('120')?button:null};
 vm.createContext(context);
 vm.runInContext(core+'\nthis.actions={estimateLineHighlightLevel,toggleEstimateHighlight,refreshEstimateHighlights,showEstimateHighlight};',context);
 return {context,button,classes,attrs,errors,getRemote:()=>remoteLevel,setRemote:v=>{remoteLevel=v},calls:()=>calls};
}
test('click cycles yellow -> red -> clear on the shared project, not localStorage',async()=>{
 const c=createContext();
 for(const [level,color] of [[1,'catalog-highlight-yellow'],[2,'catalog-highlight-red'],[0,null]]){
  await c.context.actions.toggleEstimateHighlight(c.button);
  assert.equal(c.getRemote(),level);
  assert.equal(c.context.actions.estimateLineHighlightLevel(120),level);
  if(color)assert.ok(c.classes.has(color));
  else assert.equal(c.classes.size,0);
 }
 assert.equal(c.attrs.get('aria-pressed'),'false');
 assert.equal(c.calls(),3);
});
test('a remote change updates an open editor without resetting inputs',async()=>{
 const c=createContext();
 c.setRemote(2);
 await c.context.actions.refreshEstimateHighlights();
 assert.equal(c.context.actions.estimateLineHighlightLevel(120),2);
 assert.ok(c.classes.has('catalog-highlight-red'));
 assert.equal(c.calls(),1);
});
test('read-only viewers can see colours but cannot change them',async()=>{
 const c=createContext(false);
 c.setRemote(1);
 await c.context.actions.refreshEstimateHighlights();
 await c.context.actions.toggleEstimateHighlight(c.button);
 assert.equal(c.context.actions.estimateLineHighlightLevel(120),1);
 assert.equal(c.calls(),1); // one GET, no PATCH
 assert.ok(c.errors.some(x=>/read-only/i.test(x)));
});
