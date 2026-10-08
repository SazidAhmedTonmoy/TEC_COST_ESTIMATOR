/* v2.3 project workspace. All totals use the same visible projects as the board. */
function projectOutcome(project) {
  return project.award_status==='won'?'<span class="project-outcome is-won">&#10003; Won</span>':project.award_status==='lost'?'<span class="project-outcome is-lost">&#10007; Lost</span>':'';
}
function syncProjectOutcome(editable=true) {
  const value=$('#brief-award-status').value;
  $$('[data-award-status]').forEach(button=>{
    button.disabled=!editable;
    button.setAttribute('aria-pressed',String(Boolean(value)&&button.dataset.awardStatus===value));
  });
  $('#brief-award-label').textContent=value==='won'?'Project won':value==='lost'?'Project not won':'Not recorded';
}
function closeProjectPicker() {
  $('#project-picker-menu').classList.add('hidden');
  $('#project-picker-button').setAttribute('aria-expanded','false');
}
function renderProjectPicker() {
  const active=state.projects.find(p=>p.id===state.projectId);
  $('#project-picker-label').textContent=active?.name||'Choose a project';
  $('#project-picker-button').disabled=!state.projects.some(p=>p.can_view);
  const term=$('#project-picker-search').value.trim().toLowerCase();
  const projects=state.projects.filter(p=>p.can_view&&`${p.name} ${builderText(p)}`.toLowerCase().includes(term))
    .sort((a,b)=>(b.updated_at||'').localeCompare(a.updated_at||'')||b.id-a.id);
  $('#project-picker-options').innerHTML=projects.length?projects.map(p=>`<button type="button" class="project-picker-option" role="option" aria-selected="${p.id===state.projectId}" data-project-pick="${p.id}"><strong>${escapeHtml(p.name)}</strong><small>${escapeHtml(builderText(p, 'No builder assigned'))} &middot; ${escapeHtml(statusNames[p.status]||p.status)}${p.can_edit?'':' &middot; Read-only'}</small></button>`).join(''):'<p class="helper-text">No matching projects.</p>';
}
function monthMoney(projects,key) {
  const values=new Map();
  projects.filter(p=>p.status!=='closed').forEach(p=>values.set(p.currency,(values.get(p.currency)||0)+Number(p.totals?.[key]||0)));
  return values.size?[...values].map(([currency,value])=>`${escapeHtml(currency)} ${fmtMoney(value,currency)}`).join('<br>'):'&mdash;';
}
function renderCalendarSummary(projects) {
  const month=workspaceState.month.toLocaleDateString('en-AU',{month:'long',year:'numeric'});
  const prefix=localDateKey(workspaceState.month).slice(0,7);
  const created=state.projects.filter(p=>(p.created_at||'').slice(0,7)===prefix).length;
  const won=projects.filter(p=>p.award_status==='won'),lost=projects.filter(p=>p.award_status==='lost');
  const hours=projects.filter(p=>p.status!=='closed').reduce((sum,p)=>sum+Number(p.totals?.hours||0),0);
  const items=projects.reduce((sum,p)=>sum+Number(p.line_count||0),0);
  const metrics=[
    ['Projects due this month',projects.length,`${created} projects created this month (across all deadlines)`],
    ['Total estimate / quoted value',monthMoney(projects,'quoted'),'Current saved estimate values; excluding GST'],
    ['Total material cost',monthMoney(projects,'material'),'Includes project material markup; excludes overhead and GST'],
    ['Labour allowance',`${fmtNumber(hours,2)} hrs`,`${items} estimate items across this month\'s projects`],
    ['Total labour price',monthMoney(projects,'labor'),'Hours at project rate plus fixed labour allowances; excludes overhead and GST'],
  ];
  $('#calendar-summary').innerHTML=`<div class="calendar-metric-grid">${metrics.map(([label,value,note])=>`<article class="calendar-metric" title="${escapeHtml(note)}"><span>${label}</span><strong>${value}</strong></article>`).join('')}</div><div class="calendar-status-summary">${Object.entries(statusNames).map(([key,label])=>`<span>${label} <b>${projects.filter(p=>p.status===key).length}</b></span>`).join('')}<span class="outcome-won">&#10003; Won <b>${won.length}</b></span><span class="outcome-lost">&#10007; Lost <b>${lost.length}</b></span><span>Result not recorded <b>${projects.length-won.length-lost.length}</b></span></div><p class="helper-text">Won estimate value: <strong>${monthMoney(won,'quoted')}</strong> &middot; Lost estimate value: <strong>${monthMoney(lost,'quoted')}</strong></p>`;
  $('#calendar-agenda').innerHTML=`<h3>Project details &mdash; ${escapeHtml(month)}</h3>`+(projects.length?`<div class="table-scroll"><table class="mini-table calendar-project-table"><thead><tr><th>Deadline</th><th>Project / builders</th><th>Team / estimator</th><th>Progress</th><th>Result</th><th>Items</th><th>Labour hrs</th><th>Material cost</th><th>Labour price</th><th>Quoted estimate</th></tr></thead><tbody>${projects.map(p=>`<tr><td>${dateLabel(p.submission_deadline)}</td><td><button type="button" class="text-button" data-project-brief="${p.id}">${escapeHtml(p.name)}</button><small>${escapeHtml(builderText(p, 'No builder assigned'))}</small></td><td>${escapeHtml(teamNames(p))}<small>${escapeHtml(p.owner_name||p.created_by_name||'Not recorded')}</small></td><td>${projectStatus(p)}</td><td>${projectOutcome(p)||'<span class="helper-text">Not recorded</span>'}</td><td>${p.line_count||0}</td><td>${fmtNumber(p.totals?.hours||0,2)}</td><td>${escapeHtml(p.currency)} ${fmtMoney(p.totals?.material||0,p.currency)}</td><td>${escapeHtml(p.currency)} ${fmtMoney(p.totals?.labor||0,p.currency)}</td><td><strong>${escapeHtml(p.currency)} ${fmtMoney(p.totals?.quoted||0,p.currency)}</strong></td></tr>`).join('')}</tbody><tfoot><tr><th colspan="7">Monthly totals (ex GST; Closed excluded)</th><td>${monthMoney(projects,'material')}</td><td>${monthMoney(projects,'labor')}</td><td>${monthMoney(projects,'quoted')}</td></tr></tfoot></table></div>`:'<p class="helper-text">No project deadlines this month.</p>');
}
async function deleteUserAccount() {
  const user=workspaceState.users.find(u=>u.id===workspaceState.userId);
  if(!user||user.id===state.user.id)return;
  const answer=prompt(`Permanently delete ${user.name}'s login?\n\nTheir projects, estimates, notes and history will stay. Owned projects will transfer to your account, with team access preserved. All their sessions will be revoked.\n\nType the exact username to confirm: ${user.username}`);
  if(answer===null)return;
  if(answer!==user.username){toast('Username did not match. Nothing was deleted.',true);return;}
  const button=$('#delete-user-button');button.disabled=true;
  try {
    const result=await api(`/api/users/${user.id}`,{method:'DELETE',body:{confirm_username:answer}});
    $('#user-dialog').close();await loadUsers();await loadDashboard(false);
    toast(`Account deleted. ${result.transferred_projects} owned project(s) transferred; history retained.`);
  } finally {button.disabled=false;}
}
document.addEventListener('DOMContentLoaded',()=>{
  $('#project-picker-button').addEventListener('click',()=>{
    const menu=$('#project-picker-menu');const opening=menu.classList.contains('hidden');
    if(!opening){closeProjectPicker();return;}
    $('#project-picker-search').value='';renderProjectPicker();
    menu.classList.remove('hidden');$('#project-picker-button').setAttribute('aria-expanded','true');
    $('#project-picker-options').scrollTop=0;$('#project-picker-search').focus({preventScroll:true});
  });
  $('#project-picker-search').addEventListener('input',()=>{renderProjectPicker();$('#project-picker-options').scrollTop=0;});
  $('#project-picker-options').addEventListener('click',async event=>{
    const button=event.target.closest('[data-project-pick]');if(!button)return;
    closeProjectPicker();$('#project-picker-button').disabled=true;
    try{await loadProject(Number(button.dataset.projectPick));}catch(error){toast(error.message,true);}
    finally{renderProjectPicker();$('#project-picker-button').focus({preventScroll:true});}
  });
  $('#project-picker-wrap').addEventListener('keydown',event=>{
    if(event.key==='Escape'){closeProjectPicker();$('#project-picker-button').focus();return;}
    if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key)||$('#project-picker-menu').classList.contains('hidden'))return;
    const options=$$('.project-picker-option'),current=options.indexOf(document.activeElement);if(!options.length)return;
    if(event.target===$('#project-picker-search')&&['Home','End'].includes(event.key))return;
    event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?options.length-1:event.key==='ArrowDown'?Math.min(current+1,options.length-1):Math.max(current-1,0);
    options[next].focus();
  });
  document.addEventListener('click',event=>{
    if(!event.target.closest('#project-picker-wrap'))closeProjectPicker();
    const result=event.target.closest('[data-award-status]');
    if(result&&!result.disabled){const field=$('#brief-award-status');field.value=field.value===result.dataset.awardStatus?'':result.dataset.awardStatus;syncProjectOutcome(true);}
  });
  $('#delete-user-button').addEventListener('click',()=>deleteUserAccount().catch(error=>toast(error.message,true)));
});
