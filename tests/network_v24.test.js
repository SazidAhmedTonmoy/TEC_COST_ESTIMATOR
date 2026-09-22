const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/app.js','utf8');
let calls=0,logout=0,handler;
const ctx={state:{csrfToken:'token',user:{id:1}},FormData:class{},AbortController,TypeError,SyntaxError,Error,
 setTimeout:(f,ms)=>ms===400?setTimeout(f,0):setTimeout(f,ms),clearTimeout,
 showLogin:()=>logout++,fetch:async(...args)=>{calls++;return handler(...args)}};
vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('async function api('),source.indexOf('let toastTimer')),ctx);
const response=(status,data,type='application/json')=>({status,ok:status<400,headers:{get:()=>type},json:async()=>data,body:{cancel:async()=>{}}});
(async()=>{
 handler=async()=>{if(calls===1)throw new TypeError('Failed to fetch');return response(200,{success:true})};
 await ctx.api('/api/projects');assert.equal(calls,2);assert.equal(logout,0);
 calls=0;handler=async()=>{throw new TypeError('Failed to fetch')};
 await assert.rejects(ctx.api('/api/projects',{method:'POST',body:{name:'New'}}),/may have reached the server/);assert.equal(calls,1);
 calls=0;handler=async()=>response(calls===1?503:200,{success:true});await ctx.api('/api/projects');assert.equal(calls,2);
 calls=0;handler=async()=>response(401,{error:'Sign in'});await assert.rejects(ctx.api('/api/projects'));assert.equal(calls,1);assert.equal(logout,1);
 handler=async()=>response(200,null,'text/html');await assert.rejects(ctx.api('/api/projects'),/unexpected response/);
 console.log('Network checks passed: safe read recovery, no write replay, authentication and invalid responses.');
})().catch(e=>{console.error(e);process.exitCode=1});
