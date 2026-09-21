/* Project board, account administration and deadline calendar. */
const workspaceState = { filter: 'all', reminderRows: [], boardView: 'cards', users: [], teams: [], notesProjectId: null, notesRequest: 0, noteCounts: {}, noteStatusRequests: {}, noteReadPending: {}, notesSyncBusy: false, teamId: null, briefId: null, userId: null, month: new Date(new Date().getFullYear(), new Date().getMonth(), 1), briefRequest: 0 };
const statusNames = { draft: 'Not started', in_progress: 'In progress', submitted: 'Submitted', completed: 'Completed' };

function localDateKey(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
function dateLabel(value) {
  if (!value) return 'No deadline';
  const [y,m,d] = value.split('-').map(Number);
  return new Date(y,m-1,d).toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'});
}
function isOpenProject(project) { return !['submitted','completed'].includes(project.status); }
function isOverdue(project) { return isOpenProject(project) && project.submission_deadline && project.submission_deadline < localDateKey(); }
function projectStatus(project) {
  return `<span class="project-status status-${escapeHtml(project.status)}">${escapeHtml(statusNames[project.status] || project.status)}</span>`;
}
function setAccount(user, token) {
  const changedUser=state.user?.id!==user.id;
  state.user = user; state.csrfToken = token;
  if(changedUser){workspaceState.reminderRows=[];workspaceState.boardView='cards';
    try{const saved=localStorage.getItem('conest-project-view-'+user.id);if(['cards','list','compact'].includes(saved))workspaceState.boardView=saved;}catch(_){}
  }
  $$('.user-only').forEach(el=>el.classList.toggle('hidden',user.role==='admin'));
  if(user.role==='admin' && workspaceState.filter==='team') workspaceState.filter='all';
  $('#account-name').textContent = user.name;
  if(typeof renderAccountAvatar==='function')renderAccountAvatar(user);
  $('#account-role').textContent = `${user.job_title || (user.role === 'admin' ? 'Administrator' : 'Estimator')} · ${user.role === 'admin' ? 'Admin' : 'User'}`;
  $('.app-shell').classList.remove('hidden');
  $('#login-screen').classList.add('hidden');
  $$('.admin-only').forEach(element => element.classList.toggle('hidden',user.role !== 'admin' || Boolean(user.must_change_password)));
}
function showLogin() {
  if(typeof resetHelpChat==='function')resetHelpChat();
  if(typeof clearProfilePhoto==='function')clearProfilePhoto();
  if(typeof resetUploadHistory==='function')resetUploadHistory();
  state.projectLoadRequest=(state.projectLoadRequest||0)+1;state.catalogDetailRequest=(state.catalogDetailRequest||0)+1;
  state.user = null; state.csrfToken = ''; state.projectId = null; state.projectData = null;
  state.projects = []; state.dashboard = null; state.appSettings = null; state.catalogCache.clear();
  workspaceState.users = []; workspaceState.teams = []; workspaceState.noteCounts={}; workspaceState.noteStatusRequests={}; workspaceState.noteReadPending={}; workspaceState.notesProjectId=null; workspaceState.notesRequest++; workspaceState.filter = 'all'; workspaceState.briefId = null; workspaceState.briefRequest++;
  $$('dialog[open]').forEach(dialog => dialog.close());
  $('.app-shell').classList.add('hidden');
  $('#floating-search-button').classList.add('hidden');
  $('#light-price-floating-search').classList.add('hidden');
  if(typeof resetLightPrices==='function')resetLightPrices();
  $('#catalog-hover-preview').classList.add('hidden');
  $('#login-screen').classList.remove('hidden');
  $('#login-password').value = ''; $('#gemini-api-key').value = '';
}
async function enterWorkspace(result) {
  setAccount(result.user, result.csrf_token);
  if (state.user.must_change_password) { setView('profile',false); return; }
  await loadSettings(false);
  await loadDashboard();
  if(typeof restorePage==='function')await restorePage(); else setView('home',false);
}
async function bootWorkspace() {
  try { await enterWorkspace(await api('/api/auth/session')); }
  catch(error) { showLogin(); if (error.status !== 401) $('#login-error').textContent = error.message; }
}
async function submitWithButton(event, action) {
  event.preventDefault();
  const button = event.submitter || $('button[type="submit"]',event.target);
  if (button?.disabled) return;
  if (button) button.disabled = true;
  try { await action(); } catch(error) { toast(error.message,true); }
  finally { if (button) button.disabled = false; }
}

function individualNames(project) { return (project.individual_users||[]).map(u=>u.name+(u.is_active?'':' (inactive)')).join(', '); }
function teamNames(project) { return (project.teams || []).map(t=>t.name).join(', ') || 'No team assigned'; }
function inReviewQueue(project) { return state.user?.role === 'admin' && project.needs_admin_review; }
function renderHome() {
  if (!state.user) return;
  const projects = state.projects;
  $('#welcome-name').textContent = `Welcome, ${state.user.name}`;
  $('#welcome-date').textContent = new Date().toLocaleDateString('en-AU',{weekday:'long',day:'numeric',month:'long',year:'numeric'});
  const metrics = Object.entries(statusNames).map(([key,label]) => [label,projects.filter(p=>p.status===key).length,key]);
  $('#home-metrics').innerHTML = metrics.map(([label,value,filter]) => `<button class="metric home-metric ${filter==='new'?'accent':''}" type="button" data-filter="${filter}"><span>${label}</span><strong>${value}</strong><small>${filter==='new'?'Open to review new team projects':filter==='draft'?'Ready to begin':filter==='in_progress'?'Estimates being prepared':filter==='submitted'?'Sent for review or approval':'Finished project archive'}</small></button>`).join('');
  $('#home-metrics').classList.remove('five-metrics');
  renderProjectBoard();
  if(typeof loadReminders==='function')loadReminders().catch(()=>{});
  renderSchedule();
  const values = new Map();
  projects.filter(p=>p.status!=='completed').forEach(p=>values.set(p.currency,(values.get(p.currency)||0)+Number(p.totals?.quoted||0)));
  $('#portfolio-value').textContent = values.size ? 'Active estimate value: '+[...values].map(([currency,value])=>`${currency} ${fmtMoney(value,currency)}`).join(' · ') : '';
}
function renderSchedule(){
  const reminders=new Map(workspaceState.reminderRows.map(row=>[row.project_id,row]));
  const due=state.projects.filter(p=>p.submission_deadline&&isOpenProject(p)).sort((a,b)=>a.submission_deadline.localeCompare(b.submission_deadline));
  const render=p=>{
    const reminder=reminders.get(p.id),days=reminder?.days;
    const timing=days===undefined?(isOverdue(p)?'Overdue':''):days<0?`${-days} day${days===-1?'':'s'} overdue`:days===0?'Due today':`Due in ${days} day${days===1?'':'s'}`;
    return `<article class="schedule-item ${isOverdue(p)?'overdue':''}"><div class="schedule-date">${dateLabel(p.submission_deadline)}${reminder&&!reminder.read?'<span class="schedule-new">New</span>':''}</div><button type="button" class="text-button" data-project-brief="${p.id}">${escapeHtml(p.name)}</button>${timing?`<small class="${isOverdue(p)?'overdue-text':''}">${timing}</small>`:''}${reminder&&!reminder.read?`<button type="button" class="schedule-seen text-button" data-read-reminder="${escapeHtml(reminder.key)}">Mark seen</button>`:''}</article>`;
  };
  $('#deadline-agenda').innerHTML=due.length?due.slice(0,5).map(render).join('')+(due.length>5?`<details class="schedule-more"><summary>${due.length-5} more deadlines</summary>${due.slice(5).map(render).join('')}</details>`:''):'<p class="board-empty">You’re up to date. No pending deadlines.</p>';
}
function renderProjectBoard() {
  const term = $('#project-search').value.trim().toLowerCase();
  const filter = ['all','team',...Object.keys(statusNames)].includes(workspaceState.filter)?workspaceState.filter:'all';
  workspaceState.filter=filter;
  const board=$('#project-board');board.dataset.view=workspaceState.boardView;$('#project-view-style').value=workspaceState.boardView;
  $$('#project-tabs button').forEach(b=>{b.classList.toggle('active',b.dataset.filter===filter);b.setAttribute('aria-pressed',String(b.dataset.filter===filter));});
  const projects = state.projects.filter(p=>{
    if (!(p.name+' '+builderText(p)+' '+(p.created_by_name||'')+' '+teamNames(p)+' '+(p.contributors||[]).map(c=>c.name).join(' ')).toLowerCase().includes(term)) return false;
    if (filter==='team') return p.is_assigned;
    if (statusNames[filter]) return p.status===filter;
    return true;
  });
  board.innerHTML = projects.length ? projects.map(p=>`<article class="project-card">
    <div class="project-card-heading"><div>${builderText(p)?`<p>${escapeHtml(builderText(p))}</p>`:''}<h3><button type="button" data-project-brief="${p.id}">${escapeHtml(p.name)}</button></h3></div><div class="project-badges">${inReviewQueue(p)?'<span class="project-status status-new">Newly added</span>':''}${projectStatus(p)}</div></div>
    <div class="project-facts"><span class="${isOverdue(p)?'overdue-text':''}">${isOverdue(p)?'Overdue · ':''}${dateLabel(p.submission_deadline)}</span>${projectOutcome(p)}${p.can_edit?'':'<span class="project-readonly-badge">Read-only</span>'}</div>
    <div class="project-card-footer"><span>${p.line_count||0} items <strong>${escapeHtml(p.currency)} ${fmtMoney(p.totals?.quoted,p.currency)}</strong></span><a class="button primary small" href="#/estimate/${p.id}" data-open-project="${p.id}">Open Estimate</a></div>
    <details class="project-more"><summary>Project details</summary>${p.scope_of_work?`<p class="project-scope-excerpt">${escapeHtml(p.scope_of_work)}</p>`:''}<p class="project-team"><strong>Team:</strong> ${escapeHtml(teamNames(p))}<br><strong>Added by:</strong> ${escapeHtml(p.created_by_name||'Creator not recorded')}${p.completed_by_name?`<br>Completed by ${escapeHtml(p.completed_by_name)}`:p.updated_by_name?`<br>Last edited by ${escapeHtml(p.updated_by_name)}`:''}</p><div class="project-more-actions"><button type="button" class="button secondary small" data-project-brief="${p.id}">${p.can_edit?'Manage Project':'View Project'}</button><button class="button secondary small" type="button" data-copy-project="${p.id}">Copy Project</button></div></details>
  </article>`).join('') : '<div class="board-empty"><h3>No matching projects</h3><p>Try a different search or status. Create a project from Build Estimate.</p></div>';

}
function renderGroupedEstimate(lines) {
  let category = null;
  $('#estimate-lines').innerHTML = lines.map(line => {
    const current = line.category_snapshot || 'Other';
    const header = category !== current ? `<tr class="estimate-category-group"><th colspan="10" scope="colgroup">${escapeHtml(current)}</th></tr>` : '';
    category = current;
    return header + renderEstimateLine(line);
  }).join('');
}
function renderEstimateBrief(project) {
  $('#estimate-project-brief').innerHTML = project.id ? `<div><h2>${escapeHtml(project.name)}</h2><p>${dateLabel(project.submission_deadline)} · ${escapeHtml(teamNames(project))}${project.can_edit?'':' · Read-only &middot; no edit access assigned'}</p></div><div>${projectStatus(project)}<button class="button secondary" type="button" data-project-brief="${project.id}">${project.can_edit?'Manage project & activity':'View project & activity'}</button><button type="button" data-project-notes="${project.id}" class="button secondary note-button" aria-label="Add Note${workspaceState.noteCounts[project.id]?' — unread notes':''}">${project.can_edit?'Add Note':'View notes'}<span class="note-unread-dot ${workspaceState.noteCounts[project.id]?'':'hidden'}" aria-hidden="true"></span></button><button class="button secondary" type="button" data-revisions="${project.id}">Revisions</button><button class="button secondary" type="button" data-copy-project="${project.id}">Copy project</button></div>` : '';
}
async function reviewOpenedProject(project) {
  if (state.user.role==='admin' && project.needs_admin_review) {
    const result=await api(`/api/projects/${project.id}/review`,{method:'POST',body:{}});
    Object.assign(project,result.project);
    const board=state.projects.find(p=>p.id===project.id);
    if (board) Object.assign(board,result.project);
    renderHome();
  }
  return project;
}
async function openProject(id) {
  if(await loadProject(Number(id))===false)return;
  setView('estimate',false);
}
async function loadTeams() {
  const result=await api('/api/teams'); workspaceState.teams=result.teams; return result.teams;
}
async function loadUsers(render=true) {
  const [result]=await Promise.all([api('/api/users'),loadTeams()]);
  workspaceState.users=result.users;
  if(render) {
    $('#user-rows').innerHTML=result.users.map(u=>`<tr><td><strong>${escapeHtml(u.name)}</strong><small class="line-unit">${escapeHtml(u.job_title)}</small></td><td>${escapeHtml(u.username)}</td><td>${u.role==='admin'?'Admin':'User'}</td><td>${escapeHtml(u.role==='admin'?'All projects':u.team_name||'No team')}</td><td>${u.is_active?'Active':'Inactive'}${u.must_change_password?' · Setup pending':''}</td><td><button class="button secondary small" type="button" data-edit-user="${u.id}">Edit user</button></td></tr>`).join('');
    renderTeams();
  }
  return result.users;
}
function renderTeams() {
  $('#team-cards').innerHTML=workspaceState.teams.map(t=>`<article class="team-card"><div><h3>${escapeHtml(t.name)}</h3><span>${t.members.filter(m=>m.is_active).length} active members</span></div><p>${t.members.length?t.members.map(m=>escapeHtml(m.name)+(m.is_active?'':' (inactive)')).join(', '):'No members yet'}</p><button class="button secondary small" type="button" data-edit-team="${t.id}">Edit team & members</button></article>`).join('');
}
async function openProjectBrief(id) {
  const request=++workspaceState.briefRequest;
  const result=await api(`/api/projects/${Number(id)}`);
  const p=await reviewOpenedProject(result.project);
  const [access,history]=await Promise.all([p.can_manage?api(`/api/projects/${p.id}/access-options`):Promise.resolve({teams:[],users:[]}),api(`/api/projects/${p.id}/activity`)]);
  if(request!==workspaceState.briefRequest) return;
  workspaceState.briefId=p.id; workspaceState.briefProject=p;
  $('#brief-open-estimate').href=`#/estimate/${p.id}`;
  $('#brief-title').textContent=p.name; $('#brief-client').textContent=builderText(p, 'Manage project');
  $('#brief-summary').innerHTML=`<div class="brief-meta">${projectStatus(p)}<span>Added by: ${escapeHtml(p.created_by_name||'Creator not recorded')}</span><span>Team: ${escapeHtml(teamNames(p))}</span>${individualNames(p)?`<span>Individual editors: ${escapeHtml(individualNames(p))}</span>`:''}</div><p class="helper-text">Contributors: ${p.contributors?.length?p.contributors.map(u=>escapeHtml(u.name)).join(', '):'No recorded work yet'}</p>`;
  $('#brief-scope').value=p.scope_of_work||''; $('#brief-deadline').value=p.submission_deadline||''; $('#brief-status').value=p.status;
  renderBuilderEditor('brief-builders', projectBuilders(p), p.can_manage);
  $('#brief-scope').disabled=!p.can_manage; $('#brief-deadline').disabled=!p.can_manage;
  $('#brief-award-status').value=p.award_status||'';syncProjectOutcome(p.can_edit);
  $('#brief-status').disabled=!p.can_edit; $('#brief-save').disabled=!p.can_edit;
  $('#brief-save').classList.toggle('hidden',!p.can_edit);
  $('#brief-delete').classList.toggle('hidden',!p.can_delete);
  $('#project-access-fieldset').classList.toggle('hidden',!p.can_manage);
  $('#assignment-options').innerHTML=access.teams.map(t=>`<label class="checkbox-label"><input type="checkbox" value="${t.id}" ${(p.teams||[]).some(a=>a.id===t.id)?'checked':''}><span>${escapeHtml(t.name)}<small>${t.active_members} active members</small></span></label>`).join('')||'<p class="helper-text">No teams available.</p>';
  $('#assignment-user-search').value='';
  $('#individual-assignment-options').innerHTML=access.users.map(u=>`<label class="checkbox-label" data-access-user data-search="${escapeHtml((u.name+' '+u.username+' '+(u.team_name||'')).toLowerCase())}"><input type="checkbox" value="${u.id}" ${(p.individual_users||[]).some(a=>a.id===u.id)?'checked':''}><span>${escapeHtml(u.name)}${u.is_active?'':' (inactive)'}<small>${escapeHtml(u.username)} &middot; ${escapeHtml(u.team_name||'No team')}</small></span></label>`).join('')||'<p class="helper-text">No users available for individual assignment.</p>';
  $('#assignment-user-empty').classList.add('hidden');
  $('#project-contributors').innerHTML=history.contributors?.length?'<h4>Project contributors</h4>'+history.contributors.map(c=>`<article class="contributor-card"><strong>${escapeHtml(c.name)}</strong><span>${escapeHtml(c.teams || (c.admin_contribution?'Administrator':'Historical team not recorded'))}</span><small>${c.actions} recorded actions · Last contribution ${new Date(c.last_activity).toLocaleString('en-AU')}</small></article>`).join(''):'<p class="helper-text">No contributions recorded yet.</p>';
  renderProjectActivity(history);
  if(!$('#project-brief-dialog').open) $('#project-brief-dialog').showModal();
}
function renderProjectActivity(history, append=false) {
  const old=append?(workspaceState.activityRows||[]):[];
  workspaceState.activityRows=[...new Map([...old,...history.activity].map(a=>[a.id,a])).values()].sort((a,b)=>b.id-a.id);
  workspaceState.activityNext=history.next_before_id;
  workspaceState.activityTotal=history.total_activity;
  const rows=workspaceState.activityRows;
  $('#project-activity').innerHTML=rows.length?rows.map(a=>`<article class="activity-entry"><strong>${escapeHtml(a.name||'Former user')} &middot; ${escapeHtml(a.action)}</strong><small>${escapeHtml(a.team_name_snapshot||(a.role_snapshot==='admin'?'Administrator':'Historical team not recorded'))} &middot; ${new Date(a.created_at).toLocaleString('en-AU')}</small>${a.details?`<p>${escapeHtml(a.details)}</p>`:''}</article>`).join(''):'<p class="helper-text">No activity recorded yet.</p>';
  let footer=$('#activity-pagination');
  if(!footer){footer=document.createElement('div');footer.id='activity-pagination';$('#project-activity').after(footer);}
  renderActivityPagination();
}
function renderActivityPagination() {
  const footer=$('#activity-pagination');if(!footer)return;
  footer.innerHTML=`<span>${(workspaceState.activityRows||[]).length} of ${workspaceState.activityTotal||0} recorded updates</span>${workspaceState.activityNext?'<button class="button secondary small" type="button" data-older-activity>Load older updates</button>':''}`;
}
async function loadOlderProjectActivity(button) {
  const pid=workspaceState.briefId,cursor=workspaceState.activityNext,request=workspaceState.briefRequest;
  if(!cursor||workspaceState.activityLoading)return;
  workspaceState.activityLoading=true;button.disabled=true;
  try {
    const history=await api(`/api/projects/${pid}/activity?before_id=${cursor}`);
    if(pid===workspaceState.briefId&&request===workspaceState.briefRequest)renderProjectActivity(history,true);
  } finally {workspaceState.activityLoading=false;button.disabled=false;}
}
async function refreshReadOnlyBrief() {
  const dialog=$('#project-brief-dialog'),pid=workspaceState.briefId,request=workspaceState.briefRequest;
  if(!dialog.open||workspaceState.briefProject?.can_edit||workspaceState.briefSyncBusy||workspaceState.activityLoading)return;
  workspaceState.briefSyncBusy=true;
  try {
    const [result,history]=await Promise.all([api(`/api/projects/${pid}`),api(`/api/projects/${pid}/activity`)]);
    if(!dialog.open||pid!==workspaceState.briefId||request!==workspaceState.briefRequest)return;
    const p=result.project,old=workspaceState.briefProject;
    // Permission changes need to rebuild disabled controls from server truth.
    if(p.can_edit!==old.can_edit||p.can_manage!==old.can_manage||p.can_delete!==old.can_delete){await openProjectBrief(pid);return;}
    workspaceState.briefProject=p;
    $('#brief-title').textContent=p.name;
    $('#brief-client').textContent=builderText(p, 'View project');
    renderBuilderEditor('brief-builders', projectBuilders(p), false);
    $('#brief-scope').value=p.scope_of_work||'';$('#brief-deadline').value=p.submission_deadline||'';$('#brief-status').value=p.status;
    $('#brief-award-status').value=p.award_status||'';syncProjectOutcome(false);
    $('#brief-summary').innerHTML=`<div class="brief-meta">${projectStatus(p)}<span>Added by: ${escapeHtml(p.created_by_name||'Creator not recorded')}</span><span>Team: ${escapeHtml(teamNames(p))}</span>${individualNames(p)?`<span>Individual editors: ${escapeHtml(individualNames(p))}</span>`:''}</div><p class="helper-text">Read-only &middot; latest saved project information.</p>`;
    const next=workspaceState.activityNext,oldRows=workspaceState.activityRows||[];
    // Do not skip events if more than one page arrived between refreshes.
    const newestPage=history.activity,oldTop=oldRows[0]?.id;
    const gap=oldTop&&newestPage.length===200&&newestPage[newestPage.length-1].id>oldTop;
    if(gap){renderProjectActivity(history);return;}
    const added=newestPage.some(a=>!oldRows.some(b=>a.id===b.id));
    if(added){renderProjectActivity(history,true);workspaceState.activityNext=next;renderActivityPagination();}
  } finally {workspaceState.briefSyncBusy=false;}
}
async function saveProjectWorkflow() {
  const p=workspaceState.briefProject;
  if(!p) throw new Error('Project no longer available');
  const payload={status:$('#brief-status').value,award_status:$('#brief-award-status').value,expected_revision:p.revision};
  if(p.can_manage) {payload.scope_of_work=$('#brief-scope').value;payload.builders=readBuilderEditor('brief-builders');payload.submission_deadline=$('#brief-deadline').value;}
  if(p.can_manage) {
    payload.team_ids=$$('#assignment-options input:checked').map(input=>Number(input.value));
    payload.user_ids=$$('#individual-assignment-options input:checked').map(input=>Number(input.value));
  }
  await api(`/api/projects/${p.id}/workflow`,{method:'PATCH',body:payload});
  $('#project-brief-dialog').close(); await loadDashboard();
  if(state.view==='calendar') renderCalendar(); toast('Project updated');
}
async function deleteManagedProject() {
  const p=workspaceState.briefProject;
  if(!p?.can_delete || !confirm(`Delete “${p.name}” and all its estimate lines for everyone? This cannot be undone. Saved catalog items will remain.`)) return;
  const button=$('#brief-delete'); button.disabled=true;
  try {
    await api(`/api/projects/${p.id}`,{method:'DELETE',body:{expected_revision:p.revision}});
    $('#project-brief-dialog').close();
    if(state.projectId===p.id) {state.projectId=null;state.projectData=null;}
    await loadDashboard(false); renderCalendar(); toast('Project deleted');
  } finally {button.disabled=false;}
}
function renderProfile() {
  const u=state.user; if(!u) return;
  if(!u.must_change_password) loadMyTeam().catch(error=>{ $('#my-team-details').textContent=error.message; });
  $('#profile-form').reset();
  $('#profile-contact').value=u.contact_number||'';
  if(typeof resetProfilePhoto==='function')resetProfilePhoto(u);
  $('#profile-email').value=u.email||'';$('#profile-name').value=u.name; $('#profile-username').value=u.username;
  $('#profile-title').value=u.job_title; $('#profile-role').value=u.role==='admin'?'Admin':'User';
  $('#password-setup-note').classList.toggle('hidden',!u.must_change_password);
  $('#profile-new-password').required=Boolean(u.must_change_password);
  $('#profile-current-password').required=Boolean(u.must_change_password);
  $('#profile-confirm-password').required=Boolean(u.must_change_password);
}
async function saveProfile() {
  const password=$('#profile-new-password').value;
  if (password!==$('#profile-confirm-password').value) throw new Error('The new passwords do not match');
  if(profilePhotoState.reading)throw new Error('Please wait for the photo to finish loading, then save.');
  const payload={email:$('#profile-email').value,contact_number:$('#profile-contact').value,name:$('#profile-name').value,username:$('#profile-username').value,job_title:$('#profile-title').value,password,current_password:$('#profile-current-password').value};
  if(profilePhotoState.dataUrl)payload.photo_data_url=profilePhotoState.dataUrl;
  else if(profilePhotoState.remove)payload.remove_photo=true;
  const controls=$$('input,button', $('#profile-form')), previous=controls.map(el=>el.disabled);
  profilePhotoState.busy=true;controls.forEach(el=>el.disabled=true);
  try {
    const result=await api('/api/auth/profile',{method:'PATCH',body:payload});
    const setup=state.user.must_change_password;
    setAccount(result.user,result.csrf_token);
    if (setup) await enterWorkspace(result); else { renderProfile(); await loadDashboard(); }
    toast('Profile saved');
  } finally {profilePhotoState.busy=false;controls.forEach((el,i)=>el.disabled=previous[i]);renderProfilePhoto();}
}

function openUserEditor(id=null) {
  const u=workspaceState.users.find(u=>u.id===Number(id));
  workspaceState.userId=u?.id||null;
  $('#user-form').reset();
  $('#delete-user-button').classList.toggle('hidden',!u);
  $('#delete-user-button').disabled=Boolean(u && u.id===state.user.id);
  $('#delete-user-button').title=u?.id===state.user.id?'You cannot delete your own signed-in account':'Delete login; preserve projects, notes and history';
  $('#user-dialog-title').textContent=u?'Edit user':'Add user';
  $('#user-name').value=u?.name||''; $('#user-username').value=u?.username||'';
  $('#user-email').value=u?.email||'';
  $('#user-contact').value=u?.contact_number||'';
  $('#user-title').value=u?.job_title||''; $('#user-role').value=u?.role||'user';
  $('#user-team').innerHTML='<option value="">No team</option>'+workspaceState.teams.map(t=>`<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
  $('#user-team').value=u?.team_id||''; syncUserRole();
  $('#user-active').checked=u?Boolean(u.is_active):true;
  $('#user-active').disabled=!u;
  $('#user-password').required=!u;
  $('#user-password-note').textContent=u?'Leave the password blank to keep it. Enter a temporary password to reset access; the user chooses a new one at sign-in.':'The user chooses a new password at their next sign-in.';
  $('#user-dialog').showModal();
}
async function saveUser() {
  const id=workspaceState.userId;
  const payload={email:$('#user-email').value,contact_number:$('#user-contact').value,name:$('#user-name').value,username:$('#user-username').value,job_title:$('#user-title').value,role:$('#user-role').value,team_id:$('#user-role').value==='admin'?null:Number($('#user-team').value)||null};
  if (id) payload.is_active=$('#user-active').checked;
  if ($('#user-password').value) payload.password=$('#user-password').value;
  await api(id?`/api/users/${id}`:'/api/users',{method:id?'PATCH':'POST',body:payload});
  $('#user-dialog').close();
  if (id===state.user.id) {
    try { const result=await api('/api/auth/session'); setAccount(result.user,result.csrf_token); }
    catch(error) { showLogin(); toast('Your account changed. Sign in again.'); return; }
  }
  await loadUsers(); await loadDashboard(false); toast(id?'User updated':'User created');
}

function syncUserRole() {
  const admin=$('#user-role').value==='admin';
  $('#user-team').disabled=admin;
  if(admin) $('#user-team').value='';
  $('#user-team-note').textContent=admin?'Admins can manage every project and have no team.':'Members can work on every project shared with their team. No team gives access only to their own projects.';
}
function openTeamEditor(id=null) {
  const team=workspaceState.teams.find(t=>t.id===Number(id)); workspaceState.teamId=team?.id||null;
  $('#team-form').reset(); $('#team-dialog-title').textContent=team?'Edit team':'Add team'; $('#team-name').value=team?.name||'';
  $('#team-member-options').innerHTML=workspaceState.users.filter(u=>u.role==='user').map(u=>`<label class="checkbox-label"><input type="checkbox" value="${u.id}" ${u.team_id===team?.id?'checked':''}><span>${escapeHtml(u.name)}<small>${escapeHtml(u.team_name||'No team')}${u.is_active?'':' · Inactive'}</small></span></label>`).join('')||'<p class="helper-text">Add a user first.</p>';
  $('#team-dialog').showModal();
}
async function saveTeam() {
  const id=workspaceState.teamId;
  await api(id?`/api/teams/${id}`:'/api/teams',{method:id?'PATCH':'POST',body:{name:$('#team-name').value,member_ids:$$('#team-member-options input:checked').map(i=>Number(i.value))}});
  $('#team-dialog').close(); await loadUsers(); await loadDashboard(false); toast('Team and members saved');
}
async function refreshBoard() {
  const session=await api('/api/auth/session'); setAccount(session.user,session.csrf_token);
  if(session.user.must_change_password) {setView('profile',false);return;}
  await loadDashboard(false); if(state.view==='calendar') renderCalendar();
}

async function loadMyTeam() {
  $('#profile-team-title').textContent=state.user.role==='admin'?'Teams overview':'My team';
  const teams=await loadTeams();
  $('#my-team-details').innerHTML=teams.length?teams.map(t=>`<article class="team-card"><h3>${escapeHtml(t.name)}</h3><p>${t.members.filter(m=>m.is_active).length} active members</p><ul class="member-list">${t.members.map(m=>`<li><strong>${escapeHtml(m.name)}${m.id===state.user.id?' (you)':''}</strong><span>${escapeHtml(m.username)}${m.is_active?'':' · Inactive'}</span></li>`).join('')||'<li>No members yet</li>'}</ul></article>`).join(''):'<p class="helper-text">You are not currently assigned to a team. Your administrator can update your membership.</p>';
}
function updateNoteBadge(id,count) {
  workspaceState.noteCounts[id]=count;
  const button=$(`[data-project-notes="${id}"]`);
  if(!button) return;
  $('.note-unread-dot',button)?.classList.toggle('hidden',!count);
  button.setAttribute('aria-label',count?`Add Note — ${count} unread notes`:'Add Note');
  button.title=count?`${count} unread note${count===1?'':'s'}`:'Open shared project notes';
}
async function refreshNoteBadge(id) {
  if(workspaceState.noteReadPending[id]) return;
  const userId=state.user?.id, request=(workspaceState.noteStatusRequests[id]||0)+1;
  workspaceState.noteStatusRequests[id]=request;
  const result=await api(`/api/projects/${id}/notes/status`);
  if(state.user?.id===userId && workspaceState.noteStatusRequests[id]===request && !workspaceState.noteReadPending[id]) updateNoteBadge(id,result.unread_count);
}
async function acknowledgeDisplayedNotes(id,notes) {
  if(!$('#notes-dialog').open || document.hidden || id!==workspaceState.notesProjectId) return;
  const userId=state.user?.id, request=(workspaceState.noteStatusRequests[id]||0)+1;
  workspaceState.noteStatusRequests[id]=request;
  workspaceState.noteReadPending[id]=(workspaceState.noteReadPending[id]||0)+1;
  try {
    const result=await api(`/api/projects/${id}/notes/read`,{method:'POST',body:{note_ids:notes.map(n=>n.id)}});
    if(state.user?.id===userId && workspaceState.noteStatusRequests[id]===request) updateNoteBadge(id,result.unread_count);
  } finally {
    if(state.user?.id===userId) workspaceState.noteReadPending[id]--;
  }
}
async function loadProjectNotes() {
  const id=workspaceState.notesProjectId, request=++workspaceState.notesRequest;
  const result=await api(`/api/projects/${id}/notes`);
  if(request!==workspaceState.notesRequest || id!==workspaceState.notesProjectId) return;
  $('#notes-form').classList.toggle('hidden',!result.can_edit);
  $('#notes-readonly').classList.toggle('hidden',Boolean(result.can_edit));
  renderProjectNotes(result.notes);
  await acknowledgeDisplayedNotes(id,result.notes);
}
function renderProjectNotes(notes) {
  $('#project-notes-list').innerHTML=notes.length?notes.map(n=>`<article class="shared-note"><header><div><strong>${escapeHtml(n.author_name)}</strong><small>${new Date(n.created_at).toLocaleString('en-AU')}</small></div>${n.can_delete?`<button type="button" class="button secondary small danger-text" data-remove-note="${n.id}">Remove</button>`:''}</header><p>${escapeHtml(n.body)}</p></article>`).join(''):'<p class="helper-text">No project notes yet.</p>';
}
async function openProjectNotes(id) {
  workspaceState.notesProjectId=Number(id); $('#notes-form').reset();
  const project=state.projectData?.project?.id===Number(id)?state.projectData.project:state.projects.find(p=>p.id===Number(id));
  $('#notes-form').classList.toggle('hidden',!project?.can_edit);
  $('#notes-readonly').classList.toggle('hidden',Boolean(project?.can_edit));
  $('#notes-title').textContent=project?.name||'Important notes';
  $('#project-notes-list').textContent='Loading notes…';
  if(!$('#notes-dialog').open) $('#notes-dialog').showModal();
  await loadProjectNotes(); if(project?.can_edit)$('#note-body').focus();
}
async function saveProjectNote() {
  const id=workspaceState.notesProjectId;
  const result=await api(`/api/projects/${id}/notes`,{method:'POST',body:{body:$('#note-body').value}});
  if(id!==workspaceState.notesProjectId) return;
  workspaceState.notesRequest++;
  $('#note-body').value=''; renderProjectNotes(result.notes); await acknowledgeDisplayedNotes(id,result.notes); toast('Note shared with the project');
}
async function removeProjectNote(button) {
  if(!confirm('Remove this note for everyone?')) return;
  const id=workspaceState.notesProjectId; button.disabled=true;
  try {
    const result=await api(`/api/projects/${id}/notes/${Number(button.dataset.removeNote)}`,{method:'DELETE',body:{}});
    if(id===workspaceState.notesProjectId) {workspaceState.notesRequest++; renderProjectNotes(result.notes); await acknowledgeDisplayedNotes(id,result.notes);}
  } finally {button.disabled=false;}
}

function renderCalendar() {
  const month=workspaceState.month;
  const y=month.getFullYear(), m=month.getMonth();
  $('#calendar-month').textContent=month.toLocaleDateString('en-AU',{month:'long',year:'numeric'});
  const offset=(new Date(y,m,1).getDay()+6)%7;
  const dayCount=new Date(y,m+1,0).getDate();
  const cells=Math.ceil((offset+dayCount)/7)*7;
  let html=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((d,i)=>`<div class="calendar-weekday ${i>=5?'is-weekend':''}">${d}${i>=5?'<small>Weekend</small>':''}</div>`).join('');
  const projects=state.projects.filter(p=>p.submission_deadline);
  for(let i=0;i<cells;i++) {
    const day=new Date(y,m,i-offset+1), key=localDateKey(day);
    const items=projects.filter(p=>p.submission_deadline===key);
    const weekend=day.getDay()===0||day.getDay()===6;
    html+=`<div class="calendar-day ${weekend?'is-weekend':''} ${day.getMonth()!==m?'outside-month':''} ${key===localDateKey()?'is-today':''}"><time datetime="${key}" aria-label="${escapeHtml(dateLabel(key))}${weekend?', weekend':''}">${day.getDate()}</time>${items.map(p=>`<button class="calendar-event ${p.status==='completed'?'done':isOverdue(p)?'late':p.is_assigned?'assigned':''}" type="button" data-project-brief="${p.id}" title="${escapeHtml(p.name)} — ${escapeHtml(statusNames[p.status])}">${escapeHtml(p.name)}</button>`).join('')}</div>`;
  }
  $('#calendar-grid').innerHTML=html;
  const monthProjects=projects.filter(p=>p.submission_deadline.startsWith(`${y}-${String(m+1).padStart(2,'0')}`)).sort((a,b)=>a.submission_deadline.localeCompare(b.submission_deadline));
  renderCalendarSummary(monthProjects);
}
function bindWorkspaceEvents() {
  setInterval(async()=>{
    if(!state.user || state.user.must_change_password || document.hidden || workspaceState.notesSyncBusy) return;
    workspaceState.notesSyncBusy=true;
    try {
      if($('#notes-dialog').open) await loadProjectNotes();
      else if(state.view==='estimate' && state.projectId) await refreshNoteBadge(state.projectId);
    } catch(_) {} finally {workspaceState.notesSyncBusy=false;}
  },15000);
  setInterval(()=>{if(state.user&&!state.user.must_change_password&&!document.hidden)refreshReadOnlyBrief().catch(()=>{});},15000);
  $('#refresh-my-team').addEventListener('click',()=>loadMyTeam().catch(error=>toast(error.message,true)));
  $('#notes-form').addEventListener('submit',event=>submitWithButton(event,saveProjectNote));
  $('#refresh-notes').addEventListener('click',()=>loadProjectNotes().catch(error=>toast(error.message,true)));
  setInterval(()=>{
    if(state.user && !state.user.must_change_password && ['home','calendar'].includes(state.view) && !document.hidden && !$('dialog[open]')) refreshBoard().catch(()=>{});
  },30000);
  $('#login-form').addEventListener('submit',event=>submitWithButton(event,async()=>{
    $('#login-error').textContent='';
    try {
      const result=await api('/api/auth/login',{method:'POST',body:{username:$('#login-username').value,password:$('#login-password').value}});
      $('#login-password').value=''; await enterWorkspace(result);
    } catch(error) { $('#login-error').textContent=error.message; }
  }));
  $('#logout-button').addEventListener('click',async()=>{
    try { await api('/api/auth/logout',{method:'POST',body:{}}); showLogin(); }
    catch(error) { toast(error.message,true); }
  });
  $('#profile-form').addEventListener('submit',event=>submitWithButton(event,saveProfile));
  $('#user-form').addEventListener('submit',event=>submitWithButton(event,saveUser));
  $('#assignment-user-search').addEventListener('input',()=>{
    const term=$('#assignment-user-search').value.trim().toLowerCase();
    const choices=$$('#individual-assignment-options [data-access-user]');
    choices.forEach(el=>el.classList.toggle('hidden',!el.dataset.search.includes(term)));
    $('#assignment-user-empty').classList.toggle('hidden',!choices.length||choices.some(el=>!el.classList.contains('hidden')));
  });
  $('#assignment-user-search').addEventListener('keydown',event=>{if(event.key==='Enter')event.preventDefault();});
  $('#project-workflow-form').addEventListener('submit',event=>submitWithButton(event,saveProjectWorkflow));
  $('#team-form').addEventListener('submit',event=>submitWithButton(event,saveTeam));
  $('#add-team').addEventListener('click',()=>openTeamEditor());
  $('#user-role').addEventListener('change',syncUserRole);
  $('#brief-delete').addEventListener('click',()=>deleteManagedProject().catch(error=>toast(error.message,true)));
  $('#add-user').addEventListener('click',()=>openUserEditor());
  $('#project-search').addEventListener('input',renderProjectBoard);
  $('#project-view-style').addEventListener('change',event=>{
    const value=event.target.value;if(!['cards','list','compact'].includes(value))return;
    workspaceState.boardView=value;
    try{localStorage.setItem('conest-project-view-'+state.user.id,value);}catch(_){}
    renderProjectBoard();
  });
  $('#open-calendar').addEventListener('click',event=>{if(event.currentTarget.tagName!=='A')setView('calendar');});
  $('#brief-open-estimate').addEventListener('click',event=>{ if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return; $('#project-brief-dialog').close(); if(event.currentTarget.tagName!=='A')openProject(workspaceState.briefId).catch(error=>toast(error.message,true)); });
  $('#calendar-prev').addEventListener('click',()=>{workspaceState.month=new Date(workspaceState.month.getFullYear(),workspaceState.month.getMonth()-1,1);renderCalendar();});
  $('#calendar-next').addEventListener('click',()=>{workspaceState.month=new Date(workspaceState.month.getFullYear(),workspaceState.month.getMonth()+1,1);renderCalendar();});
  document.addEventListener('click',event=>{
    const older=event.target.closest('[data-older-activity]');
    if(older)loadOlderProjectActivity(older).catch(error=>toast(error.message,true));
    const note=event.target.closest('[data-project-notes]');
    if(note) openProjectNotes(note.dataset.projectNotes).catch(error=>toast(error.message,true));
    const removeNote=event.target.closest('[data-remove-note]');
    if(removeNote) removeProjectNote(removeNote).catch(error=>toast(error.message,true));
    const brief=event.target.closest('[data-project-brief]');
    if (brief) openProjectBrief(brief.dataset.projectBrief).catch(error=>toast(error.message,true));
    const open=event.target.closest('[data-open-project]');
    if (open && open.tagName!=='A') openProject(open.dataset.openProject).catch(error=>toast(error.message,true));
    const user=event.target.closest('[data-edit-user]');
    if(user) openUserEditor(user.dataset.editUser);
    const team=event.target.closest('[data-edit-team]');
    if(team) openTeamEditor(team.dataset.editTeam);
    const refresh=event.target.closest('[data-refresh-estimate]');
    if(refresh && confirm('Reload the latest estimate? Unsaved fields will be discarded.')) loadProject(Number(refresh.dataset.refreshEstimate)).catch(error=>toast(error.message,true));
    const filter=event.target.closest('[data-filter]');
    if(filter) { workspaceState.filter=filter.dataset.filter; renderProjectBoard(); }
  });
}
