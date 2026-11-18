import test from 'node:test';
import assert from 'node:assert/strict';
import {request} from '../tenders_frontend/src/lib/request.ts';
const originalFetch=globalThis.fetch;
test.after(()=>{globalThis.fetch=originalFetch});
test('GET retries transient 503 and preserves final JSON body',async()=>{
 let calls=0;
 globalThis.fetch=async()=>{calls++;return calls===1?new Response('temporary',{status:503}):Response.json({ok:true})};
 const response=await request('/test');
 assert.equal(calls,2);assert.deepEqual(await response.json(),{ok:true});
});
test('POST is never retried after a network interruption',async()=>{
 let calls=0;
 globalThis.fetch=async()=>{calls++;throw new TypeError('network unavailable')};
 await assert.rejects(request('/test',{method:'POST',body:'{}'}),/while saving/);
 assert.equal(calls,1);
});
test('cancelled GET is not retried',async()=>{
 let calls=0;const controller=new AbortController();
 globalThis.fetch=async()=>{calls++;controller.abort();throw new DOMException('Cancelled','AbortError')};
 await assert.rejects(request('/test',{signal:controller.signal}),/Cancelled/);
 assert.equal(calls,1);
});
