/** Bound headers AND body reads. Never retry mutations with uncertain outcomes. */
export async function request(url:string,options:RequestInit={},timeoutMs?:number){
 const readOnly=['GET','HEAD'].includes((options.method||'GET').toUpperCase());
 const controller=new AbortController();
 const abort=()=>controller.abort();
 if(options.signal?.aborted)abort();
 options.signal?.addEventListener('abort',abort,{once:true});
 const timer=setTimeout(abort,timeoutMs??(readOnly?90000:120000));
 try{
  const response=await fetch(url,{...options,signal:controller.signal});
  const body=await response.arrayBuffer();
  return new Response([204,205,304].includes(response.status)?null:body,{status:response.status,statusText:response.statusText,headers:response.headers});
 }catch(error){
  if(options.signal?.aborted)throw error;
  if(controller.signal.aborted||error instanceof TypeError)throw new Error(readOnly?'Connection interrupted or the server took too long. Please retry.':'Connection interrupted while saving. The change may have reached the server. Refresh and check before submitting again.');
  throw error;
 }finally{clearTimeout(timer);options.signal?.removeEventListener('abort',abort)}
}
