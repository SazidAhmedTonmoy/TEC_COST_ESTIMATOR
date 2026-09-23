function updateEstimateExtras(data){
  const project=data.project||{};
  $('#project-hours-per-day').value=project.hours_per_day||8;$('#project-crew-size').value=project.crew_size||2;
  renderEstimateTimeSummary(data,project.hours_per_day||8,project.crew_size||2);
}
function renderEstimateTimeSummary(data,hoursPerDay,crewSize){
  const project=data.project||{},hours=Number(data.totals?.hours||0);
  const valid=Number.isFinite(hoursPerDay)&&hoursPerDay>0&&Number.isFinite(crewSize)&&crewSize>0;
  const personDays=valid?fmtNumber(hours/hoursPerDay):'—';
  const crewDays=valid?fmtNumber(hours/(hoursPerDay*crewSize)):'—';
  let days=$('#metric-person-days');if(!days){days=document.createElement('small');days.id='metric-person-days';$('#metric-hours').after(days);}
  days.textContent=`${personDays} person-days · ${crewDays} crew working days`;
  const total=$('#floating-estimate-total');
  total.textContent='';
  const name=document.createElement('span');name.className='floating-project-name';name.textContent=project.name||'';total.append(name);
  total.append(document.createTextNode(`Quoted total · ${fmtMoney(data.totals?.quoted||0,project.currency)}\n${fmtNumber(hours)} hrs · ${crewDays} crew days`));
  refreshFloatingTotal();
}
function previewEstimateTimeSummary(){
  if(!state.projectData)return;
  renderEstimateTimeSummary(state.projectData,Number($('#project-hours-per-day').value),Number($('#project-crew-size').value));
}
function refreshFloatingTotal(){
  const target=$('#metric-quoted');$('#floating-estimate-total').classList.toggle('hidden',state.view!=='estimate'||!state.projectId||target.getBoundingClientRect().bottom>=0);
}
document.addEventListener('DOMContentLoaded',()=>{
  ['#project-hours-per-day','#project-crew-size'].forEach(selector=>$(selector).addEventListener('input',previewEstimateTimeSummary));
  document.addEventListener('click',event=>{const button=event.target.closest('[data-password-target]');if(!button)return;const input=document.getElementById(button.dataset.passwordTarget),show=input.type==='password';input.type=show?'text':'password';button.textContent=show?'Hide':'Show';button.setAttribute('aria-pressed',String(show));button.setAttribute('aria-label',show?'Hide password':'Show password');});
  document.addEventListener('submit',event=>{event.target.querySelectorAll('[data-password-target]').forEach(button=>{document.getElementById(button.dataset.passwordTarget).type='password';button.textContent='Show';button.setAttribute('aria-pressed','false');button.setAttribute('aria-label','Show password');});},true);
  window.addEventListener('scroll',refreshFloatingTotal,{passive:true});window.addEventListener('resize',refreshFloatingTotal);
  new MutationObserver(refreshFloatingTotal).observe($('#estimate-view'),{attributes:true,attributeFilter:['class']});
  $('#floating-estimate-total').addEventListener('click',()=>$('#metric-quoted').scrollIntoView({behavior:'smooth',block:'center'}));
  $('#toggle-all-categories').addEventListener('click',()=>{
    const lines=state.projectData?.lines||[];
    const allCollapsed=lines.length>0&&lines.every(line=>estimateViewState.collapsed.has(scopeKey(line.category_snapshot||'Other')));
    estimateViewState.bulkCollapsed=!allCollapsed;
    for(const line of lines){const key=scopeKey(line.category_snapshot||'Other');if(allCollapsed)estimateViewState.collapsed.delete(key);else estimateViewState.collapsed.add(key);}
    renderGroupedEstimate(lines);
  });
});
function syncCategoryToggle(){
  const button=$('#toggle-all-categories'),lines=state.projectData?.lines||[];
  button.classList.toggle('hidden',state.view!=='estimate'||!state.projectId);
  button.disabled=!lines.length;
  const collapsed=lines.length>0&&lines.every(line=>estimateViewState.collapsed.has(scopeKey(line.category_snapshot||'Other')));
  const label=collapsed?'Expand all categories':'Collapse all categories';
  button.textContent=collapsed?'+':'−';
  button.title=label;button.setAttribute('aria-label',label);button.setAttribute('aria-expanded',String(!collapsed));
}
