/** Bounded retries for idempotent reads. Mutations are never replayed: a timeout
 * after POST/PATCH/DELETE does not prove that the server failed to commit. */
const transientStatuses=new Set([408,429,502,503,504]);
const pause=(ms:number,signal?:AbortSignal)=>new Promise<void>((resolve,reject)=>{
  if(signal?.aborted){reject(new DOMException('Request cancelled','AbortError'));return;}
  const done=()=>{clearTimeout(timer);signal?.removeEventListener('abort',cancel);};
  const cancel=()=>{done();reject(new DOMException('Request cancelled','AbortError'));};
  const timer=setTimeout(()=>{done();resolve()},ms);
  signal?.addEventListener('abort',cancel,{once:true});
});
export async function request(url:string,options:RequestInit={},timeoutMs?:number){
 const readOnly=['GET','HEAD'].includes((options.method||'GET').toUpperCase());
 const attempts=readOnly?3:1;
 for(let attempt=0;attempt<attempts;attempt++){
  if(options.signal?.aborted)throw new DOMException('Request cancelled','AbortError');
  const controller=new AbortController();
  const abort=()=>controller.abort();
  options.signal?.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(abort,timeoutMs??(readOnly?45000:120000));
  try{
   const response=await fetch(url,{...options,signal:controller.signal});
   if(readOnly&&attempt<attempts-1&&transientStatuses.has(response.status)){
    // Do not read the possibly large error body or replay state-changing actions.
    await pause(600*(attempt+1),options.signal??undefined);continue;
   }
   // Bound the entire response body, not just the response headers.
   const body=await response.arrayBuffer();
   return new Response([204,205,304].includes(response.status)?null:body,{status:response.status,statusText:response.statusText,headers:response.headers});
  }catch(error){
   if(options.signal?.aborted)throw error;
   const isConnectionError=controller.signal.aborted||error instanceof TypeError;
   if(isConnectionError&&readOnly&&attempt<attempts-1){await pause(600*(attempt+1),options.signal??undefined);continue;}
   if(isConnectionError)throw new Error(readOnly?'Connection interrupted or the server took too long after automatic retries. Please retry.':'Connection interrupted while saving. The change may have reached the server. Refresh and check before submitting again.');
   throw error;
  }finally{clearTimeout(timer);options.signal?.removeEventListener('abort',abort)}
 }
 throw new Error('Unable to retrieve the latest information. Please retry.');
}
