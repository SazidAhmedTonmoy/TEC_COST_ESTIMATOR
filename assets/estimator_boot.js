// Start authenticated data loading while the Estimator bundle downloads.
(()=>{
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),90000);
 window.__estimatorBoot=fetch('/api/bootstrap',{signal:controller.signal,credentials:'same-origin'}).then(async response=>{
  if(!response.ok)return {error:response.status===401?'Please sign in to continue':'The server is busy or unavailable. Please retry.',status:response.status};
  return response.json();
 }).catch(()=>({error:'Connection interrupted or the server took too long. Please retry.'})).finally(()=>clearTimeout(timer));
})();
