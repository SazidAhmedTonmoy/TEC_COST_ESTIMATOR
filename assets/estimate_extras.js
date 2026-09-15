function updateEstimateExtras(data){
  const project=data.project||{},plan=data.crew_plan||{};
  $('#project-hours-per-day').value=project.hours_per_day||8;$('#project-crew-size').value=project.crew_size||2;
  $('#crew-hours-per-day').textContent=fmtNumber(plan.crew_hours_per_day||16);
  $('#crew-working-days').textContent=fmtNumber(plan.working_days||0)+' days';
  let days=$('#metric-person-days');if(!days){days=document.createElement('small');days.id='metric-person-days';$('#metric-hours').after(days);}
  days.textContent=`${fmtNumber(plan.person_days||0)} person-days · ${fmtNumber(plan.working_days||0)} crew working days`;
  $('#floating-estimate-total').textContent=`Quoted total · ${fmtMoney(data.totals?.quoted||0,project.currency)}\n${fmtNumber(data.totals?.hours||0)} hrs · ${fmtNumber(plan.working_days||0)} crew days`; 
  refreshFloatingTotal();
}
function refreshFloatingTotal(){
  const target=$('#metric-quoted');$('#floating-estimate-total').classList.toggle('hidden',state.view!=='estimate'||!state.projectId||target.getBoundingClientRect().bottom>=0);
}
document.addEventListener('DOMContentLoaded',()=>{
  document.addEventListener('click',event=>{const button=event.target.closest('[data-password-target]');if(!button)return;const input=document.getElementById(button.dataset.passwordTarget),show=input.type==='password';input.type=show?'text':'password';button.textContent=show?'Hide':'Show';button.setAttribute('aria-pressed',String(show));button.setAttribute('aria-label',show?'Hide password':'Show password');});
  document.addEventListener('submit',event=>{event.target.querySelectorAll('[data-password-target]').forEach(button=>{document.getElementById(button.dataset.passwordTarget).type='password';button.textContent='Show';button.setAttribute('aria-pressed','false');button.setAttribute('aria-label','Show password');});},true);
  window.addEventListener('scroll',refreshFloatingTotal,{passive:true});window.addEventListener('resize',refreshFloatingTotal);
  new MutationObserver(refreshFloatingTotal).observe($('#estimate-view'),{attributes:true,attributeFilter:['class']});
  $('#floating-estimate-total').addEventListener('click',()=>$('#metric-quoted').scrollIntoView({behavior:'smooth',block:'center'}));
  $('#expand-all-items').addEventListener('click',()=>{estimateViewState.bulkCollapsed=false;for(const line of state.projectData?.lines||[]){estimateViewState.collapsed.delete(scopeKey(line.category_snapshot||'Other'));}renderGroupedEstimate(state.projectData?.lines||[]);});
  $('#collapse-all-items').addEventListener('click',()=>{estimateViewState.bulkCollapsed=true;for(const line of state.projectData?.lines||[])estimateViewState.collapsed.add(scopeKey(line.category_snapshot||'Other'));renderGroupedEstimate(state.projectData?.lines||[]);});
});
