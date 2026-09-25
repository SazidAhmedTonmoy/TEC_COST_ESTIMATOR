/* One small shared transition; never fetches the other workspace's data. */
(()=>{
 const html=document.documentElement,key='conest-workspace-switch';
 const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
 let timeout,cleanup;
 function finish(){
  if(!html.hasAttribute('data-swap')||html.classList.contains('workspace-reveal'))return;
  clearTimeout(timeout);html.classList.add('workspace-reveal');
  cleanup=setTimeout(()=>{html.removeAttribute('data-swap');html.removeAttribute('data-swap-label');html.classList.remove('workspace-reveal')},1050);
 }
 try{
  const saved=JSON.parse(sessionStorage.getItem(key)||'null');sessionStorage.removeItem(key);
  const target=location.pathname.startsWith('/tenders/')?'tenders':'estimator';
  if(saved&&saved.target===target&&Date.now()-saved.at<15000&&!reduced()){
   html.dataset.swap=target;html.dataset.swapLabel=target==='tenders'?'TENDERS':'ESTIMATOR';
   window.addEventListener('conest:workspace-ready',()=>requestAnimationFrame(()=>requestAnimationFrame(finish)),{once:true});
   // Never leave an overlay blocking a slow/offline page or its error/retry UI.
   timeout=setTimeout(finish,1800);
  }
 }catch{}
 document.addEventListener('click',event=>{
  if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||reduced())return;
  const link=event.target.closest?.('a.workspace-swap');if(!link||link.target==='_blank')return;
  const url=new URL(link.href,location.href);if(url.origin!==location.origin)return;
  const target=url.pathname.startsWith('/tenders/')?'tenders':'estimator';
  document.querySelector('.workspace-departure')?.remove();
  const progress=document.createElement('div');progress.className='workspace-departure';progress.dataset.target=target;progress.setAttribute('role','status');progress.setAttribute('aria-label','Loading '+target);
  const spinner=document.createElement('div');spinner.className='loader';progress.append(spinner);document.body.append(progress);
  setTimeout(()=>progress.remove(),15000);
  try{sessionStorage.setItem(key,JSON.stringify({target:url.pathname.startsWith('/tenders/')?'tenders':'estimator',at:Date.now()}))}catch{}
 });
 window.addEventListener('pageshow',event=>{document.querySelector('.workspace-departure')?.remove();if(event.persisted){clearTimeout(timeout);clearTimeout(cleanup);html.removeAttribute('data-swap');html.removeAttribute('data-swap-label');html.classList.remove('workspace-reveal')}});
})();
