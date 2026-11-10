import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function createContext(raw='{}'){
 const source=readFileSync(new URL('../assets/estimate_workspace.js',import.meta.url),'utf8');
 const core=source.slice(source.indexOf('const estimateHighlightCache'),source.indexOf('function scopeKey(category)'));
 const local=new Map([['tec-estimate-highlight:7:11',raw]]);
 const context={state:{user:{id:7},projectId:11},localStorage:{getItem:k=>local.get(k),setItem:(k,v)=>local.set(k,v)},Map,Set,JSON,Object,String,Array};
 vm.createContext(context);
 vm.runInContext(core+'\nthis.actions={estimateHighlights,estimateLineHighlightLevel,toggleEstimateHighlight};',context);
 return {ctx:context,store:local};
}
function button(id){
 const classes=new Set();const attrs=new Map();
 const row={classList:{toggle:(key,yes)=>yes?classes.add(key):classes.delete(key)}};
 return {dataset:{lineId:id},setAttribute:(key,val)=>attrs.set(key,val),closest:()=>row,classes,attrs};
}
test('click cycles yellow -> red -> clear and stores the state',()=>{
 const {ctx,store}=createContext();const marker=button('120');
 assert.equal(ctx.actions.estimateLineHighlightLevel(120),0);
 ctx.actions.toggleEstimateHighlight(marker);
 assert.equal(ctx.actions.estimateLineHighlightLevel(120),1);
 assert.ok(marker.classes.has('catalog-highlight-yellow'));
 ctx.actions.toggleEstimateHighlight(marker);
 assert.equal(ctx.actions.estimateLineHighlightLevel(120),2);
 assert.ok(marker.classes.has('catalog-highlight-red'));
 assert.ok(!marker.classes.has('catalog-highlight-yellow'));
 ctx.actions.toggleEstimateHighlight(marker);
 assert.equal(ctx.actions.estimateLineHighlightLevel(120),0);
 assert.ok(!marker.classes.has('catalog-highlight-red'));
 assert.equal(marker.attrs.get('aria-pressed'),'false');
 assert.equal(store.get('tec-estimate-highlight:7:11'),'{}');
});
test('old string-array highlights remain yellow',()=>{
 const {ctx}=createContext('["120", "121"]');
 assert.equal(ctx.actions.estimateLineHighlightLevel(120),1);
 assert.equal(ctx.actions.estimateLineHighlightLevel(121),1);
});
