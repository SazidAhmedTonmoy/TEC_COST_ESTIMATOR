const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const test=require('node:test');
const ts=require('../tenders_frontend/node_modules/typescript');

const bootstrapCode=fs.readFileSync('assets/tender_boot.js','utf8');
const startup={};
vm.runInNewContext(ts.transpile(fs.readFileSync('tenders_frontend/src/lib/startup.ts','utf8'),{module:ts.ModuleKind.CommonJS}),{exports:startup});
const successBody={user:{id:1,name:'Startup test',role:'admin',must_change_password:false},csrf_token:'test-token',
  data:{submissions:[],chases:[],reminders:[],teams:[],settings:{author:'Startup test',defaultDays:7}}};
function transport(fetch,timeout=90000){
  const window={};
  vm.runInNewContext(bootstrapCode,{window,fetch,AbortController,setTimeout:(fn)=>setTimeout(fn,timeout),clearTimeout});
  return window;
}
const json=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json; charset=utf-8'}});

test('HTTP500 JSON retains its safe error reference, code and administrator message',async()=>{
  const window=transport(async()=>json({error:'The Tender database could not be opened. Ask your administrator to check the server log.',error_reference:'abc123456789',error_code:'TENDERS_STARTUP_FAILED'},500));
  const response=await window.__tenderBoot;
  assert.equal(response.status,500);assert.equal(response.ok,false);
  const problem=startup.startupProblem(response);
  assert.equal(problem.status,500);assert.equal(problem.reference,'abc123456789');
  assert.equal(problem.code,'TENDERS_STARTUP_FAILED');
  assert.match(problem.message,/Tender database could not be opened/);
  assert.doesNotMatch(problem.title,/session/i);
  const sessionFailure=startup.startupProblem({status:503,ok:false,data:{error_code:'SESSION_STARTUP_FAILED',error_reference:'123456abcdef'}});
  assert.match(sessionFailure.title,/sign-in/);assert.equal(sessionFailure.status,503);
});

test('HTML502 and malformed JSON are diagnosed without rendering response markup',async()=>{
  const window=transport(async()=>new Response('<html>Passenger failed at /srv/private/app.py</html>',{status:502,headers:{'Content-Type':'text/html'}}));
  const response=await window.__tenderBoot;
  assert.equal(response.status,502);assert.equal(response.data,null);
  const problem=startup.startupProblem(response);
  assert.equal(problem.status,502);assert.match(problem.title,/temporarily unavailable/);
  assert.doesNotMatch(JSON.stringify(problem),/html|private|app\.py/);
  const malformed=transport(async()=>new Response('{broken',{headers:{'Content-Type':'application/json'}}));
  const invalid=await malformed.__tenderBoot;
  assert.equal(invalid.format,'invalid-json');assert.equal(invalid.data,null);
  assert.equal(startup.startupProblem(invalid).action,'reload');
});

test('401 is retained for normal sign-in redirect, even when the error body is not JSON',async()=>{
  const window=transport(async()=>new Response('Sign in',{status:401,headers:{'Content-Type':'text/html'}}));
  const response=await window.__tenderBoot;
  assert.equal(response.status,401);assert.equal(response.ok,false);assert.equal(response.failure,undefined);
});

test('Concurrent startup attempts share a request; retry makes a fresh uncached request',async()=>{
  let calls=0,release;
  const window=transport(async(url,options)=>{
    calls++;assert.equal(url,'/api/tenders/bootstrap');assert.equal(options.cache,'no-store');assert.equal(options.credentials,'same-origin');
    if(calls===1)return await new Promise(resolve=>{release=resolve});
    return json(successBody);
  });
  const first=window.__tenderBoot;
  assert.equal(window.conestTenderStart(),first);assert.equal(window.conestTenderStart(),first);assert.equal(calls,1);
  release(json({error:'The database is busy. Please retry shortly.'},503));
  assert.equal((await first).status,503);
  const retry=await window.conestTenderStart();
  assert.equal(calls,2);assert.equal(retry.status,200);
  assert.equal(startup.validBootstrapSession(retry.data),true);
  assert.equal(startup.validTenderData(retry.data.data),true);
});

test('Connection failures and a stalled response body have distinct retry messages',async()=>{
  const offline=transport(async()=>{throw new TypeError('Failed to fetch')});
  const network=await offline.__tenderBoot;
  assert.equal(network.failure,'network');assert.match(startup.startupProblem(network).title,/connect/);
  const slow=transport(async(url,options)=>({status:200,ok:true,headers:new Headers({'Content-Type':'application/json'}),
    text:()=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted'))))}),10);
  const timedOut=await slow.__tenderBoot;
  assert.equal(timedOut.failure,'timeout');assert.match(startup.startupProblem(timedOut).title,/too long/);
});

test('Bootstrap payload checks reject missing session/CSRF/data without rejecting valid empty workspaces',()=>{
  assert.equal(startup.validBootstrapSession(successBody),true);
  assert.equal(startup.validTenderData(successBody.data),true);
  for(const value of [null,[],{}, {user:{id:1}}, {...successBody,csrf_token:''}, {...successBody,user:{id:'1',name:'Test',role:'user'}}])
    assert.equal(startup.validBootstrapSession(value),false);
  for(const value of [null,[],{}, {...successBody.data,settings:null}, {...successBody.data,submissions:{}}, {...successBody.data,reminders:null}])
    assert.equal(startup.validTenderData(value),false);
  assert.equal(startup.validBootstrapSession({user:{...successBody.user,must_change_password:true},csrf_token:'test-token'}),true);
});

test('A safe error reference is retained while exception paths and markup are suppressed',()=>{
  for(const error of ['Traceback: File "/srv/private/app.py"','Cannot open /home/example/data.db',"Cannot open '/home/example/data.db'",'Cannot open C:\\private\\data.db','<script>secret</script>']){
    const problem=startup.startupProblem({status:500,ok:false,data:{error,error_reference:'abc123456789'}});
    assert.equal(problem.reference,'abc123456789');assert.notEqual(problem.message,error);
    assert.doesNotMatch(problem.message,/private|example|script|Traceback/);
  }
  const problem=startup.startupProblem({status:500,ok:false,data:{error_reference:'/srv/private',error_code:'<script>'}});
  assert.equal(problem.reference,undefined);assert.equal(problem.code,undefined);
});
