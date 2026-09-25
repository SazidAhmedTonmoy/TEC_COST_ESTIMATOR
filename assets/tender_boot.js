window.conestTenderStart=()=>{
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),90000);
 return fetch('/api/tenders/bootstrap',{signal:controller.signal}).then(async response=>({status:response.status,ok:response.ok,data:response.ok?await response.json():null})).catch(()=>null).finally(()=>clearTimeout(timer));
};
window.__tenderBoot=window.conestTenderStart();
