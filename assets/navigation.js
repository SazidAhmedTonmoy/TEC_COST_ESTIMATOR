/* Hash addresses work on the existing Python server without rewrite rules.
   Native anchors retain Ctrl/Cmd-click, middle-click and Open in new tab. */
const pageNavigation={request:0,applying:0};
const pageNames=new Set(['home','estimate','calendar','catalog','users','imports','settings','profile','light-prices']);
function pageAddress(view,id){
  return `#/${view}${['estimate','catalog','light-prices'].includes(view)&&Number.isSafeInteger(Number(id))&&Number(id)>0?`/${Number(id)}`:''}`;
}
function currentPageRoute(){
  const parts=location.hash.replace(/^#\/?/,'').split('/');
  if(!pageNames.has(parts[0])||parts.length>2)return {view:'home',id:null};
  if(parts[1] && (!['estimate','catalog','light-prices'].includes(parts[0])||!/^\d+$/.test(parts[1])||!Number.isSafeInteger(Number(parts[1]))||Number(parts[1])<1))return {view:parts[0],id:null};
  return {view:parts[0],id:parts[1]?Number(parts[1]):null};
}
function updateEstimateLink(){
  const link=document.querySelector('.nav-button[data-view="estimate"]');
  if(link)link.href=pageAddress('estimate',state.projectId);
}
function rememberPage(view,id,replace=false){
  updateEstimateLink();
  if(!state.user||pageNavigation.applying)return;
  if(id===undefined)id=view==='estimate'?state.projectId:view==='catalog'?state.currentCatalogItem?.id:view==='light-prices'?lightPriceState.selected:null;
  const address=pageAddress(view,id);
  if(location.hash!==address)history[replace?'replaceState':'pushState'](null,'',address);
}
async function restorePage(){
  if(!state.user)return;
  const request=++pageNavigation.request;
  state.projectLoadRequest=(state.projectLoadRequest||0)+1;
  state.catalogDetailRequest=(state.catalogDetailRequest||0)+1;
  if(typeof lightPriceState!=='undefined')lightPriceState.detailRequest++;
  pageNavigation.applying++;
  const route=currentPageRoute();
  let id=route.id;
  try{
    setView(route.view,false,false);
    if(state.view!==route.view)id=null; // Existing role/setup restrictions remain authoritative.
    const view=state.view;
    if(view==='estimate'){
      // Remove another project's data while this URL is loading.
      state.projectId=null;state.projectData=null;renderProjectSelect();renderProject();
      if(id)await loadProject(id);
    }else if(view==='catalog'){
      state.currentCatalogItem=null;
      $('#catalog-detail').innerHTML='<p class="helper-text">Select a catalogue item to review.</p>';
      $('#catalog-detail').classList.add('empty-detail');
      await loadCatalog();
      if(request!==pageNavigation.request)return;
      if(id)await showCatalogDetail(id);
    }else if(view==='light-prices'){
      lightPriceState.selected=null;$('#light-price-detail').classList.add('hidden');await loadLightPrices();
      if(request!==pageNavigation.request)return;
      if(id)await showLightPrice(id);
    }else if(view==='users')await loadUsers();
    else if(view==='imports')await loadImports();
    else if(view==='settings'){
      await loadSettings();
      if(request===pageNavigation.request && typeof loadBackups==='function')await loadBackups();
    }
  }catch(error){
    if(request!==pageNavigation.request)return;
    toast(error.message,true);
    if(state.view==='estimate'){
      state.projectId=null;state.projectData=null;renderProjectSelect();renderProject();
    }
    if(state.view==='catalog')state.currentCatalogItem=null;
    if(state.view==='light-prices')lightPriceState.selected=null;
    id=null;
  }finally{
    pageNavigation.applying--;
    if(request===pageNavigation.request && state.user){
      const selected=state.view==='estimate'?state.projectId:state.view==='catalog'?state.currentCatalogItem?.id:state.view==='light-prices'?lightPriceState.selected:null;
      history.replaceState(null,'',pageAddress(state.view,selected));
      updateEstimateLink();
    }
  }
}
window.addEventListener('hashchange',()=>{restorePage().catch(error=>toast(error.message,true));});
