const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const text=fs.readFileSync('assets/workspace.js','utf8'),events=[],classes=new Set(),elements={};
let sessionFail=false;
const ctx={Event,window:{dispatchEvent(){}},URLSearchParams,location:{search:'',replace:path=>events.push(path)},document:{body:{classList:{add:x=>classes.add(x),remove:x=>classes.delete(x)}}},
 $:s=>elements[s]||(elements[s]={textContent:'',classList:{add(){},remove(){}}}),state:{user:{id:1}},
 setAccount:()=>events.push('account'),loadSettings:async()=>events.push('settings'),loadDashboard:async()=>events.push('dashboard'),
 restorePage:async()=>{assert.ok(classes.has('app-loading'));events.push('route')},setView:()=>events.push('view'),
 api:async()=>{if(sessionFail)throw new Error('offline');return {user:{id:1},csrf_token:'token'}},showLogin:()=>events.push('login')};
vm.createContext(ctx);vm.runInContext(text.slice(text.indexOf('async function enterWorkspace('),text.indexOf('async function submitWithButton')),ctx);
(async()=>{
 await ctx.bootWorkspace();assert.deepEqual(events,['account','settings','dashboard','route']);assert.ok(!classes.has('app-loading'));
 events.length=0;ctx.window.__estimatorBoot=Promise.resolve({user:{id:1},csrf_token:'token',dashboard:{projects:[]},settings:{}});await ctx.bootWorkspace();assert.deepEqual(events,['account','settings','dashboard','route']);assert.equal(ctx.window.__estimatorBoot,undefined);
 events.length=0;ctx.location.search='?return=tenders';await ctx.bootWorkspace();assert.deepEqual(events,['account','/tenders/']);ctx.location.search='';
 sessionFail=true;events.length=0;await ctx.bootWorkspace();assert.deepEqual(events,[]);assert.ok(classes.has('app-loading'));assert.equal(elements['#startup-message'].textContent,'offline');
 console.log('Startup checks passed: restore behind loading screen; network failure does not show login.');
})().catch(e=>{console.error(e);process.exitCode=1});
