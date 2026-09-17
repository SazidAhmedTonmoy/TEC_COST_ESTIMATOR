/* Project board, account administration and deadline calendar. */
const workspaceState = { filter: 'all', users: [], teams: [], notesProjectId: null, notesRequest: 0, noteCounts: {}, noteStatusRequests: {}, noteReadPending: {}, notesSyncBusy: false, teamId: null, briefId: null, userId: null, month: new Date(new Date().getFullYear(), new Date().getMonth(), 1), briefRequest: 0 };
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
  state.user = user; state.csrfToken = token;
  $$('.user-only').forEach(el=>el.classList.toggle('hidden',user.role==='admin'));
  if(user.role==='admin' && workspaceState.filter==='team') workspaceState.filter='all';
  $('#account-name').textContent = user.name;
  $('#account-role').textContent = `${user.job_title || (user.role === 'admin' ? 'Administrator' : 'Estimator')} · ${user.role === 'admin' ? 'Admin' : 'User'}`;
  $('.app-shell').classList.remove('hidden');
  $('#login-screen').classList.add('hidden');
  $$('.admin-only').forEach(element => element.classList.toggle('hidden',user.role !== 'admin' || Boolean(user.must_change_password)));
}
function showLogin() {
  if(typeof resetHelpChat==='function')resetHelpChat();
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

function teamNames(project) { return (project.teams || []).map(t=>t.name).join(', ') || 'No team assigned'; }
function inReviewQueue(project) { return state.user?.role === 'admin' && project.needs_admin_review; }
function renderHome() {
  if (!state.user) return;
  const projects = state.projects;
  $('#welcome-name').textContent = `Welcome, ${state.user.name}`;
  $('#welcome-date').textContent = new Date().toLocaleDateString('en-AU',{weekday:'long',day:'numeric',month:'long',year:'numeric'});
  const metrics = Object.entries(statusNames).map(([key,label]) => [label,projects.filter(p=>p.status===key && !inReviewQueue(p)).length,key]);
  if (state.user.role==='admin') metrics.unshift(['Newly added',projects.filter(inReviewQueue).length,'new']);
  $('#home-metrics').innerHTML = metrics.map(([label,value,filter]) => `<button class="metric home-metric ${filter==='new'?'accent':''}" type="button" data-filter="${filter}"><span>${label}</span><strong>${value}</strong><small>${filter==='new'?'Open to review new team projects':filter==='draft'?'Ready to begin':filter==='in_progress'?'Estimates being prepared':filter==='submitted'?'Sent for review or approval':'Finished project archive'}</small></button>`).join('');
  $('#home-metrics').classList.toggle('five-metrics',state.user.role==='admin');
  renderProjectBoard();
  if(typeof loadReminders==='function')loadReminders().catch(()=>{});
  const due = projects.filter(p=>p.submission_deadline && isOpenProject(p)).sort((a,b)=>a.submission_deadline.localeCompare(b.submission_deadline));
  $('#deadline-agenda').innerHTML = due.length ? due.slice(0,8).map(p=>`<button class="deadline-item ${isOverdue(p)?'overdue':''}" type="button" data-project-brief="${p.id}"><span>${isOverdue(p)?'Overdue · ':''}${dateLabel(p.submission_deadline)}</span><strong>${escapeHtml(p.name)}</strong><small>${escapeHtml(teamNames(p))}</small></button>`).join('') : '<p class="board-empty">No pending deadlines. Add a deadline in Manage project.</p>';
  const values = new Map();
  projects.filter(p=>p.status!=='completed').forEach(p=>values.set(p.currency,(values.get(p.currency)||0)+Number(p.totals?.quoted||0)));
  $('#portfolio-value').textContent = values.size ? 'Active estimate value: '+[...values].map(([currency,value])=>`${currency} ${fmtMoney(value,currency)}`).join(' · ') : '';
}
function renderProjectBoard() {
  const term = $('#project-search').value.trim().toLowerCase();
  const filter = workspaceState.filter;
  $$('#project-tabs button').forEach(b=>{b.classList.toggle('active',b.dataset.filter===filter);b.setAttribute('aria-pressed',String(b.dataset.filter===filter));});
  const projects = state.projects.filter(p=>{
    if (!(p.name+' '+(p.client||'')+' '+(p.created_by_name||'')+' '+teamNames(p)+' '+(p.contributors||[]).map(c=>c.name).join(' ')).toLowerCase().includes(term)) return false;
    if (filter==='new') return inReviewQueue(p);
    if (filter==='team') return p.is_assigned;
    if (filter==='mine') return p.is_owner;
    if (statusNames[filter]) return p.status===filter && !inReviewQueue(p);
    return true;
  });
  $('#project-board').innerHTML = projects.length ? projects.map(p=>`<article class="project-card">
    <div class="project-card-heading"><div><p>${escapeHtml(p.client||'Client not set')}</p><h3><button type="button" data-project-brief="${p.id}">${escapeHtml(p.name)}</button></h3></div>${inReviewQueue(p)?'<span class="project-status status-new">Newly added</span>':projectStatus(p)}</div>
    <p class="project-scope-excerpt">${escapeHtml(p.scope_of_work||'Add the scope of work in Manage project.')}</p>
    <div class="project-facts"><span class="${isOverdue(p)?'overdue-text':''}">${isOverdue(p)?'Overdue · ':''}${dateLabel(p.submission_deadline)}</span>${inReviewQueue(p)?projectStatus(p):''}${projectOutcome(p)}</div>
    <p class="project-team"><strong>Team:</strong> ${escapeHtml(teamNames(p))}<br><strong>Added by:</strong> ${escapeHtml(p.created_by_name||'Existing project · creator not recorded')}${p.completed_by_name?`<br>Completed by ${escapeHtml(p.completed_by_name)}`:p.updated_by_name?`<br>Last edited by ${escapeHtml(p.updated_by_name)}`:''}</p>
    <div class="project-card-footer"><span>${p.line_count||0} items · ${escapeHtml(p.currency)} ${fmtMoney(p.totals?.quoted,p.currency)}</span><div><button type="button" class="text-button" data-project-brief="${p.id}">Manage project</button><button class="text-button" type="button" data-copy-project="${p.id}">Copy</button><a class="button secondary small" href="#/estimate/${p.id}" data-open-project="${p.id}">${p.can_edit?'Open estimate':'View estimate'}</a></div></div>
  </article>`).join('') : '<div class="board-empty"><h3>No projects here yet</h3><p>New projects are shared with your team automatically. You can also work on projects an administrator assigns to your team.</p></div>';
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
  $('#estimate-project-brief').innerHTML = project.id ? `<div><h2>${escapeHtml(project.name)}</h2><p>${dateLabel(project.submission_deadline)} · ${escapeHtml(teamNames(project))}${project.can_edit?'':' · Read-only completed project'}</p></div><div>${projectStatus(project)}<button class="button secondary" type="button" data-project-brief="${project.id}">Manage project & activity</button><button type="button" data-project-notes="${project.id}" class="button secondary note-button" aria-label="Add Note${workspaceState.noteCounts[project.id]?' — unread notes':''}">Add Note<span class="note-unread-dot ${workspaceState.noteCounts[project.id]?'':'hidden'}" aria-hidden="true"></span></button><button class="button secondary" type="button" data-revisions="${project.id}">Revisions</button><button class="button secondary" type="button" data-copy-project="${project.id}">Copy project</button><button class="button secondary" type="button" data-refresh-estimate="${project.id}">Refresh estimate</button></div>` : '';
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
  const [teams,history]=await Promise.all([state.user.role==='admin'?loadTeams():Promise.resolve([]),api(`/api/projects/${p.id}/activity`)]);
  if(request!==workspaceState.briefRequest) return;
  workspaceState.briefId=p.id; workspaceState.briefProject=p;
  $('#brief-open-estimate').href=`#/estimate/${p.id}`;
  $('#brief-title').textContent=p.name; $('#brief-client').textContent=p.client||'Manage project';
  $('#brief-summary').innerHTML=`<div class="brief-meta">${projectStatus(p)}<span>Added by: ${escapeHtml(p.created_by_name||'Creator not recorded')}</span><span>Team: ${escapeHtml(teamNames(p))}</span></div><p class="helper-text">Contributors: ${p.contributors?.length?p.contributors.map(u=>escapeHtml(u.name)).join(', '):'No recorded work yet'}</p>`;
  $('#brief-scope').value=p.scope_of_work||''; $('#brief-deadline').value=p.submission_deadline||''; $('#brief-status').value=p.status;
  $('#brief-scope').disabled=!p.can_manage; $('#brief-deadline').disabled=!p.can_manage;
  $('#brief-award-status').value=p.award_status||'';syncProjectOutcome(p.can_edit);
  $('#brief-status').disabled=!p.can_edit; $('#brief-save').disabled=!p.can_edit;
  $('#brief-save').classList.toggle('hidden',!p.can_edit);
  $('#brief-delete').classList.toggle('hidden',!p.can_delete);
  $('#assignment-options').innerHTML=teams.map(t=>`<label class="checkbox-label"><input type="checkbox" value="${t.id}" ${(p.teams||[]).some(a=>a.id===t.id)?'checked':''}><span>${escapeHtml(t.name)}<small>${t.members.filter(m=>m.is_active).length} active members</small></span></label>`).join('')||'<p class="helper-text">Create a team in Manage users.</p>';
  $('#project-contributors').innerHTML=history.contributors?.length?'<h4>Project contributors</h4>'+history.contributors.map(c=>`<article class="contributor-card"><strong>${escapeHtml(c.name)}</strong><span>${escapeHtml(c.teams || (c.admin_contribution?'Administrator':'Historical team not recorded'))}</span><small>${c.actions} recorded actions · Last contribution ${new Date(c.last_activity).toLocaleString('en-AU')}</small></article>`).join(''):'<p class="helper-text">No contributions recorded yet.</p>';
  $('#project-activity').innerHTML=history.activity.length?history.activity.map(a=>`<article class="activity-entry"><strong>${escapeHtml(a.name||'Former user')} · ${escapeHtml(a.action)}</strong><small>${escapeHtml(a.team_name_snapshot || (a.role_snapshot==='admin'?'Administrator':'Historical team not recorded'))} · ${new Date(a.created_at).toLocaleString('en-AU')}</small>${a.details?`<p>${escapeHtml(a.details)}</p>`:''}</article>`).join(''):'<p class="helper-text">No activity recorded yet.</p>';
  if(!$('#project-brief-dialog').open) $('#project-brief-dialog').showModal();
}
async function saveProjectWorkflow() {
  const p=workspaceState.briefProject;
  if(!p) throw new Error('Project no longer available');
  const payload={status:$('#brief-status').value,award_status:$('#brief-award-status').value,expected_revision:p.revision};
  if(p.can_manage) {payload.scope_of_work=$('#brief-scope').value;payload.submission_deadline=$('#brief-deadline').value;}
  if(state.user.role==='admin') payload.team_ids=$$('#assignment-options input:checked').map(input=>Number(input.value));
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
  const result=await api('/api/auth/profile',{method:'PATCH',body:{email:$('#profile-email').value,name:$('#profile-name').value,username:$('#profile-username').value,job_title:$('#profile-title').value,password,current_password:$('#profile-current-password').value}});
  const setup=state.user.must_change_password;
  setAccount(result.user,result.csrf_token);
  if (setup) await enterWorkspace(result); else { renderProfile(); await loadDashboard(); }
  toast('Profile saved');
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
  const payload={name:$('#user-name').value,username:$('#user-username').value,job_title:$('#user-title').value,role:$('#user-role').value,team_id:$('#user-role').value==='admin'?null:Number($('#user-team').value)||null};
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
  renderProjectNotes(result.notes);
  await acknowledgeDisplayedNotes(id,result.notes);
}
function renderProjectNotes(notes) {
  $('#project-notes-list').innerHTML=notes.length?notes.map(n=>`<article class="shared-note"><header><div><strong>${escapeHtml(n.author_name)}</strong><small>${new Date(n.created_at).toLocaleString('en-AU')}</small></div><button type="button" class="button secondary small danger-text" data-remove-note="${n.id}">Remove</button></header><p>${escapeHtml(n.body)}</p></article>`).join(''):'<p class="helper-text">No notes yet. Add the first reminder for this project.</p>';
}
async function openProjectNotes(id) {
  workspaceState.notesProjectId=Number(id); $('#notes-form').reset();
  const project=state.projects.find(p=>p.id===Number(id)) || state.projectData?.project;
  $('#notes-title').textContent=project?.name||'Important notes';
  $('#project-notes-list').textContent='Loading notes…';
  if(!$('#notes-dialog').open) $('#notes-dialog').showModal();
  await loadProjectNotes(); $('#note-body').focus();
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
  let html=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d=>`<div class="calendar-weekday">${d}</div>`).join('');
  const projects=state.projects.filter(p=>p.submission_deadline);
  for(let i=0;i<cells;i++) {
    const day=new Date(y,m,i-offset+1), key=localDateKey(day);
    const items=projects.filter(p=>p.submission_deadline===key);
    html+=`<div class="calendar-day ${day.getMonth()!==m?'outside-month':''} ${key===localDateKey()?'is-today':''}"><time datetime="${key}">${day.getDate()}</time>${items.map(p=>`<button class="calendar-event ${p.status==='completed'?'done':isOverdue(p)?'late':p.is_assigned?'assigned':''}" type="button" data-project-brief="${p.id}" title="${escapeHtml(p.name)} — ${escapeHtml(statusNames[p.status])}">${escapeHtml(p.name)}</button>`).join('')}</div>`;
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
  $('#project-workflow-form').addEventListener('submit',event=>submitWithButton(event,saveProjectWorkflow));
  $('#team-form').addEventListener('submit',event=>submitWithButton(event,saveTeam));
  $('#add-team').addEventListener('click',()=>openTeamEditor());
  $('#user-role').addEventListener('change',syncUserRole);
  $('#brief-delete').addEventListener('click',()=>deleteManagedProject().catch(error=>toast(error.message,true)));
  $('#add-user').addEventListener('click',()=>openUserEditor());
  $('#project-search').addEventListener('input',renderProjectBoard);
  $('#refresh-home').addEventListener('click',()=>refreshBoard().catch(error=>toast(error.message,true)));
  $('#open-calendar').addEventListener('click',event=>{if(event.currentTarget.tagName!=='A')setView('calendar');});
  $('#brief-open-estimate').addEventListener('click',event=>{ if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return; $('#project-brief-dialog').close(); if(event.currentTarget.tagName!=='A')openProject(workspaceState.briefId).catch(error=>toast(error.message,true)); });
  $('#calendar-prev').addEventListener('click',()=>{workspaceState.month=new Date(workspaceState.month.getFullYear(),workspaceState.month.getMonth()-1,1);renderCalendar();});
  $('#calendar-next').addEventListener('click',()=>{workspaceState.month=new Date(workspaceState.month.getFullYear(),workspaceState.month.getMonth()+1,1);renderCalendar();});
  $('#calendar-today').addEventListener('click',()=>{workspaceState.month=new Date(new Date().getFullYear(),new Date().getMonth(),1);renderCalendar();});
  document.addEventListener('click',event=>{
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
