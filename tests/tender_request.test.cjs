const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),ts=require('../tenders_frontend/node_modules/typescript');
const out={};let implementation,calls=0;
vm.runInNewContext(ts.transpile(fs.readFileSync('tenders_frontend/src/lib/request.ts','utf8'),{module:ts.ModuleKind.CommonJS}),{exports:out,fetch:(...args)=>{calls++;return implementation(...args)},Response,AbortController,TypeError,setTimeout,clearTimeout});
(async()=>{
 implementation=async()=>new Response('{"ok":true}',{headers:{'Content-Type':'application/json'}});
 assert.deepEqual(await (await out.request('/test')).json(),{ok:true});
 // Simulate headers arriving followed by a stalled response body.
 implementation=async(url,options)=>({arrayBuffer:()=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted')))),status:200,headers:new Headers()});
 await assert.rejects(out.request('/test',{},10),/took too long/);
 calls=0;await assert.rejects(out.request('/test',{method:'POST'},10),/may have reached the server/);assert.equal(calls,1);
 implementation=async()=>new Response(null,{status:204});assert.equal((await out.request('/test')).status,204);
 console.log('PASS: body timeout, successful response, empty response and no mutation retry.');
})().catch(e=>{console.error(e);process.exitCode=1});
