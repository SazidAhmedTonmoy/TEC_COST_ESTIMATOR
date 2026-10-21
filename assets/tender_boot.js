/* Read the complete bootstrap response, including safe server error details. */
(()=>{
 let pending=null;
 window.conestTenderStart=()=>{
  if(pending)return pending;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),90000);
  pending=(async()=>{
   let response;
   try{
    response=await fetch('/api/tenders/bootstrap',{signal:controller.signal,cache:'no-store',credentials:'same-origin',headers:{Accept:'application/json'}});
    // Authentication failures go straight to the existing sign-in screen.
    if(response.status===401)return {status:401,ok:false,data:null,format:'json'};
    const jsonType=/\bjson\b/i.test(response.headers.get('Content-Type')||'');
    const text=await response.text();
    let data=null,format=jsonType?'invalid-json':'other';
    if(jsonType){try{data=JSON.parse(text);format='json'}catch{}}
    // HTML gateway pages and tracebacks are never copied into the UI.
    return {status:response.status,ok:response.ok,data,format};
   }catch{
    return {status:response?.status||0,ok:false,data:null,format:'other',failure:controller.signal.aborted?'timeout':'network'};
   }finally{clearTimeout(timer)}
  })().finally(()=>{pending=null});
  return pending;
 };
 window.__tenderBoot=window.conestTenderStart();
})();
