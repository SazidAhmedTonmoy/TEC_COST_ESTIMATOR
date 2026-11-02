/* v3.7.18 Estimator usability. No duplicate project state or database writes. */
function setEstimateSaveState(status){
  const el=document.getElementById('estimate-save-state');
  if(!el)return;
  const states={idle:'Choose a project to begin',saved:'Saved',saving:'Saving...',dirty:'Unsaved changes',error:'Save failed - check the form'};
  const mode=Object.hasOwn(states,status)?status:'idle';
  el.dataset.status=mode;
  el.querySelector('.save-text').textContent=states[mode];
  el.title=mode==='error'?'Some changes were not saved. Check the form below, resolve the error and save again.':states[mode];
}

(() => {
  const steps=[
    {title:'Project details',desc:'Create or select a project, confirm its scope and builders, and check the submission date.',action:'Open project setup'},
    {title:'Catalog items',desc:'Search reusable electrical assemblies, preview their components, and add selected items. Use Quick add when rates are already known.',action:'Find catalog items'},
    {title:'Quantities and areas',desc:'Edit quantities in your estimate. Use Breakdown to allocate items by Area / Floor / Space; fix unallocated quantities before saving.',action:'Edit quantities'},
    {title:'Cost review',desc:'Review hours, material and labour, the Included quoted total and separately excluded Optional costs.',action:'Review estimate totals'},
    {title:'Save, revisions and export',desc:'Verify the Saved indicator, save a named revision before important changes, then export your quotation to Excel.',action:'Open revisions'}
  ];
  let stepIndex=0;
  const dialog=document.getElementById('estimate-setup-guide');
  if(!dialog)return;
  const body=document.getElementById('estimate-guide-body');
  const progress=document.getElementById('estimate-guide-progress');
  const back=document.getElementById('estimate-guide-back');
  const next=document.getElementById('estimate-guide-next');
  const action=document.getElementById('estimate-guide-action');
  const render=()=>{
    const current=steps[stepIndex];
    progress.innerHTML=steps.map((s,i)=>`<span class="guide-step-dot ${i===stepIndex?'active':''} ${i<stepIndex?'complete':''}" aria-label="Step ${i+1}: ${escapeHtml(s.title)}" ${i===stepIndex?'aria-current="step"':''}></span>`).join('');
    body.innerHTML=`<p class="eyebrow">Step ${stepIndex+1} of ${steps.length}</p><h3>${escapeHtml(current.title)}</h3><p>${escapeHtml(current.desc)}</p>${!state.projectId&&stepIndex>0?'<p class="guide-notice">Create or select a project before adding or editing estimate items.</p>':''}`;
    back.disabled=stepIndex===0;
    next.textContent=stepIndex===steps.length-1?'Finish':'Next';
    action.textContent=current.action;
  };
  document.getElementById('estimate-setup-guide-open')?.addEventListener('click',()=>{stepIndex=0;render();dialog.showModal()});
  dialog.querySelectorAll('[data-guide-close]').forEach(button=>button.addEventListener('click',()=>dialog.close()));
  back.addEventListener('click',()=>{stepIndex=Math.max(0,stepIndex-1);render()});
  next.addEventListener('click',()=>{if(stepIndex===steps.length-1){dialog.close();return}stepIndex++;render()});
  action.addEventListener('click',()=>{
    const current=stepIndex;
    dialog.close();
    if(current===0){
      if(state.projectData){setView('estimate');document.querySelector('#project-name')?.focus();}
      else if(typeof openProjectForm==='function')openProjectForm();
      return;
    }
    if(!state.projectId){
      if(typeof toast==='function')toast('Create or choose an estimate project first',true);
      if(typeof openProjectForm==='function')openProjectForm();
      return;
    }
    setView('estimate');
    const targets=['','#smart-search-input','#estimate-lines','#estimate-cost-separation','#metric-quoted'];
    if(current===4){
      if(typeof openRevisions==='function')openRevisions(state.projectId).catch(error=>toast(error.message,true));
      return;
    }
    const el=document.querySelector(targets[current]);
    if(el){el.scrollIntoView({behavior:'smooth',block:'center'});if(current===1)el.focus({preventScroll:true});}
  });
})();
