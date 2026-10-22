/* project_sharing.js */
function bindProjectSharing(){
 let project=null,busy=false;
 const dialog=$('#project-share-dialog'),url=$('#project-share-url'),status=$('#project-share-status');
 $('#share-project-button').addEventListener('click',()=>{if(!state.projectData?.project.can_manage)return;project=state.projectId;url.value='';status.textContent='';$('#copy-project-share').disabled=true;dialog.showModal();});
 for(const [selector,action]of [['#create-project-share','create'],['#revoke-project-share','revoke']])$(selector).addEventListener('click',async()=>{
  if(busy)return;
  if(!confirm(action==='create'?'Create a public read-only link with all prices and component details? Any previous link will stop working.':'Revoke this project’s public link?'))return;
  busy=true;dialog.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{const result=await api(`/api/projects/${project}/share`,{method:'POST',body:{action}});url.value=result.path?new URL(result.path,location.origin).href:'';status.textContent=result.path?'Link ready. Anyone with this link can view this project.':'Public access revoked.';}
  catch(error){status.textContent=error.message;}
  finally{busy=false;dialog.querySelectorAll('button').forEach(b=>b.disabled=false);$('#copy-project-share').disabled=!url.value;}
 });
 dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault()});
 $('#copy-project-share').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(url.value);status.textContent='Link copied.';}catch{url.focus();url.select();status.textContent='Select and copy the link above.';}});
}
function bindFrozenEstimateHeader(){
 const table=document.querySelector('.estimate-table'),wrapper=table.parentElement;
 const floating=document.createElement('div');floating.className='frozen-estimate-heading';floating.setAttribute('aria-hidden','true');floating.hidden=true;document.body.append(floating);
 let scheduled=false,signature='',copy=null;
 function update(){
  scheduled=false;
  const rect=table.getBoundingClientRect(),frame=wrapper.getBoundingClientRect(),head=table.tHead;
  const top=0,height=head.getBoundingClientRect().height;
  const visible=innerWidth>820&&state.view==='estimate'&&rect.top<top&&rect.bottom>top+height;
  document.body.style.setProperty('--estimate-heading-bottom',`${top+height+10}px`);
  floating.hidden=!visible;document.body.classList.toggle('estimate-heading-frozen',visible);if(!visible)return;
  floating.style.cssText=`top:${top}px;left:${Math.max(0,frame.left)}px;width:${Math.min(frame.right,innerWidth)-Math.max(0,frame.left)}px`;
  const widths=[...head.rows[0].cells].map(c=>c.getBoundingClientRect().width),next=widths.join(',');
  if(next!==signature||!copy){
   signature=next;copy=document.createElement('table');copy.className='estimate-table';copy.style.width=rect.width+'px';copy.style.minWidth=rect.width+'px';copy.style.tableLayout='fixed';
   const group=document.createElement('colgroup');for(const width of widths){const col=document.createElement('col');col.style.width=width+'px';group.append(col);}copy.append(group,head.cloneNode(true));floating.replaceChildren(copy);
  }
  copy.style.transform=`translateX(${-wrapper.scrollLeft}px)`;
 }
 function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(update)}}
 document.addEventListener('scroll',schedule,{passive:true,capture:true});window.addEventListener('resize',schedule,{passive:true});new ResizeObserver(schedule).observe(table);window.addEventListener('hashchange',schedule);
}

;
/* workspace_switch.js */
/* Tender assets are loaded only when entering the tender workspace. */
document.addEventListener('DOMContentLoaded',()=>{
 const inTenders=new URLSearchParams(location.search).get('workspace')==='tenders';
 const brand=document.querySelector('.sidebar .brand');
 const swap=document.createElement('a');swap.className='workspace-swap';swap.href=inTenders?'/':'/tenders/';swap.title=inTenders?'Switch to Estimator':'Switch to Tenders';swap.setAttribute('aria-label',swap.title);
 swap.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 10a9 9 0 0 1 15-6l3 3M21 2v5h-5M21 14a9 9 0 0 1-15 6l-3-3M3 22v-5h5"/></svg>';
 const wrap=document.createElement('div');wrap.className='workspace-brand';brand.before(wrap);wrap.append(brand,swap);
 if(inTenders){document.documentElement.dataset.workspace='tenders';brand.querySelector('div:last-child span').textContent='TENDERS';brand.href='/tenders/';brand.removeAttribute('data-view');
 const nav=document.querySelector('#main-navigation');nav.querySelectorAll('.nav-button').forEach(a=>a.remove());
 const pages=[['dashboard','Home','⌂'],['chase-up','Project Chase-up','☷'],['projects','Projects','▦'],['builders','Builders','♙'],['calendar','Calendar','▤'],['reminders','Reminders','◷']];
 for(const [path,label,icon] of pages.reverse()){const a=document.createElement('a');a.className='nav-button';a.href='/tenders/'+path;a.innerHTML=`<span>${icon}</span> ${label}`;nav.prepend(a);}
 }
});

;
/* mobile.js */
document.addEventListener('DOMContentLoaded',()=>{
 const sidebar=document.querySelector('.sidebar'),button=document.getElementById('mobile-menu-button');
 function close(){sidebar.classList.remove('menu-open');button.setAttribute('aria-expanded','false');}
 button.addEventListener('click',()=>{const open=button.getAttribute('aria-expanded')!=='true';sidebar.classList.toggle('menu-open',open);button.setAttribute('aria-expanded',String(open));});
 sidebar.addEventListener('click',event=>{if(event.target.closest('a[href^="#/"]'))close();});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&button.getAttribute('aria-expanded')==='true'){close();button.focus();}});
 window.addEventListener('hashchange',close);
 window.matchMedia('(min-width: 821px)').addEventListener('change',close);
});

;
/* file_drop.js */
/* Select a dropped file; the existing preview/import button confirms submission. */
function bindFileDrop(zone,input,extensions,maxBytes,status){
  let depth=0;
  function message(text){status.textContent=text;status.classList.remove('hidden');}
  zone.addEventListener('dragenter',event=>{event.preventDefault();depth++;zone.classList.add('drop-active');});
  zone.addEventListener('dragover',event=>{event.preventDefault();event.dataTransfer.dropEffect='copy';});
  zone.addEventListener('dragleave',()=>{if(--depth<=0){depth=0;zone.classList.remove('drop-active');}});
  zone.addEventListener('drop',event=>{
    event.preventDefault();depth=0;zone.classList.remove('drop-active');
    const files=event.dataTransfer.files;
    if(files.length!==1){message('Drop one file at a time.');return;}
    const file=files[0],ext=file.name.toLowerCase().split('.').pop();
    if(!extensions.includes(ext)){message('Choose a '+extensions.join(' or ').toUpperCase()+' file.');return;}
    if(file.size>maxBytes){message('This file exceeds the '+Math.round(maxBytes/1024/1024)+' MB limit.');return;}
    if(input.disabled){message('File selection is currently unavailable.');return;}
    const transfer=new DataTransfer();transfer.items.add(file);input.files=transfer.files;
    input.dispatchEvent(new Event('change',{bubbles:true}));
    message(file.name+' selected. Use the button below to continue.');
  });
}
document.addEventListener('DOMContentLoaded',()=>{
  bindFileDrop(document.querySelector('#drop-zone'),document.querySelector('#import-file'),['xlsx','xlsm'],80*1024*1024,document.querySelector('#import-progress'));
  bindFileDrop(document.querySelector('.light-upload-file'),document.querySelector('#light-price-file'),['xlsx','pdf'],30*1024*1024,document.querySelector('#light-price-import-status'));
});

;
/* builders.js */
/* Optional project builders. One name per row; punctuation is part of a name. */
function projectBuilders(project = {}) {
  const values = Array.isArray(project.builders) ? project.builders : String(project.client || '').split(/\r?\n/);
  const seen = new Set();
  return values.map(name => String(name || '').trim().replace(/\s+/g, ' ')).filter(name => {
    const key = name.toLocaleLowerCase();
    if (!name || seen.has(key)) return false;
    seen.add(key); return true;
  });
}
function builderText(project, empty = '') { return projectBuilders(project).join(', ') || empty; }
function readBuilderEditor(id) {
  return Array.from(document.querySelectorAll(`#${id} [data-builder-name]`), input => input.value).filter(name => name.trim());
}
function updateBuilderRows(editor) {
  const rows = editor.querySelectorAll('.builder-row');
  rows.forEach((row, index) => {
    const input = row.querySelector('input'), button = row.querySelector('button');
    input.id = `${editor.id}-name-${index + 1}`;
    input.setAttribute('aria-label', `Builder ${index + 1}`);
    button.setAttribute('aria-label', `Remove builder ${index + 1}`);
  });
  editor.querySelector('[data-builder-add]').disabled = rows.length >= 100;
}
function appendBuilderRow(editor, name = '', focus = false) {
  const rows = editor.querySelector('[data-builder-rows]');
  if (rows.children.length >= 100) return;
  const row = document.createElement('div'); row.className = 'builder-row';
  const input = document.createElement('input');
  input.type = 'text'; input.dataset.builderName = ''; input.value = name;
  input.maxLength = 500; input.placeholder = 'Builder name'; input.autocomplete = 'off';
  const remove = document.createElement('button');
  remove.type = 'button'; remove.className = 'icon-button builder-remove';
  remove.dataset.builderRemove = ''; remove.textContent = '\u00d7'; remove.title = 'Remove builder';
  row.append(input, remove); rows.append(row); updateBuilderRows(editor);
  if (focus) input.focus();
}
function renderBuilderEditor(id, names = [], editable = true) {
  const editor = document.getElementById(id); if (!editor) return;
  editor.disabled = !editable;
  editor.querySelector('[data-builder-rows]').replaceChildren();
  (names.length ? names : ['']).forEach(name => appendBuilderRow(editor, name));
  const add = editor.querySelector('[data-builder-add]');
  add.hidden = !editable;
  editor.querySelectorAll('[data-builder-remove]').forEach(button => { button.hidden = !editable; });
  if (!editable && !names.length) editor.querySelector('input').placeholder = 'No builder assigned';
}
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-builder-editor]').forEach(editor => renderBuilderEditor(editor.id));
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-builder-add], [data-builder-remove]');
    if (!button) return;
    const editor = button.closest('[data-builder-editor]');
    if (!editor || editor.disabled || button.disabled) return;
    if (button.hasAttribute('data-builder-add')) {
      appendBuilderRow(editor, '', true);
    } else {
      const row = button.closest('.builder-row');
      const next = row.nextElementSibling || row.previousElementSibling;
      row.remove();
      if (!editor.querySelector('.builder-row')) appendBuilderRow(editor, '', true);
      else { updateBuilderRows(editor); next?.querySelector('input').focus(); }
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || !event.target.matches('[data-builder-name]') || event.isComposing) return;
    event.preventDefault();
    const row = event.target.closest('.builder-row'), editor = row.closest('[data-builder-editor]');
    if (editor.disabled) return;
    if (row.nextElementSibling) row.nextElementSibling.querySelector('input').focus();
    else if (event.target.value.trim()) appendBuilderRow(editor, '', true);
  });
});

;
/* app.js */
const state = {
  user: null,
  csrfToken: '',
  view: 'home',
  dashboard: null,
  projects: [],
  projectId: null,
  projectData: null,
  currentCatalogItem: null,
  manualAddToEstimate: false,
  manualEditId: null,
  manualLineId: null,
  manualSource: {},
  manualSaving: false,
  appSettings: null,
  suggestions: [],
  suggestionIndex: -1,
  catalogCache: new Map(),
  catalogCategories: [],
  activeSearchQuery: "",
  quickSearchRequest: 0,
  quickSearchTimer: null,
  quickSearchAdding: false,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

// Remove number-field focus before the browser can interpret a wheel gesture
// as a step. Keep native scrolling (including inside dialogs) and zoom intact.
// Delegation also covers estimate/component rows added after page load.
document.addEventListener("wheel", (event) => {
  const field = event.target;
  if (event.ctrlKey || !event.deltaY) return;
  if (field instanceof HTMLInputElement && field.type === "number"
      && field === document.activeElement) {
    field.blur();
  }
}, { capture: true, passive: true });

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmtMoney(value, currency) {
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: currency || state.projectData?.project?.currency || "AUD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function fmtNumber(value, digits = 2) {
  return new Intl.NumberFormat("en-AU", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(value || 0));
}

function dataStatusLabel(status) {
  return {
    ready: "Material + labour",
    material_only: "Material only",
    labour_only: "Labour only",
    reference_only: "Needs pricing",
  }[status] || "Catalog data";
}

function cleanEstimateTitle(value) {
  return String(value||'').replace(/\(([^()]*)\)/g,(whole,inner)=>/^(?:(?:l|length|qty|quantity)\s*[:=.-]?\s*)?\d+(?:\.\d+)?\s*(?:m|metres?|meters?|ea|pcs|units?|nos?\.?)?$/i.test(inner.trim())?'':whole).replace(/\s+/g,' ').trim();
}

function catalogName(item) {
  return escapeHtml(item.display_name || cleanEstimateTitle(item.name)) + (item.specification ? ` <span class="item-spec">${escapeHtml(item.specification)}</span>` : "");
}

function componentLabel(component) {
  const description = String(component.description || "");
  const size = String(component.size || "").trim();
  if(!size)return escapeHtml(description);
  const at=description.toLowerCase().indexOf(size.toLowerCase());
  return at<0?`${escapeHtml(description)} <strong class="component-spec">${escapeHtml(size)}</strong>`:
    `${escapeHtml(description.slice(0,at))}<strong class="component-spec">${escapeHtml(description.slice(at,at+size.length))}</strong>${escapeHtml(description.slice(at+size.length))}`;
}

function variantText(item) {
  const count = Number(item.variant_count || 1);
  return count > 1 ? `${count} source records` : "1 source record";
}

function typedQuantity(text) {
  const qty = String(text || "").match(/\b(?:qty|quantity)\s*[:=]?\s*(\d+(?:\.\d+)?)/i)
    || String(text || "").match(/^\s*(\d+(?:\.\d+)?)\s*[x×]\s*/i)
    || String(text || "").match(/[x×]\s*(\d+(?:\.\d+)?)\s*$/i);
  return qty ? Math.max(0, Number(qty[1])) : Number($("#smart-quantity")?.value || 1);
}

async function fetchCatalogItem(itemId) {
  const key = Number(itemId);
  if (state.catalogCache.has(key)) return state.catalogCache.get(key);
  const pending = api(`/api/catalog/${key}`).then((result) => result.item);
  state.catalogCache.set(key, pending);
  try {
    const item = await pending;
    state.catalogCache.set(key, item);
    return item;
  } catch (error) {
    state.catalogCache.delete(key);
    throw error;
  }
}

const pendingApiReads=new Map();
let apiGeneration=0;
async function api(path,options={}){
  const readOnly=['GET','HEAD'].includes((options.method||'GET').toUpperCase());
  const key=readOnly&&!options.signal?`${state.csrfToken}:${apiGeneration}:${path}`:null;
  if(key&&pendingApiReads.has(key))return structuredClone(await pendingApiReads.get(key));
  if(!readOnly)apiGeneration++;
  state.apiPendingCount=(state.apiPendingCount||0)+1;
  const request=apiRequest(path,options);
  if(key)pendingApiReads.set(key,request);
  try{return structuredClone(await request);}
  finally{
    state.apiPendingCount=Math.max(0,(state.apiPendingCount||1)-1);
    if(key)pendingApiReads.delete(key);
    if(!readOnly)apiGeneration++;
  }
}
async function apiRequest(path, options = {}) {
  const estimateBase = state.projectData;
  const config = { ...options, headers: { ...(options.headers || {}) } };
  config.credentials = 'same-origin';
  config.headers['X-ConEst-Request'] = '1';
  if (state.csrfToken) config.headers['X-CSRF-Token'] = state.csrfToken;
  if (config.body && !(config.body instanceof FormData)) {
    const match=path.match(/^\/api\/projects\/(\d+)(?:\/lines\/(\d+))?$/);
    if(match && ['PATCH','DELETE'].includes(config.method) && config.body.expected_revision===undefined) {
      const record=match[2]?state.projectData?.lines.find(l=>l.id===Number(match[2])):state.projectData?.project;
      if(record && state.projectId===Number(match[1])) config.body={...config.body,expected_revision:record.revision};
    }
    const estimatePath=path.match(/^\/api\/projects\/(\d+)(?:\/|$)/);
    if(estimatePath && Number(estimatePath[1])===state.projectId && estimateBase?.lines && /^\/api\/projects\/\d+(?:$|\/(?:reorder|manual-items|lines)(?:\/|$))/.test(path)) {
      config.body={...config.body,_known_lines:Object.fromEntries(estimateBase.lines.map(l=>[l.id,l.revision||0])),_known_pricing:['material_markup','labor_rate','labor_hours_markup','overhead_markup','crew_size','hours_per_day','excluded_categories'].map(k=>estimateBase.project[k]??0)};
      state.projectLoadRequest=(state.projectLoadRequest||0)+1;
    }
    // Section changes return complete estimates; invalidate pending loads without
    // supplying line-delta hints, because line revisions do not change here.
    if(estimatePath && Number(estimatePath[1])===state.projectId && /^\/api\/projects\/\d+\/sections\/(?:inclusion|remove)$/.test(path)) {
      state.projectLoadRequest=(state.projectLoadRequest||0)+1;
    }
    config.headers["Content-Type"] = "application/json";
    config.body = JSON.stringify(config.body);
  }
  const readOnly=['GET','HEAD'].includes((config.method||'GET').toUpperCase());
  let response,result;
  for(let attempt=0;attempt<1;attempt++){
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),readOnly?90000:120000);
    try {
      response=await fetch(path,{...config,signal:config.signal||controller.signal});
      const contentType=response.headers.get('content-type')||'';
      if(response.ok&&!contentType.includes('application/json'))throw new Error('The server returned an unexpected response. Refresh or try again shortly.');
      result=contentType.includes('application/json')?await response.json():null;
      break;
    }catch(error){
      if(config.signal?.aborted)throw error;
      const connectionError=error instanceof TypeError||error.name==='AbortError';
      if(connectionError)throw new Error(readOnly?'Connection interrupted or the server took too long. Check your connection and try again.':'Connection interrupted while saving. The change may have reached the server. Reload and check before submitting again.');
      if(error instanceof SyntaxError)throw new Error('The server returned an incomplete response. Reload to check the latest saved information.');
      throw error;
    }finally{clearTimeout(timer);}
  }
  if (!response.ok || (result && result.success === false)) {
    if (response.status === 401 && path !== '/api/auth/login') showLogin();
    const fallback=response.status===413?'The server rejected the upload size. Its hosting limit may be lower than the app limit; try a smaller file.':[502,503,504].includes(response.status)?'The server is starting, busy or timed out. Wait briefly and try again.':response.status>=500?'The server returned an error before application details were available. Ask your administrator to check the hosting error log.':`Request failed (${response.status})`;
    const error = new Error(result?.error || result?.message || fallback);
    error.status = response.status;
    throw error;
  }
  return mergeEstimateResponse(result,estimateBase);
}

function mergeEstimateResponse(result,base){
  if(!result?.estimate_delta&&!result?.estimate_order)return result;
  if(!base||base.project.id!==result.project.id)throw new Error('Estimate changed. Reload to see the saved result.');
  const rows=new Map(base.lines.map(line=>[line.id,line]));
  for(const line of result.lines||[])rows.set(line.id,line);
  for(const version of result.line_versions||[])rows.set(version.id,{...rows.get(version.id),...version});
  const lines=result.line_order.map((id,index)=>{const line=rows.get(id);if(!line)throw new Error('Estimate changed. Reload to see the saved result.');return {...line,sort_order:index*10};});
  const merged={...base,...result,lines};
  delete merged.estimate_delta;delete merged.estimate_order;delete merged.line_order;delete merged.line_versions;
  return merged;
}

let toastTimer;
function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("show"), 3500);
}

function setView(name, load = true, remember = true) {
  if (state.user?.must_change_password) name = 'profile';
  if (['users','settings'].includes(name) && state.user?.role !== 'admin') name = 'home';
  if(state.view !== name) { state.projectLoadRequest=(state.projectLoadRequest||0)+1; state.catalogDetailRequest=(state.catalogDetailRequest||0)+1; }
  state.view = name;
  if(remember && typeof rememberPage==='function') rememberPage(name);
  $$(".nav-button").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === `${name}-view`));
  const titles = { 'light-prices':'Light Price', home: 'Home', calendar: 'Deadline Calendar', users: 'Manage Users', profile: 'My Profile', estimate: "Build Estimate", catalog: "Catalog Explorer", imports: "Import Files", settings: "Application Settings" };
  $("#view-title").textContent = titles[name] || "TEC ConEst";
  $("#export-button").classList.toggle("hidden", name !== "estimate");
  $("#share-project-button").classList.toggle("hidden", name !== "estimate");
  $("#floating-search-button").classList.toggle("hidden", name !== "estimate");
  syncCategoryToggle();
  $('#project-select').classList.toggle('hidden', name !== 'estimate');
  $('#project-picker-wrap').classList.toggle('hidden', name !== 'estimate');
  $('#light-price-floating-search').classList.toggle('hidden', name !== 'light-prices');
  if(typeof closeProjectPicker==='function')closeProjectPicker();
  $('#delete-project-button').classList.toggle('hidden', name !== 'estimate');
  $('#new-project-button').classList.toggle('hidden', name !== 'estimate' || Boolean(state.user?.must_change_password));
  if (name === 'home') { renderHome(); if (load) loadDashboard().catch(error => toast(error.message,true)); }
  if (name === 'calendar') { renderCalendar(); if (load) loadDashboard().then(renderCalendar).catch(error => toast(error.message,true)); }
  if (name === 'profile') renderProfile();
  if (load && name === 'users') loadUsers().catch(error => toast(error.message,true));
  if (load && name === "catalog") loadCatalog();
  if (load && name === "light-prices") loadLightPrices().catch(error=>toast(error.message,true));
  if (load && name === "imports") loadImports().catch(error=>toast(error.message,true));
  if (load && name === "settings") {loadSettings(); if(typeof loadBackups==='function')loadBackups().catch(error=>toast(error.message,true));}
}

async function loadDashboard(reloadEstimate = true, initialData = null) {
  const uid=state.user?.id;
  const result = initialData || await api("/api/dashboard");
  if(uid!==state.user?.id)return;
  state.dashboard = result;
  state.projects = result.projects;
  state.catalogCategories = result.catalog?.categories || [];
  renderCatalogCategoryFilter();
  renderProjectSelect();
  $("#category-options").innerHTML = (result.manual_options?.categories || []).map((category) => `<option value="${escapeHtml(category)}">`).join("");
  if (!state.projects.some((project) => project.id === state.projectId && project.can_view)) state.projectId = null;
  if (state.projectId) { if(reloadEstimate) await loadProject(state.projectId); }
  else { state.projectData = null; renderProject(); }
  if(state.view==='home')renderHome();
}

function renderCatalogCategoryFilter() {
  const select = $("#catalog-category");
  if (!select) return;
  const current = select.value;
  select.innerHTML = `<option value="">All categories</option>` + state.catalogCategories
    .map((category) => `<option value="${escapeHtml(category.name)}">${escapeHtml(category.name)} (${Number(category.count).toLocaleString()})</option>`)
    .join("");
  if ([...select.options].some((option) => option.value === current)) select.value = current;
}

function renderProjectSelect() {
  const select = $("#project-select");
  const editable = state.projects.filter(project => project.can_view);
  select.innerHTML = '<option value="">Choose a project</option>' + editable.map((project) => `<option value="${project.id}">${escapeHtml(project.name)}</option>`).join('');
  select.disabled = !editable.length;
  if (state.projectId) select.value = String(state.projectId);
  if(typeof renderProjectPicker==='function')renderProjectPicker();
}

async function loadProject(projectId) {
  const request=state.projectLoadRequest=(state.projectLoadRequest||0)+1;
  if (!projectId) { state.projectId = null; state.projectData = null; renderProject(); if(typeof rememberPage==='function')rememberPage('estimate'); return; }
  const result = await api(`/api/projects/${projectId}`);
  // A read can start while a write is pending and return its older snapshot
  // after the write commits. Never replace a newer same-project response.
  const stale=()=>request!==state.projectLoadRequest || (
    state.projectId===Number(projectId) && state.projectData?.project?.id===Number(projectId) &&
    Number(result.project.revision)<Number(state.projectData.project.revision));
  if(stale())return false;
  await reviewOpenedProject(result.project);
  if(stale())return false;
  state.projectId = Number(projectId);
  state.projectData = result;
  renderProjectSelect();
  renderProject();
  if(state.view==='estimate' && typeof rememberPage==='function') rememberPage('estimate');
  return result;
}

function renderProject() {
  $("#share-project-button").disabled=!state.projectData?.project.can_manage;
  $$("#estimate-view input, #estimate-view textarea, #estimate-view select, #estimate-view button").forEach(field=>field.disabled=false);
  const available = Boolean(state.projectData);
  for (const selector of ["#delete-project-button", "#export-button", "#floating-search-button", "#manual-item-button", "#toggle-project-settings"]) $(selector).disabled = !available;
  $$("#project-settings-form input, #project-settings-form button, #smart-search-form input, #smart-search-form button").forEach((field) => { field.disabled = !available; });
  $("#empty-estimate-title").textContent = available ? "Your estimate is empty" : "Create a project to begin";
  $("#empty-estimate-description").textContent = available ? "Search above, or use the search button at the lower right to keep adding items." : "Use New project at the top. Your saved catalog is ready to reuse.";
  const data = state.projectData || {
    project: {}, lines: [], scope_summary: [], totals: { material:0, hours:0, labor:0, quoted:0 },
  };
  const { project, totals, lines } = data;
  $("#metric-material").textContent = fmtMoney(totals.material, project.currency);
  $("#metric-hours").textContent = `${fmtNumber(totals.hours)} hrs`;
  if(typeof updateEstimateExtras==='function')updateEstimateExtras(data);
  $("#metric-labour").textContent = fmtMoney(totals.labor, project.currency);
  $("#metric-quoted").textContent = fmtMoney(totals.quoted, project.currency);
  $("#estimate-line-count").textContent = `${lines.length} assembl${lines.length === 1 ? "y" : "ies"}`;
  $("#project-name").value = project.name || "";
  $("#project-builders").value = projectBuilders(project).join("\n");
  $("#project-currency").value = project.currency || "AUD";
  $("#project-hours-markup").value=Number(project.labor_hours_markup||0)*100;
  $("#project-material-markup").value = Number(project.material_markup || 0) * 100;
  $("#project-labour-rate").value = Number(project.labor_rate || 0);
  $("#project-overhead-markup").value = Number(project.overhead_markup || 0) * 100;
  $("#empty-estimate").classList.toggle("hidden", lines.length > 0);
  $('#delete-project-button').disabled = !available || !project.can_delete;
  renderGroupedEstimate(lines);
  renderEstimateBrief(project);
  $("#project-builders").disabled = !available || !project.can_manage;
  renderScopeBreakdown(data);
  if(typeof renderCollaboration==='function')renderCollaboration();
  if(project.id) refreshNoteBadge(project.id).catch(()=>{});
  if(available && !project.can_edit) {
    $$('#estimate-view input, #estimate-view textarea, #estimate-view select, #estimate-view button').forEach(field=>field.disabled=true);
    $$('#estimate-view [data-revisions], #estimate-view [data-project-brief], #estimate-view [data-project-notes], #estimate-view [data-refresh-estimate], #estimate-view .toggle-details, #estimate-view .toggle-scope, #toggle-all-categories, #find-estimate-button, #estimate-find-input, #estimate-view [data-copy-project], #toggle-project-settings').forEach(field=>field.disabled=false);
    $('#floating-search-button').disabled=true;
  }
}

function showCategorySuggestions(field,showAll=false){
  const query=field.value.trim().toLowerCase();
  const categories=[...new Set([...(state.dashboard?.manual_options?.categories||[]),...(state.catalogCategories||[]).map(c=>c.name),...(state.projectData?.lines||[]).map(estimateSectionName)].filter(Boolean))];
  const matches=categories.sort((a,b)=>{const am=!showAll&&query&&a.toLowerCase().includes(query),bm=!showAll&&query&&b.toLowerCase().includes(query);return Number(bm)-Number(am)||a.localeCompare(b);});
  const box=field.parentElement.querySelector('.category-suggestions');
  box.innerHTML=matches.map(c=>`<button class="category-choice" type="button" data-category="${escapeHtml(c)}">${escapeHtml(c)}</button>`).join('');
  box.classList.toggle('hidden',!matches.length);
}

function renderScopeBreakdown(data) {
  const summary = (state.summaryMode==='work'?data.work_summary:data.scope_summary) || [];
  function summaryRow(row,child=false){return `<tr class="${child?'scope-subcategory':''} ${row.included===false?'scope-summary-excluded':''}"><td>${escapeHtml(row.category)}${row.included===false&&!child?'<small class="scope-excluded-label">Optional cost</small>':''}</td><td>${child?'':row.assemblies}</td><td>${fmtMoney(row.material)}</td><td>${fmtNumber(row.hours)} hrs</td><td>${fmtMoney(row.labor)}</td><td><strong>${fmtMoney(row.quoted)}</strong></td></tr>`;}
  $('#scope-breakdown-rows').innerHTML=summary.length?summary.map(row=>summaryRow(row)+(row.subcategories||[]).map(child=>summaryRow(child,true)).join('')).join(''):'<tr><td colspan="6" class="scope-empty">Add estimate items to see the breakdown.</td></tr>';
  const totals = data.totals;
  $("#scope-breakdown-total").innerHTML = `<tr><td>${data.totals.included_line_count<data.lines.length?'TOTAL INCLUDED':'TOTAL'}</td><td>${data.totals.included_line_count??data.lines.length}</td><td>${fmtMoney(totals.material)}</td><td>${fmtNumber(totals.hours)} hrs</td><td>${fmtMoney(totals.labor)}</td><td>${fmtMoney(totals.quoted)}</td></tr>`;
}

async function deleteCurrentProject() {
  const current = state.projectData;
  if (!current) return;
  const id = current.project.id;
  if (!confirm(`Delete “${current.project.name}” and its ${current.lines.length} estimate lines? Catalog items will stay available.`)) return;
  $("#delete-project-button").disabled = true;
  $("#project-select").disabled = true;
  try {
    await api(`/api/projects/${id}`, { method: "DELETE", body: {} });
    state.projectId = null;
    state.projectData = null;
    hideSmartSuggestions();
    $("#search-results").classList.add("hidden");
    renderProject();
    await loadDashboard(false);
    toast("Project deleted");
  } finally {
    $("#delete-project-button").disabled = !state.projectData;
    $("#project-select").disabled = !state.projects.length;
  }
}

async function updateLineCategory(lineId, value) {
  const result = await api(`/api/projects/${state.projectId}/lines/${lineId}`, { method:"PATCH", body:{ category_snapshot:value.trim() || "Other" } });
  if(result.project.id!==state.projectId || Number(result.project.revision)<Number(state.projectData?.project?.revision))return;
  state.projectData = result;
  renderProject();
  toast("Category and scope breakdown updated");
}

function openQuickSearch() {
  if (!state.projectId) return;
  $("#quick-search-project").textContent = state.projectData.project.name;
  $("#quick-search-status").textContent = "";
  $("#quick-search-dialog").showModal();
  $("#quick-search-input").focus();
  runQuickSearch().catch((error) => { $("#quick-search-status").textContent = error.message; });
}

async function runQuickSearch(more=false) {
  clearTimeout(state.quickSearchTimer);
  const request = ++state.quickSearchRequest;
  const query = $("#quick-search-input").value.trim();
  const box = $("#quick-search-results");
  if (!query) { box.innerHTML = `<p class="helper-text">Type an item title to find it.</p>`; return; }
  const offset=more?box.querySelectorAll(".quick-search-result").length:0;
  if(!more)box.innerHTML = `<p class="helper-text">Searching…</p>`;
  const result = await api(`/api/catalog/search?q=${encodeURIComponent(query)}&limit=30&recent_first=1&offset=${offset}`);
  if (request !== state.quickSearchRequest) return;
  const html = result.results.length ? result.results.map((item) => `<article class="quick-search-result"><div><strong>${catalogName(item)}</strong><small>${escapeHtml(item.category)} · ${escapeHtml(workTypeLabel(item.pricing_work_type || item.work_type))} / ${escapeHtml(item.base_uom || "EA")}</small><small>Material ${fmtMoney(item.unit_material)} · Labour ${catalogLaborLabel(item)}</small></div><div>${ratingStamp(item)}<button class="button primary small quick-add" type="button" data-id="${item.id}" data-name="${escapeHtml(item.name)}" data-unit="${escapeHtml(item.base_uom || "EA")}">Add</button><button class="text-button quick-edit-add" type="button" data-id="${item.id}">Edit & add</button></div></article>`).join("") : `<p class="helper-text">No matching item. Try another search or add a manual item.</p>`;
  box.querySelector(".quick-search-more")?.remove();if(more)box.insertAdjacentHTML("beforeend",html);else box.innerHTML=html;
  if(result.has_more)box.insertAdjacentHTML("beforeend",`<button type="button" class="button secondary quick-search-more">Show more matches (${offset+result.results.length} of ${result.total})</button>`);
}

async function addQuickResult(button) {
  if (state.quickSearchAdding) return;
  if (!$("#quick-search-form").reportValidity()) return;
  const quantity = Number($("#quick-search-quantity").value);
  state.quickSearchAdding = true;
  button.disabled = true;
  try {
    await addCatalogItem(button.dataset.id, $("#quick-search-input").value, quantity);
    $("#quick-search-status").textContent = `Added ${fmtNumber(quantity)} ${button.dataset.unit} · ${button.dataset.name}`;
  } finally { state.quickSearchAdding = false; button.disabled = false; }
}

function renderEstimateLine(line) {
  const category = line.category_snapshot || "Other";
  const details = (estimateViewState.expanded.has(line.id) ? (line.components || []) : []).map((component) => `
    <tr class="detail-row hidden-row" data-parent="${line.id}" data-component-id="${component.id}">
      <td class="assembly-cell"><span class="drag-handle" draggable="true" data-drag-kind="component" data-line-id="${line.id}" data-component-id="${component.id}" title="Drag component">⠿</span><button class="component-copy-live" data-line-id="${line.id}" data-component-id="${component.id}" title="Copy component below" aria-label="Copy component">+</button>${componentLabel(component)}${component.fixed_quantity?'<small class="fixed-quantity-note">Fixed total quantity</small>':''}</td>
      <td>${fmtNumber(component.scaled_quantity)} ${escapeHtml(component.uom || "")}</td>
      <td>${component.is_supply_allowance?fmtMoney(component.unit_material):"—"}</td><td>${component.is_supply_allowance?"—":fmtMoney(component.unit_material)}</td>
      <td>${fmtMoney(component.total_material)}</td>
      <td>${componentLaborLabel(component)}</td>
      <td>${fmtNumber(component.total_hours)}</td>
      <td>${fmtMoney(component.total_labor)}</td>
      <td>${fmtMoney(component.grand_total)}</td>
      <td>—</td><td><button type="button" class="component-remove-live delete-line-component" data-line-id="${line.id}" data-component-id="${component.id}" aria-label="Remove component from this estimate" title="Remove from this estimate only">×</button></td>
    </tr>`).join("");
  return `
    <tr class="assembly-row" data-line-id="${line.id}">
      <td class="assembly-cell"><div class="assembly-title">
        <button class="toggle-details" data-line-id="${line.id}" aria-label="Expand component details" aria-expanded="false">+</button>
        <div class="assembly-copy">
          <div class="line-heading-grid">
            <div class="line-name-field"><div class="assembly-name-row"><span class="drag-handle" draggable="true" data-drag-kind="line" data-line-id="${line.id}" title="Drag item within this category">⠿</span><textarea class="line-estimate-name" data-line-id="${line.id}" rows="1" maxlength="500" aria-label="Estimate item name">${escapeHtml(line.display_name || cleanEstimateTitle(line.name_snapshot))}</textarea></div>
            ${['Lighting','Emergency & Exit Lighting'].includes(estimateSectionName(line))?`<label class="compact-light-reference"><span>Ref.</span><input class="line-light-reference" data-line-id="${line.id}" type="text" maxlength="120" value="${escapeHtml(line.reference_name||'')}" placeholder="Light ref." aria-label="Project-only light reference" title="Project-only lighting reference (for example D1 or EX1). Not saved to the shared catalogue."></label>`:''}<label class="line-remarks-field"><span>Remarks</span><textarea class="line-remarks" data-line-id="${line.id}" rows="1" maxlength="2000" placeholder="Add a note…" aria-label="Remarks for ${escapeHtml(line.name_snapshot)}">${escapeHtml(line.notes||'')}</textarea></label></div>
            <div class="line-category-field"><label class="line-category-label">Category<div class="category-editor" data-value="${escapeHtml(category)}"><textarea class="line-category" data-line-id="${line.id}" rows="1" maxlength="120" aria-label="Scope or category for ${escapeHtml(line.name_snapshot)}" title="Choose or type a category; saves when you leave this field">${escapeHtml(category)}</textarea><div class="category-suggestions hidden" aria-label="Suggested categories"></div></div></label>
            <div class="assembly-actions"><button class="text-button edit-estimate-line" data-line-id="${line.id}" title="Edit item and components">Edit item</button><button class="text-button copy-estimate-line" data-line-id="${line.id}">Copy item</button><span class="line-detail-count">${line.components.length} components</span></div></div>
          </div>
        </div></div></td>
      <td class="line-quantity-cell"><input class="line-quantity" data-line-id="${line.id}" type="number" min="0" step="any" value="${Number(line.quantity)}" aria-label="Estimate quantity"><small class="line-unit">${escapeHtml(line.uom || "EA")}</small>${line.has_supply_allowance?`<label class="compact-supply">Supply cost / unit<input class="line-supply-cost" data-line-id="${line.id}" type="number" min="0" step="any" value="${line.supply_unit_cost}" title="Supplier price for one fitting, before mark-ups. Saved only with this estimate."></label>`:''}</td>
      <td>${fmtMoney(line.unit_supply_material)}</td><td>${fmtMoney(line.unit_installation_material)}</td><td>${fmtMoney(line.total_material)}</td>
      <td>${catalogLaborLabel(line)}</td><td>${fmtNumber(line.total_hours)}</td>
      <td>${fmtMoney(line.total_labor)}</td><td>${fmtMoney(line.direct_total)}</td>
      <td class="money-positive">${fmtMoney(line.quoted_total)}</td>
      <td><button class="delete-line" data-line-id="${line.id}" aria-label="Remove line">×</button></td>
    </tr>${details}`;
}

let suggestionTimer;
let suggestionRequestId = 0;

function hideSmartSuggestions() {
  const box = $("#smart-search-suggestions");
  if (!box) return;
  box.classList.add("hidden");
  box.innerHTML = "";
  state.suggestions = [];
  state.suggestionIndex = -1;
  $("#smart-search-input")?.setAttribute("aria-expanded", "false");
}

function renderSmartSuggestions(items) {
  const box = $("#smart-search-suggestions");
  const input = $("#smart-search-input");
  state.suggestions = items;
  state.suggestionIndex = -1;
  if (!items.length) {
    box.innerHTML = `<div class="suggestion-empty">No close catalog suggestion yet. Keep typing or press Find.</div>`;
    box.classList.remove("hidden");
    input.setAttribute("aria-expanded", "true");
    return;
  }
  box.innerHTML = items.map((item, index) => `
    <button class="suggestion-item catalog-peek" type="button" role="option" aria-selected="false" data-index="${index}" data-catalog-preview="${item.id}">
      <span class="suggestion-copy"><strong>${catalogName(item)}</strong><small>${escapeHtml(item.category || "Other")} · ${escapeHtml(workTypeLabel(item.pricing_work_type || item.work_type))} / ${escapeHtml(item.base_uom || "EA")}</small></span>
      ${ratingStamp(item)}<span class="suggestion-meta"><em class="data-status ${escapeHtml(item.data_status)}">${(item.pricing_label || dataStatusLabel(item.data_status))}</em>${fmtMoney(item.unit_material)} · ${catalogLaborLabel(item)}</span>
    </button>`).join("");
  box.classList.remove("hidden");
  input.setAttribute("aria-expanded", "true");
}

function setSuggestionIndex(index) {
  const buttons = $$("#smart-search-suggestions .suggestion-item");
  if (!buttons.length) return;
  state.suggestionIndex = (index + buttons.length) % buttons.length;
  buttons.forEach((button, buttonIndex) => {
    const active = buttonIndex === state.suggestionIndex;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
    if (active) button.scrollIntoView({ block: "nearest" });
  });
}

let suggestionLoading=false,suggestionQuery="";
async function loadSmartSuggestions(more=false) {
  if(more&&suggestionLoading)return;
  const input = $("#smart-search-input");
  const text = input.value.trim();
  if (text.length < 2) {
    hideSmartSuggestions();
    return;
  }
  if(more&&suggestionQuery!==text)more=false;
  suggestionLoading=true;
  const requestId = ++suggestionRequestId;
  const query = text
    .replace(/\b(?:qty|quantity)\s*[:=]?\s*\d+(?:\.\d+)?\b/ig, " ")
    .replace(/^\s*\d+(?:\.\d+)?\s*[x×]\s*/i, "")
    .trim() || text;
  try {
    const result = await api(`/api/catalog/search?q=${encodeURIComponent(query)}&limit=30&recent_first=1&offset=${more?state.suggestions.length:0}`);
    if (requestId !== suggestionRequestId || input.value.trim() !== text) return;
    suggestionQuery=text;
    const box=$('#smart-search-suggestions'),scroll=box.scrollTop;
    renderSmartSuggestions(more?[...state.suggestions,...(result.results||[])]:result.results||[]);
    box.insertAdjacentHTML('afterbegin',`<div class="suggestion-count" role="status">${result.total} matching items · ${state.suggestions.length} shown${result.has_more?' · Scroll for more':''}</div>`);
    if(result.has_more)box.insertAdjacentHTML('beforeend',`<button type="button" class="suggestion-more button secondary">Show more matches (${state.suggestions.length} of ${result.total})</button>`);
    if(more)box.scrollTop=scroll;
  } catch (_) {
    if (requestId === suggestionRequestId) hideSmartSuggestions();
  } finally {if(requestId===suggestionRequestId)suggestionLoading=false;}
}

let smartResultVersion=0;
function clearSmartSearch() {
  smartResultVersion++;
  suggestionRequestId++;
  clearTimeout(suggestionTimer);
  state.activeSearchQuery='';
  const box=$('#search-results');
  box.innerHTML='';box.classList.add('hidden');
  hideSmartSuggestions();
}
function queueSmartSuggestions() {
  if (!$('#smart-search-input').value.trim()) {clearSmartSearch();return;}

  clearTimeout(suggestionTimer);
  suggestionTimer = setTimeout(() => loadSmartSuggestions(), 180);
}

async function chooseSmartSuggestion(index) {
  const item = state.suggestions[index];
  if (!item) return;
  const selectionVersion=++smartResultVersion;
  const original = $("#smart-search-input").value.trim();
  const quantity = typedQuantity(original);
  $("#smart-quantity").value = quantity;
  $("#smart-search-input").value = item.display_name || cleanEstimateTitle(item.name);
  hideSmartSuggestions();
  state.activeSearchQuery = original || item.name;
  const box = $("#search-results");
  box.classList.remove("hidden");
  box.innerHTML = "<p class='helper-text'>Opening the selected catalog…</p>";
  try {
    const detail = await fetchCatalogItem(item.id);
    if(selectionVersion!==smartResultVersion)return;
    renderSelectedCatalog(detail, state.activeSearchQuery);
  } catch (error) {
    if(selectionVersion!==smartResultVersion)return;
    box.innerHTML = `<p class="helper-text">${escapeHtml(error.message)}</p>`;
  }
}

function compactComponentTable(item, maxRows = 8) {
  const components = item.components || [];
  const rows = components.slice(0, maxRows).map((component) => `
    <tr><td>${componentLabel(component)}${component.fixed_quantity?'<small class="fixed-quantity-note">Fixed total quantity</small>':''}</td><td>${fmtNumber(component.quantity_per_unit, 4)} ${escapeHtml(component.uom || "")}</td><td>${fmtMoney(component.unit_material)}</td><td>${componentLaborLabel(component)}</td></tr>`).join("");
  const more = components.length > maxRows ? `<p class="preview-more">+ ${components.length - maxRows} more component rows</p>` : "";
  return `<div class="component-preview-wrap"><table class="component-preview-table"><thead><tr><th>Contained detail</th><th>Qty / 1</th><th>Unit material</th><th>Labour / unit</th></tr></thead><tbody>${rows}</tbody></table>${more}</div>`;
}

function renderSelectedCatalog(item, query) {
  const box = $("#search-results");
  const versions = Number(item.variant_count || 1);
  box.innerHTML = `
    <div class="selection-banner"><strong>Ready to add</strong><span>Check the quantity and allowances below.</span></div>
    <article class="search-result selected-result catalog-peek" data-catalog-preview="${item.id}">
      <div class="search-result-main"><div><h3>${catalogName(item)}</h3><p>${escapeHtml(item.category || "Other")} · ${escapeHtml(workTypeLabel(item.pricing_work_type || item.work_type))} / ${escapeHtml(item.base_uom || "EA")}</p><div class="result-tags"><span class="data-status ${escapeHtml(item.data_status)}">${(item.pricing_label || dataStatusLabel(item.data_status))}</span><span>${versions > 1 ? `${versions} source records` : "Saved item"}</span><span>${(item.components || []).length} components</span></div></div></div>
      <div class="result-cost">${ratingStamp(item)}<span>Material / unit<strong>${fmtMoney(item.unit_material)}</strong></span><span>Labour / unit<strong>${catalogLaborLabel(item)}</strong></span><button class="button secondary search-delete-item" type="button" data-id="${item.id}">Delete</button><button class="button secondary edit-add-result" data-id="${item.id}">Edit & add</button><button class="button primary add-result" data-id="${item.id}" data-query="${escapeHtml(query)}">Add to estimate</button></div>
    </article>
    ${compactComponentTable(item, 10)}
    ${versions > 1 ? `<div class="variant-callout"><span>${versions} source records are available for this item. Identical allowances appear once.</span><button class="text-button compare-variants" data-id="${item.id}" data-query="${escapeHtml(item.name)}">View details</button></div>` : ""}`;
}

async function runSmartSearch() {
  const text = $("#smart-search-input").value.trim();
  if (!text) {clearSmartSearch();return;}
  const requestVersion=++smartResultVersion;
  state.activeSearchQuery = text;
  hideSmartSuggestions();
  const box = $("#search-results");
  box.classList.remove("hidden");
  box.innerHTML = "<p class='helper-text'>Searching item titles…</p>";
  try {
    const result = await api("/api/assistant/interpret", { method: "POST", body: { text } });
    if(requestVersion!==smartResultVersion)return;
    $("#smart-quantity").value = result.quantity;
    renderSearchResults(result);
  } catch (error) {
    if(requestVersion!==smartResultVersion)return;
    box.innerHTML = `<p class="helper-text">${escapeHtml(error.message)}</p>`;
  }
}

function renderSearchResults(result) {
  const box = $("#search-results");
  if (!result.candidates.length) {
    box.innerHTML = `<div class="empty-state"><h3>No reliable catalog match</h3><p>Try a product name, size or shorter description, or create a manual item.</p></div>`;
    return;
  }
  const methodLabel = result.method === "gemini_rerank" ? " Gemini reranked the local matches." : result.method === "local_free_quota" ? " Gemini free quota is exhausted, so local ranking was used." : result.method === "local_fallback" ? " Gemini was unavailable, so local ranking was used." : " Local catalog ranking was used.";
  box.innerHTML = `<p class="helper-text">Interpreted as <strong>${escapeHtml(result.query)}</strong>, quantity <strong>${fmtNumber(result.quantity)}</strong>. Match confidence: ${escapeHtml(result.confidence)}.${methodLabel} Select an item to review its components.</p>` + result.candidates.map((item, index) => `
    <article class="search-result catalog-peek" data-catalog-preview="${item.id}">
      <div class="search-result-main"><div><h3>${catalogName(item)}${index === 0 ? ` <em class="recommended-tag">Recommended</em>` : ""}</h3><p>${escapeHtml(item.category || "Other")} · ${escapeHtml(workTypeLabel(item.pricing_work_type || item.work_type))} / ${escapeHtml(item.base_uom || "EA")}</p><div class="result-tags"><span class="data-status ${escapeHtml(item.data_status)}">${(item.pricing_label || dataStatusLabel(item.data_status))}</span><span>${variantText(item)}</span><span>${Number(item.component_count || 0)} components</span></div></div></div>
      <div class="result-cost">${ratingStamp(item)}<span>Material / unit<strong>${fmtMoney(item.unit_material)}</strong></span><span>Labour / unit<strong>${catalogLaborLabel(item)}</strong></span>${Number(item.variant_count || 1) > 1 ? `<button class="button tertiary small compare-variants" data-id="${item.id}" data-query="${escapeHtml(item.name)}">Versions</button>` : ""}<button class="button secondary search-delete-item" type="button" data-id="${item.id}">Delete</button><button class="button secondary edit-add-result" data-id="${item.id}">Edit & add</button><button class="button primary add-result" data-id="${item.id}" data-query="${escapeHtml(result.original)}">Add</button></div>
    </article>`).join("");
}

async function addCatalogItem(itemId, query = "", quantity = null) {
  if (!state.projectId) throw new Error("Create a project first");
  const qty = quantity ?? Number($("#smart-quantity").value || 1);
  const result = await api(`/api/projects/${state.projectId}/lines`, {
    method: "POST",
    body: { catalog_item_id: Number(itemId), quantity: qty, query },
  });
  if(result.project.id!==state.projectId || Number(result.project.revision)<Number(state.projectData?.project?.revision))return;
  state.projectData = result;
  renderProject();
  $("#search-results").classList.add("hidden");
  $("#smart-quantity").value="1";
  $("#quick-search-quantity").value="1";
  toast("Assembly added with all component rows");
}

async function updateLineQuantity(lineId, value) {
  const quantity = Number(value);
  if (!Number.isFinite(quantity) || quantity < 0) { toast("Quantity must be zero or greater", true); renderProject(); return; }
  const result = await api(`/api/projects/${state.projectId}/lines/${lineId}`, { method: "PATCH", body: { quantity } });
  if(result.project.id!==state.projectId || Number(result.project.revision)<Number(state.projectData?.project?.revision))return;
  state.projectData = result;
  renderProject();
}

async function removeLine(lineId) {
  const result = await api(`/api/projects/${state.projectId}/lines/${lineId}`, { method: "DELETE", body: {} });
  if(result.project.id!==state.projectId || Number(result.project.revision)<Number(state.projectData?.project?.revision))return;
  state.projectData = result;
  renderProject();
  toast("Assembly removed");
}

let projectSettingsTimer=null,projectSettingsBusy=false,projectSettingsQueued=false,projectSettingsOwner=null;
function queueProjectSettings(){
 if(!state.projectData?.project.can_edit)return;
 projectSettingsOwner=state.projectId;projectSettingsQueued=true;
 $('#project-autosave-status').textContent='Unsaved changes…';
 clearTimeout(projectSettingsTimer);projectSettingsTimer=setTimeout(()=>saveProjectSettings().catch(()=>{}),450);
}
async function saveProjectSettings(event) {
 event?.preventDefault();clearTimeout(projectSettingsTimer);
 if(projectSettingsBusy){projectSettingsQueued=true;return;}
 if(!state.projectId||!state.projectData?.project.can_edit)return;
 if(projectSettingsOwner&&projectSettingsOwner!==state.projectId){projectSettingsQueued=false;projectSettingsOwner=null;return;}
 if(!$('#project-settings-form').checkValidity()){$('#project-autosave-status').textContent='Enter valid values to save';return;}
 const pid=state.projectId;
  const payload = {
    name: $("#project-name").value,
    currency: $("#project-currency").value,
    labor_hours_markup: Number($("#project-hours-markup").value || 0) / 100,
    material_markup: Number($("#project-material-markup").value || 0) / 100,
    labor_rate: Number($("#project-labour-rate").value || 0),
    overhead_markup: Number($("#project-overhead-markup").value || 0) / 100,
    hours_per_day: Number($("#project-hours-per-day").value || 8),
    crew_size: Number($("#project-crew-size").value || 2),
  };
  if (state.projectData?.project.can_manage) payload.builders = $("#project-builders").value.split(/\r?\n/);

 payload.expected_revision=state.projectData.project.revision;
 projectSettingsBusy=true;projectSettingsQueued=false;
 $('#project-autosave-status').textContent='Saving…';
 try{
  const result=await api(`/api/projects/${pid}`,{method:'PATCH',body:payload});
  if(state.projectId!==pid)return;
  const draft=Object.fromEntries([...$('#project-settings-form').querySelectorAll('input,textarea')].map(f=>[f.id,f.value]));
  state.projectData=result;renderProject();
  if(projectSettingsQueued){for(const [id,value] of Object.entries(draft))$('#'+id).value=value;}
  const i=state.projects.findIndex(p=>p.id===pid);if(i>=0)state.projects[i]={...state.projects[i],...result.project,totals:result.totals};
  $('#project-autosave-status').textContent=projectSettingsQueued?'Saving latest changes…':'Saved · totals updated';
 }catch(error){projectSettingsQueued=false;$('#project-autosave-status').textContent='Not saved — '+error.message;toast(error.message,true);}
 finally{projectSettingsBusy=false;if(projectSettingsQueued&&state.projectId===pid)saveProjectSettings().catch(()=>{});}
}

let projectCopySource=null;
function openProjectForm(source=null){
  projectCopySource=source;
  $('#new-project-form').reset();
  $('#copy-zero-label').classList.toggle('hidden',!source);
  $('#new-project-name').value=source?`${source.name} — Copy`:'';
  $('#new-project-scope').value=source?.scope_of_work||'';
  renderBuilderEditor('new-project-builders',source?projectBuilders(source):[]);
  $('#new-project-deadline').min=localDateKey();
  $('#new-project-deadline').value='';
  $('#project-form-title').textContent=source?'Copy Estimate':'Create Estimate';
  $('#project-form-submit').textContent=source?'Create copy':'Create project';
  $('#project-dialog').showModal();
}
async function createNewProject(event) {
  event.preventDefault();
  const settings = state.appSettings || await loadSettings(false);
  const payload = {
    name: $("#new-project-name").value,
    builders: readBuilderEditor("new-project-builders"),
    scope_of_work: $('#new-project-scope').value,
    submission_deadline: $('#new-project-deadline').value,
    labor_hours_markup: Number(settings.default_labor_hours_markup || 0),
    currency: settings.currency || "AUD",
    material_markup: Number(settings.default_material_markup || .15),
    labor_rate: Number(settings.default_labor_rate || 120),
    crew_size: Number(settings.default_crew_size || 2),
    hours_per_day: Number(settings.default_hours_per_day || 8),
    overhead_markup: Number(settings.default_overhead_markup || .10),
  };
  const source=projectCopySource;
  const result = await api(source?`/api/projects/${source.id}/copy`:"/api/projects", { method: "POST", body: source?{
    name:payload.name,builders:payload.builders,scope_of_work:payload.scope_of_work,
    submission_deadline:payload.submission_deadline,expected_revision:source.revision,zero_quantities:$("#copy-zero-quantities").checked
  }:payload });
  projectCopySource=null;
  state.projectId = result.project.id;
  $("#project-dialog").close();
  $("#new-project-form").reset();
  renderBuilderEditor("new-project-builders", []);
  await loadDashboard(false);
  state.projectData=result;renderProject();
  setView('estimate', false);
  if(source){toast('Project copied');return;}
  toast(state.user.role==='user' && state.user.team_id ? "Project created and shared with your team" : "New estimate created");
}

function workTypeLabel(value) {
  return state.dashboard?.manual_options?.work_types?.[value] || "Existing / custom assembly";
}

function componentLaborLabel(component) {
  return component.labor_pricing === "fixed"
    ? `${fmtMoney(component.unit_labor_price)} fixed`
    : `${fmtNumber(component.unit_hours, 3)} hrs`;
}

function catalogLaborLabel(item) {
  const parts = [];
  if (Number(item.unit_hours)) parts.push(`${fmtNumber(item.unit_hours)} hrs`);
  if (Number(item.unit_labor_price)) parts.push(`${fmtMoney(item.unit_labor_price)} fixed`);
  return parts.join(" + ") || "0.00 hrs";
}

function componentRow(component = {}) {
  const mode = component.labor_pricing || "hours";
  return `<tr class="manual-component" data-component="${escapeHtml(JSON.stringify(component))}" data-labor-mode="${escapeHtml(mode)}">
    <td data-label="Description"><div class="component-row-tools"><label class="fixed-quantity-control" title="Restore original database quantity and keep it independent of the assembly quantity"><input type="checkbox" class="component-fixed-quantity"${component.fixed_quantity?' checked':''}> Fixed total</label><span class="drag-handle" draggable="true" data-drag-kind="manual" title="Drag component">⠿</span><button class="clipboard-component" type="button" title="Copy component to paste into another item" aria-label="Copy component to clipboard"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4H4v12h4"/></svg><span>Copy</span></button><button class="copy-manual-component" type="button" title="Copy component below" aria-label="Copy component">+</button></div><input class="component-description" aria-label="Detail description" required value="${escapeHtml(component.description || "")}" placeholder="Product, material or work description">
      <details class="component-extra"><summary>Specifications, factors & notes</summary><div>

        <label>Material factor<input class="component-material-factor" type="number" min="0" step="any" required value="${Number(component.material_factor ?? 1)}"></label>
        <label>Labour factor<input class="component-labor-factor" type="number" min="0" step="any" required value="${Number(component.labor_factor ?? 1)}"></label>
        <label>Notes<input class="component-notes" value="${escapeHtml(component.notes || "")}"></label>
      </div></details></td>
    <td data-label="Size / specification"><input class="component-size" aria-label="Component size or specification" value="${escapeHtml(component.size || '')}" placeholder="e.g. 1200mm"></td>
    <td data-label="Qty / 1"><input class="component-ratio" aria-label="Quantity per item" type="number" min="0" step="any" required value="${Number(component.quantity_per_unit ?? 1)}"></td>
    <td data-label="Unit"><input class="component-uom" aria-label="Detail unit" list="unit-options" required value="${escapeHtml(component.uom || "EA")}"></td>
    <td data-label="Product / material"><input class="component-material" aria-label="Unit product or material price" type="number" min="0" step="any" required value="${Number(component.unit_material || 0)}"></td>
    <td data-label="Labour basis"><select class="component-labor-mode" aria-label="Labour pricing basis"><option value="hours"${mode === "hours" ? " selected" : ""}>Hours</option><option value="fixed"${mode === "fixed" ? " selected" : ""}>Fixed price</option></select></td>
    <td data-label="Labour hrs / price"><input class="component-labor-value" aria-label="${mode === "fixed" ? "Unit labour price" : "Unit labour hours"}" type="number" min="0" step="any" required value="${Number(mode === "fixed" ? component.unit_labor_price || 0 : component.unit_hours || 0)}"><small class="component-labor-label">${mode === "fixed" ? "Price / unit" : "Hours / unit"}</small></td>
    <td data-label="Remove"><button class="remove-component" type="button" aria-label="Remove detail">×</button></td>
  </tr>`;
}

function readManualComponents(selectedRow = null) {
  const workType = $("#manual-work-type").value;
  return (selectedRow ? [selectedRow] : $$("#manual-components .manual-component")).map((row, index) => {
    const original = JSON.parse(row.dataset.component || "{}");
    const mode = $(".component-labor-mode", row).value;
    const value = workType === "supply_only" ? 0 : Number($(".component-labor-value", row).value || 0);
    return {
      ...original,
      description: $(".component-description", row).value.trim(),
      item_no: original.item_no || "",
      size: $(".component-size", row).value.trim(),
      notes: $(".component-notes", row).value,
      quantity_per_unit: Number($(".component-ratio", row).value),
      fixed_quantity: $(".component-fixed-quantity", row).checked ? 1 : 0,
      source_quantity: original.source_quantity ?? original.quantity_per_unit ?? Number($(".component-ratio", row).value),
      uom: $(".component-uom", row).value.trim(),
      unit_material: workType === "installation_only" ? 0 : Number($(".component-material", row).value),
      material_factor: Number($(".component-material-factor", row).value),
      labor_factor: Number($(".component-labor-factor", row).value),
      labor_pricing: mode,
      unit_hours: mode === "hours" ? value : 0,
      unit_labor_price: mode === "fixed" ? value : 0,
      is_parent: original.is_parent ?? index === 0,
    };
  });
}

function manualMarkupOptions(){return {exclude_material_markup:state.manualAddToEstimate&&$('#manual-exclude-material').checked,exclude_hours_markup:state.manualAddToEstimate&&$('#manual-exclude-hours').checked,exclude_final_markup:state.manualAddToEstimate&&$('#manual-exclude-final').checked};}
function refreshManualPricing() {
  const workType = $("#manual-work-type").value;
  const help = {
    assembly: "Keep the existing component allowances, or enter a custom build-up.",
    supply_install: "Enter product supply prices and installation labour separately. Both are included in the item total.",
    supply_only: "Product or lighting supply prices only. Labour is excluded when saved.",
    installation_only: "Installation labour only. Product and material supply prices are excluded when saved.",
    relocation: "Enter relocation labour and any additional materials or consumables required.",
    demolition: "Enter demolition labour and any additional disposal or material costs required.",
  };
  $("#manual-work-help").textContent = help[workType] || "";
  const rows = $$("#manual-components .manual-component");
  rows.forEach((row) => {
    $(".component-material", row).disabled = workType === "installation_only";
    $(".component-material-factor", row).disabled = workType === "installation_only";
    for (const field of [".component-labor-mode", ".component-labor-value", ".component-labor-factor"]) {
      $(field, row).disabled = workType === "supply_only";
    }
    $(".remove-component", row).disabled = rows.length === 1;
  });
  const components = readManualComponents();
  const material = components.reduce((sum, c) => sum + c.quantity_per_unit * c.unit_material * c.material_factor, 0);
  const hours = components.reduce((sum, c) => sum + c.quantity_per_unit * c.unit_hours * c.labor_factor, 0);
  const fixed = components.reduce((sum, c) => sum + c.quantity_per_unit * c.unit_labor_price * c.labor_factor, 0);
  const project = state.projectData?.project;
  const rate = Number(project?.labor_rate ?? state.appSettings?.default_labor_rate ?? 120);
  const exclusions=manualMarkupOptions();
  const hoursFactor=1+(exclusions.exclude_hours_markup?0:Number(project?.labor_hours_markup??state.appSettings?.default_labor_hours_markup??0));
  const markup = exclusions.exclude_material_markup?0:Number(project?.material_markup ?? state.appSettings?.default_material_markup ?? .15);
  const overhead = exclusions.exclude_final_markup?0:Number(project?.overhead_markup ?? state.appSettings?.default_overhead_markup ?? .10);
  const qty = Number($("#manual-quantity").value);
  const estimateTotal=components.reduce((sum,c)=>{
    const quantity=c.quantity_per_unit*(c.fixed_quantity?1:qty);
    return sum+quantity*(c.unit_material*c.material_factor*(1+markup)+(c.unit_hours*hoursFactor*rate+c.unit_labor_price)*c.labor_factor)*(1+overhead);
  },0);
  const quotedUnit = (material * (1 + markup) + hours * hoursFactor * rate + fixed) * (1 + overhead);
  const unit = escapeHtml($("#manual-uom").value || "unit");
  $("#manual-cost-preview").innerHTML = `<span>Base material / ${unit}<strong>${fmtMoney(material)}</strong></span><span>Labour / ${unit}<strong>${fmtNumber(hours)} hrs + ${fmtMoney(fixed)} fixed</strong></span><span>Quoted price / ${unit}<strong>${fmtMoney(quotedUnit)}</strong></span>${state.manualAddToEstimate ? `<span>Estimate total · ${fmtNumber(qty)} ${unit}<strong>${fmtMoney(estimateTotal)}</strong></span>` : ""}<small>Preview uses ${fmtMoney(rate)}/hr, ${fmtNumber(markup * 100)}% material, ${fmtNumber((hoursFactor-1)*100)}% labour hours and ${fmtNumber(overhead * 100)}% final mark-up. ${state.manualAddToEstimate ? "Lighting fitting supply prices are saved only with this estimate." : "Existing estimates retain their saved prices."}</small>`;
}

function ratingStamp(item){const value=Math.max(0,Math.min(5,Number(item?.importance_rating)||0));return `<span class="rating-stamp" data-rating-item="${Number(item?.id)||0}" role="img" aria-label="${value?value+' out of 5 importance stars':'Not starred'}" title="${value?value+' out of 5 importance stars':'Not starred'}">${value?'★'.repeat(value):''}</span>`;}
function renderManualRating(){
 const value=state.manualRating||0;
 $('#manual-rating').innerHTML=`<small>Importance · optional</small><div class="rating-buttons" role="group" aria-label="Importance stars">${[1,2,3,4,5].map(n=>`<button type="button" data-rating="${n}" aria-label="${n} star${n===1?'':'s'}" aria-pressed="${value===n}" class="rating-star ${n<=value?'is-filled':''}" ${state.ratingBusy?'disabled':''}>${n<=value?'★':'☆'}</button>`).join('')}<button class="rating-clear" type="button" data-rating="0" aria-label="Clear stars" title="Clear stars" ${!value||state.ratingBusy?'disabled':''}>×</button></div><small class="rating-note" aria-live="polite">${state.ratingBusy?'Saving…':state.ratingItemId?'Shared catalogue rating · saved separately':'Saved with the new item'}</small>`;
}
async function changeManualRating(value){
 if(state.ratingBusy)return;
 const original=state.manualRating,itemId=state.ratingItemId,token=state.ratingDialogToken;
 state.manualRating=value;
 if(!itemId){renderManualRating();return;}
 state.ratingBusy=true;renderManualRating();
 try{
  await api(`/api/catalog/${itemId}/rating`,{method:'POST',body:{importance_rating:value}});
  state.catalogCache.clear();
  if(state.currentCatalogItem?.id===itemId)state.currentCatalogItem.importance_rating=value;
  for(const item of state.suggestions||[])if(item.id===itemId)item.importance_rating=value;
  $$(`[data-rating-item="${itemId}"]`).forEach(el=>{el.outerHTML=ratingStamp({id:itemId,importance_rating:value});});
 }catch(error){if(state.ratingDialogToken===token)state.manualRating=original;toast(error.message,true);}
 finally{if(state.ratingDialogToken===token){state.ratingBusy=false;renderManualRating();}}
}
function openManualDialog(addToEstimate = false, sourceItem = null, editExisting = false, lineId = null, quantityOverride = null) {
  if (!state.dashboard?.manual_options) { toast("Catalog is still loading. Please try again.", true); return; }
  state.manualAddToEstimate = addToEstimate;
  state.manualEditId = editExisting && sourceItem?.id ? sourceItem.id : null;
  state.manualLineId = lineId;
  state.manualLineRevision = state.projectData?.lines.find(l=>l.id===lineId)?.revision;
  state.manualProjectId = state.projectId;
  state.manualSource = sourceItem || {};
  state.ratingItemId=(editExisting||addToEstimate)?sourceItem?.id:null;
  const ratingToken=state.ratingDialogToken=(state.ratingDialogToken||0)+1;
  state.manualRating=Number(sourceItem?.importance_rating)||0;state.ratingBusy=false;renderManualRating();
  if(sourceItem?.id){state.ratingBusy=true;renderManualRating();fetchCatalogItem(sourceItem.id).then(item=>{if(state.ratingDialogToken===ratingToken){state.manualRating=item.importance_rating||0;state.ratingBusy=false;renderManualRating();}}).catch(error=>{if(state.ratingDialogToken===ratingToken){state.ratingBusy=false;renderManualRating();}toast(error.message,true);});}
  state.manualSaving = false;
  $("#manual-save-error").classList.add("hidden");
  $("#manual-item-form").reset();
  $('#manual-markup-options').classList.toggle('hidden',!addToEstimate);
  for(const [control,key] of [['material','exclude_material_markup'],['hours','exclude_hours_markup'],['final','exclude_final_markup']])$('#manual-exclude-'+control).checked=!!sourceItem?.[key];
  const options = state.dashboard.manual_options;
  $("#manual-category").value = sourceItem?.category_override || sourceItem?.category || "Lighting";
  $("#manual-work-type").innerHTML = Object.entries(options.work_types).map(([value, label]) => `<option value="${value}">${escapeHtml(label)}</option>`).join("");
  $("#manual-work-type").value = sourceItem?.work_type || "supply_install";
  $("#manual-name").value = sourceItem?.display_name || cleanEstimateTitle(sourceItem?.name || "");
  $('#manual-assembly-size').value=sourceItem?.assembly_size || '';
  $('#manual-save-mode-label').classList.toggle('hidden',!addToEstimate||!sourceItem);
  $('#manual-save-mode').innerHTML=(sourceItem?'<option value="estimate">Save this estimate only</option>':'')+(sourceItem?.id?'<option value="update">Update existing catalog item</option>':'')+'<option value="new">Save as a new catalog item</option>';
  $('#manual-save-mode').value=defaultSaveMode(addToEstimate, sourceItem);
  $("#manual-description").value = sourceItem?.description || "";
  $("#manual-uom").value = sourceItem?.base_uom || "EA";
  state.manualBaseUom = $("#manual-uom").value;
  $("#manual-quantity-label").classList.toggle("hidden", !addToEstimate);
  $("#manual-quantity").disabled = !addToEstimate;
  $("#manual-quantity").value = quantityOverride ?? sourceItem?.estimate_quantity ?? Number($("#smart-quantity").value || 1);
  const components = sourceItem?.components?.length ? sourceItem.components : [{ description: sourceItem?.name || "", quantity_per_unit: 1, uom: $("#manual-uom").value, unit_material: 0, unit_hours: 0, is_parent:1 }];
  $("#manual-components").innerHTML = components.map(componentRow).join("");
  if (!sourceItem) $("#manual-components .manual-component").dataset.autoDescription = "1";
  $("#manual-title").textContent = lineId ? "Edit estimate item" : state.manualEditId ? "Edit saved catalog item" : sourceItem ? "Edit item" : "Add manual catalog item";
  $("#manual-save-button").textContent = lineId ? "Save changes" : addToEstimate ? (sourceItem ? "Save & add to estimate" : "Save to catalog & add to estimate") : state.manualEditId ? "Save catalog changes" : "Save to catalog";
  $("#manual-save-button").disabled = false;
  $("#manual-save-note").textContent = lineId
    ? "Choose to save only this estimate, update the original catalog item or create a new item. Lighting fitting prices stay in this estimate."
    : state.manualEditId ? "Updates this catalog item for future use. Existing estimates keep their saved allowances."
    : addToEstimate ? "New items are reusable. Lighting fitting supply prices stay only in this project." : "Saves this item, its name, units and base prices for future estimates.";
  refreshManualPricing();
  $("#manual-dialog").showModal();
}

function openEstimateLineEditor(lineId) {
  const line = state.projectData?.lines.find((item) => Number(item.id) === Number(lineId));
  if (!line) return;
  openManualDialog(true, {
    id: line.catalog_item_id, code: line.code_snapshot, name: line.name_snapshot, description: line.description_snapshot,
    phase: line.scope_snapshot, scope: line.scope_snapshot, category: line.category_snapshot,
    work_type: line.work_type_snapshot, base_uom: line.uom, components: line.components, assembly_size:line.size_snapshot,
    estimate_quantity: line.quantity, exclude_material_markup:line.exclude_material_markup, exclude_hours_markup:line.exclude_hours_markup, exclude_final_markup:line.exclude_final_markup,
  }, false, line.id);
}

function showManualSaveError(error){
  const box=$('#manual-save-error');box.textContent=error.message||'Unable to save. Please try again.';box.classList.remove('hidden');box.scrollIntoView({block:'nearest'});box.focus();
}
async function saveManualItem(event) {
  event.preventDefault();
  if (state.manualSaving) return;
  $("#manual-save-error").classList.add("hidden");
  const form = $("#manual-item-form");
  if (!form.reportValidity()) return;
  const payload = {
    importance_rating:state.manualRating||0, assembly_size:$("#manual-assembly-size").value.trim(), code: state.manualSource.code || "", name: $("#manual-name").value.trim(),
    description: $("#manual-description").value.trim() || $("#manual-name").value.trim(),
    phase: state.manualSource.phase || "Manual items", subphase: state.manualSource.subphase || "",
    scope: state.manualSource.scope || $("#manual-category").value,
    base_uom: $("#manual-uom").value.trim(), category_override: $("#manual-category").value,
    work_type: $("#manual-work-type").value, components: readManualComponents(),
    supplier: $("#manual-supplier").value, quote_date: $("#manual-quote-date").value, source: $("#manual-price-source").value, source_item_id: state.manualSource.id || null,
  };
  if (!payload.name || !payload.base_uom || payload.components.some((c) => !c.description || !c.uom)) {
    throw new Error("Enter an item name, descriptions and units.");
  }
  state.manualSaving = true;
  const button = $("#manual-save-button");
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = "Saving…";
  let result;
  try {
    if (state.manualAddToEstimate) {
      const path = state.manualLineId
        ? `/api/projects/${state.manualProjectId}/lines/${state.manualLineId}/manual-item`
        : `/api/projects/${state.manualProjectId}/manual-items`;
      result = await api(path, { method: "POST", body: { ...manualMarkupOptions(), save_mode:$("#manual-save-mode").value || "new", item: payload, quantity: Number($("#manual-quantity").value), ...(state.manualLineId ? {expected_revision:state.manualLineRevision}: {}) } });
      if(result.project.id===state.projectId && Number(result.project.revision)>=Number(state.projectData?.project?.revision||0))state.projectData = result;
    } else {
      const path = state.manualEditId ? `/api/catalog/${state.manualEditId}` : "/api/catalog";
      result = await api(path, { method: state.manualEditId ? "PUT" : "POST", body: payload });
    }
  } finally {
    state.manualSaving = false;
    button.disabled = false;
    button.textContent = originalLabel;
  }
  $("#manual-dialog").close();
  if(state.manualAddToEstimate&&!state.manualLineId){$("#smart-quantity").value="1";$("#quick-search-quantity").value="1";}
  toast(state.manualLineId ? "Estimate saved" : state.manualAddToEstimate ? "Estimate changes saved" : "Catalog changes saved for future use");
  // A rendering/refresh failure must not turn a successful write into a retry.
  try {
    state.catalogCache.clear();hideSmartSuggestions();hideCatalogHover(0);
    if(state.manualAddToEstimate){renderProject();$("#search-results").classList.add("hidden");}
    if (!state.manualAddToEstimate) await loadDashboard(false);
    if (!state.manualAddToEstimate) {
      $("#catalog-category").value = "";
      $("#catalog-search-input").value = result.item.display_name || cleanEstimateTitle(result.item.name);
      await loadCatalog();
      await showCatalogDetail(result.item.id);
    }
  } catch (_) { toast("Saved successfully. Refresh the page to reload the catalog."); }
}

let catalogSearchTimer, catalogSearchRequest=0;
async function loadCatalog(query = null,more=false) {
  const offset=more?$("#catalog-results").querySelectorAll(".catalog-result").length:0;
  const request=++catalogSearchRequest;
  const term = query ?? $("#catalog-search-input").value.trim();
  const category = $("#catalog-category")?.value || "";
  const includeIncomplete = "0";
  const result = await api(`/api/catalog/search?q=${encodeURIComponent(term)}&category=${encodeURIComponent(category)}&include_incomplete=${includeIncomplete}&limit=60&offset=${offset}`);
  if(request!==catalogSearchRequest)return;
  const box = $("#catalog-results");
  if (!result.results.length) {
    if(more){box.querySelector(".catalog-search-more")?.remove();return;}
    box.innerHTML = `<div class="empty-state"><p>No catalog results found.</p></div>`;
    return;
  }
  const html = result.results.map((item) => `<a href="#/catalog/${item.id}" class="catalog-result catalog-peek" data-id="${item.id}" data-catalog-preview="${item.id}"><span><strong>${catalogName(item)}</strong><small>${escapeHtml(item.category || "Other")} · ${escapeHtml(workTypeLabel(item.pricing_work_type || item.work_type))} / ${escapeHtml(item.base_uom || "EA")}<br>${variantText(item)} · ${Number(item.component_count || 0)} detail rows</small></span><span class="catalog-result-meta">${ratingStamp(item)}<em class="data-status ${escapeHtml(item.data_status)}">${(item.pricing_label || dataStatusLabel(item.data_status))}</em></span></a>`).join("");
  box.querySelector(".catalog-search-more")?.remove();if(more)box.insertAdjacentHTML("beforeend",html);else box.innerHTML=html;
  if(result.has_more)box.insertAdjacentHTML("beforeend",`<button type="button" class="button secondary catalog-search-more">Show more matches (${offset+result.results.length} of ${result.total})</button>`);
}

async function deleteCurrentCatalog(){
  const item=state.currentCatalogItem;
  if(!item || !confirm(`Delete "${item.name}" from the catalog? Only this saved version is deleted. Existing estimates and revisions keep their saved items and prices.`))return;
  await api(`/api/catalog/${item.id}`,{method:'DELETE',body:{}});
  state.catalogCache.clear();state.currentCatalogItem=null;
  if(typeof rememberPage==='function')rememberPage('catalog',null,true);
  $('#catalog-detail').innerHTML='<p class="helper-text">Item deleted. Select another catalogue item to review.</p>';
  $('#catalog-detail').classList.add('empty-detail');
  clearSmartSearch();await loadCatalog();toast('Catalog item deleted. Saved estimates are preserved.');
}

async function showCatalogDetail(itemId) {
  const request=state.catalogDetailRequest=(state.catalogDetailRequest||0)+1;
  const item = await fetchCatalogItem(itemId);
  if(request!==state.catalogDetailRequest)return false;
  state.currentCatalogItem = item;
  $$(".catalog-result").forEach((row) => row.classList.toggle("active", Number(row.dataset.id) === Number(itemId)));
  const componentRows = item.components.map((component) => `<tr><td>${componentLabel(component)}${component.fixed_quantity?'<small class="fixed-quantity-note">Fixed total quantity</small>':''}</td><td>${fmtNumber(component.quantity_per_unit, 4)}</td><td>${escapeHtml(component.uom || "")}</td><td>${fmtMoney(component.unit_material)}</td><td>${componentLaborLabel(component)}</td></tr>`).join("");
  const sources = item.occurrences.length ? item.occurrences.map((source) => `<span class="source-chip">${escapeHtml(source.project_name || source.file_name)} · ${escapeHtml(source.sheet_name || "")} · row ${source.source_row || "—"}</span>`).join("") : `<span class="source-chip">Manual catalog</span>`;
  const variants = (item.variants || []).map((variant) => `<a href="#/catalog/${variant.id}" class="variant-option${Number(variant.id) === Number(item.id) ? " active" : ""}" data-variant-id="${variant.id}"><span><strong>${escapeHtml(variant.specification || variant.name || "Saved option")}</strong><small>${escapeHtml(variant.source_file || "Manual catalog")} · ${variant.component_count} rows</small></span><span><b>${fmtMoney(variant.unit_material)}</b><small>${catalogLaborLabel(variant)}</small></span><em class="data-status ${escapeHtml(variant.data_status)}">${dataStatusLabel(variant.data_status)}</em></a>`).join("");
  $("#catalog-detail").classList.remove("empty-detail");
  $("#catalog-detail").innerHTML = `
    <div class="detail-header"><div><h3>${catalogName(item)}</h3><p>${escapeHtml(item.category || "Other")} · ${escapeHtml(workTypeLabel(item.pricing_work_type || item.work_type))} / ${escapeHtml(item.base_uom || "EA")}</p><div class="result-tags"><span class="data-status ${escapeHtml(item.data_status)}">${(item.pricing_label || dataStatusLabel(item.data_status))}</span><span>${(item.components || []).length} components</span><span>${variantText(item)}</span></div></div><div><button class="button primary small detail-add" data-id="${item.id}">Add to estimate</button> <button class="button secondary small detail-edit">Edit catalog item</button> <button class="button secondary small detail-clone">${item.is_manual ? "Save as new version" : "Create editable version"}</button><div class="detail-rating">${ratingStamp(item)}</div></div></div>
    <div class="detail-meta"><div><span>Base quantity</span><strong>${fmtNumber(item.base_quantity)} ${escapeHtml(item.base_uom || "")}</strong></div><div><span>Material / unit</span><strong>${fmtMoney(item.unit_material)}</strong></div><div><span>Labour / unit</span><strong>${catalogLaborLabel(item)}</strong></div></div>
    <div class="table-scroll"><table class="mini-table"><thead><tr><th>Component</th><th>Qty / 1</th><th>Unit</th><th>Material</th><th>Labour / unit</th></tr></thead><tbody>${componentRows}</tbody></table></div>
    ${(item.variants || []).length > 1 ? `<div class="variant-section"><div><h4>Other saved allowances</h4><p>These options have different components, specifications or prices.</p></div><div class="variant-list">${variants}</div></div>` : ""}
    <button class="button secondary" data-price-history="${item.id}">Price history & source</button><button class="button secondary detail-delete" type="button">Delete catalog item</button><h4>Source history for this version</h4><div>${sources}</div>`;
  if(state.view==='catalog' && typeof rememberPage==='function')rememberPage('catalog',item.id);
  return item;
}

async function compareCatalogVersions(itemId, query = "") {
  setView("catalog", false, false);
  $("#catalog-search-input").value = query;
  await loadCatalog(query);
  await showCatalogDetail(itemId);
  $("#catalog-detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

let catalogHoverTimer;
let catalogHoverHideTimer;
let catalogHoverRequest = 0;

function positionCatalogHover(target) {
  const preview = $("#catalog-hover-preview");
  const rect = target.getBoundingClientRect();
  const width = Math.min(500, window.innerWidth - 28);
  preview.style.width = `${width}px`;
  const previewHeight = Math.min(preview.offsetHeight || 440, window.innerHeight - 28);
  let left = rect.right + 12;
  if (left + width > window.innerWidth - 14) left = rect.left - width - 12;
  if (left < 14) left = Math.max(14, (window.innerWidth - width) / 2);
  let top = rect.top;
  if (top + previewHeight > window.innerHeight - 14) top = window.innerHeight - previewHeight - 14;
  preview.style.left = `${Math.max(14, left)}px`;
  preview.style.top = `${Math.max(14, top)}px`;
}

function hideCatalogHover(delay = 90) {
  clearTimeout(catalogHoverTimer);
  clearTimeout(catalogHoverHideTimer);
  catalogHoverHideTimer = setTimeout(() => $("#catalog-hover-preview")?.classList.add("hidden"), delay);
}

function renderCatalogHover(item, target) {
  const preview = $("#catalog-hover-preview");
  const rows = (item.components || []).slice(0, 7).map((component) => `
    <tr><td>${componentLabel(component)}${component.fixed_quantity?'<small class="fixed-quantity-note">Fixed total quantity</small>':''}</td><td>${fmtNumber(component.quantity_per_unit, 3)} ${escapeHtml(component.uom || "")}</td><td>${fmtMoney(component.unit_material)}</td><td>${componentLaborLabel(component)}</td></tr>`).join("");
  preview.innerHTML = `
    <div class="hover-preview-heading"><div><strong>${catalogName(item)}</strong><small>${escapeHtml(item.category || "Other")} · ${variantText(item)}</small></div><em class="data-status ${escapeHtml(item.data_status)}">${(item.pricing_label || dataStatusLabel(item.data_status))}</em></div>
    <div class="hover-totals"><span>Material / unit <strong>${fmtMoney(item.unit_material)}</strong></span><span>Labour / unit <strong>${catalogLaborLabel(item)}</strong></span></div>
    <table class="hover-component-table"><thead><tr><th>Catalog contains</th><th>Qty / 1</th><th>Material</th><th>Labour / unit</th></tr></thead><tbody>${rows}</tbody></table>
    ${(item.components || []).length > 7 ? `<p>+ ${(item.components || []).length - 7} more connected rows. Click the catalog for the full list.</p>` : ""}`;
  preview.classList.remove("hidden");
  positionCatalogHover(target);
}

function queueCatalogHover(target) {
  if (window.matchMedia("(hover: none)").matches || window.innerWidth < 760) return;
  clearTimeout(catalogHoverTimer);
  clearTimeout(catalogHoverHideTimer);
  const request = ++catalogHoverRequest;
  catalogHoverTimer = setTimeout(async () => {
    const itemId = Number(target.dataset.catalogPreview);
    if (!itemId) return;
    const preview = $("#catalog-hover-preview");
    preview.innerHTML = `<p class="hover-loading">Loading catalog contents…</p>`;
    preview.classList.remove("hidden");
    positionCatalogHover(target);
    try {
      const item = await fetchCatalogItem(itemId);
      if (request === catalogHoverRequest && document.body.contains(target)) renderCatalogHover(item, target);
    } catch (_) {
      hideCatalogHover(0);
    }
  }, 170);
}

async function loadImports() {
  if (typeof refreshUploadHistory === 'function' && $('#import-history-dialog')?.open) await refreshUploadHistory();
}

async function importWorkbook(event) {
  event.preventDefault();
  const file = $("#import-file").files[0];
  if (!file) return;
  const progress = $("#import-progress");
  progress.classList.remove("hidden");
  progress.textContent = `Reading every supported sheet in ${file.name}…`;
  const form = new FormData();
  form.append("file", file);
  try {
    const result = await api("/api/import-previews", { method: "POST", body: form });
    renderImportPreview(result.report);
    progress.textContent = 'Preview ready. Review the rows below; no catalogue prices have been changed.';
  } catch (error) {
    progress.textContent = error.message;
    toast(error.message, true);
  }
}

function defaultSaveMode(addToEstimate, sourceItem) {
  if (!addToEstimate || !sourceItem) return 'new';
  const preferred=state.appSettings?.default_save_mode || 'estimate';
  return ['estimate','new'].includes(preferred) || (preferred==='update' && sourceItem.id) ? preferred : 'estimate';
}

async function loadSettings(render = true, initialData = null) {
  const result = initialData ? {settings:initialData} : await api("/api/settings");
  state.appSettings = result.settings;
  if (render) {
    $("#default-save-mode").value=result.settings.default_save_mode || "estimate";
    $("#default-hours-markup").value=Number(result.settings.default_labor_hours_markup||0)*100;
    $("#default-material-markup").value = Number(result.settings.default_material_markup || .15) * 100;
    $("#default-labour-rate").value = result.settings.default_labor_rate || 120;
    $("#default-overhead-markup").value = Number(result.settings.default_overhead_markup || .10) * 100;
    $("#default-currency").value = result.settings.currency || "AUD";
    $("#default-crew-size").value = result.settings.default_crew_size || 2;
    $("#default-hours-per-day").value = result.settings.default_hours_per_day || 8;
    $("#llm-enabled").checked = result.settings.llm_enabled === "1";
    const models = result.settings.llm_models || ["gemini-3.8-flash"];
    $("#llm-model").innerHTML = models.map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`).join("");
    $("#llm-model").value = models.includes(result.settings.llm_model) ? result.settings.llm_model : models[0];
    const keyInput = $("#gemini-api-key");
    keyInput.value = "";
    keyInput.type = "password";
    $("#toggle-gemini-key").textContent = "Show";
    const source = result.settings.llm_api_key_source;
    $("#llm-key-status").textContent = result.settings.llm_api_key_configured
      ? source === "saved" ? "Gemini API key is saved in this app. Select Show to view it, or replace it and save defaults."
        : "Gemini API key is configured from GEMINI_API_KEY. Enter a key here to save an override."
      : "No Gemini API key is configured. Search suggestions and local fuzzy matching still work without AI.";
    if (source === "saved") {
      const saved = await api("/api/settings/saved-key");
      keyInput.value = saved.api_key || "";
    }
  }
  return result.settings;
}

async function saveSettings(event) {
  event.preventDefault();
  const payload = {
    default_save_mode: $("#default-save-mode").value,
    default_labor_hours_markup: Number($("#default-hours-markup").value || 0) / 100,
    default_material_markup: Number($("#default-material-markup").value || 0) / 100,
    default_labor_rate: Number($("#default-labour-rate").value || 0),
    default_overhead_markup: Number($("#default-overhead-markup").value || 0) / 100,
    currency: $("#default-currency").value,
    default_crew_size: Number($("#default-crew-size").value || 2),
    default_hours_per_day: Number($("#default-hours-per-day").value || 8),
    llm_enabled: $("#llm-enabled").checked ? "1" : "0",
    llm_model: $("#llm-model").value,
  };
  const key = $("#gemini-api-key").value.trim();
  if (key) payload.gemini_api_key = key;
  await api("/api/settings", { method: "PATCH", body: payload });
  await loadSettings();
  toast("Application defaults and Gemini settings saved");
}

async function testGemini() {
  const button = $("#test-llm-button");
  const oldText = button.textContent;
  button.disabled = true;
  button.textContent = "Testing…";
  try {
    const payload = { llm_model: $("#llm-model").value };
    const key = $("#gemini-api-key").value.trim();
    if (key) payload.gemini_api_key = key;
    const result = await api("/api/settings/test-llm", { method: "POST", body: payload });
    $("#llm-key-status").textContent = `${result.message} Model: ${result.model}.`;
    toast("Gemini connection is working");
  } catch (error) {
    $("#llm-key-status").textContent = error.message;
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
}

async function clearGeminiKey() {
  if (!confirm("Clear the Gemini API key saved in this app?")) return;
  await api("/api/settings", { method: "PATCH", body: { clear_gemini_api_key: true } });
  await loadSettings();
  toast("Saved Gemini API key cleared");
}

function bindEvents() {
  $$(".nav-button").forEach((button) => { if(button.tagName!=='A')button.addEventListener("click", () => setView(button.dataset.view)); });
  $("#project-select").addEventListener("change", (event) => loadProject(event.target.value).catch((error) => toast(error.message, true)));
  $("#smart-search-form").addEventListener("submit", (event) => { event.preventDefault(); runSmartSearch(); });
  $('#clear-smart-search').addEventListener('click',()=>{$('#smart-search-input').value='';clearSmartSearch();$('#smart-search-input').focus();});
  $$('.summary-mode').forEach(button=>button.addEventListener('click',()=>{state.summaryMode=button.dataset.mode;$$('.summary-mode').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));renderScopeBreakdown(state.projectData);}));
  $("#smart-search-input").addEventListener("input", queueSmartSuggestions);
  $("#smart-search-input").addEventListener("focus", queueSmartSuggestions);
  $("#smart-search-input").addEventListener("blur", () => setTimeout(hideSmartSuggestions, 140));
  $("#smart-search-input").addEventListener("keydown", (event) => {
    const menuVisible = !$("#smart-search-suggestions").classList.contains("hidden") && state.suggestions.length;
    if (event.key === "ArrowDown" && menuVisible) { event.preventDefault(); setSuggestionIndex(state.suggestionIndex + 1); }
    else if (event.key === "ArrowUp" && menuVisible) { event.preventDefault(); setSuggestionIndex(state.suggestionIndex <= 0 ? state.suggestions.length - 1 : state.suggestionIndex - 1); }
    else if (event.key === "Enter" && menuVisible && state.suggestionIndex >= 0) { event.preventDefault(); chooseSmartSuggestion(state.suggestionIndex).catch((error) => toast(error.message, true)); }
    else if (event.key === "Escape") hideSmartSuggestions();
  });
  $("#smart-search-suggestions").addEventListener('scroll',event=>{const box=event.currentTarget;if(box.scrollTop+box.clientHeight>=box.scrollHeight-100&&box.querySelector('.suggestion-more')&&!suggestionLoading)loadSmartSuggestions(true);},{passive:true});
  $("#smart-search-suggestions").addEventListener("mousedown", (event) => event.preventDefault());
  $("#smart-search-suggestions").addEventListener("click", (event) => {
    const more=event.target.closest('.suggestion-more');
    if(more){more.disabled=true;loadSmartSuggestions(true).catch(error=>toast(error.message,true));return;}
    const button = event.target.closest(".suggestion-item");
    if (button) chooseSmartSuggestion(Number(button.dataset.index)).catch((error) => toast(error.message, true));
  });
  $("#search-results").addEventListener("click", (event) => {
    const compare = event.target.closest(".compare-variants");
    if (compare) {
      compareCatalogVersions(compare.dataset.id, compare.dataset.query).catch((error) => toast(error.message, true));
      return;
    }
    const editAdd = event.target.closest(".edit-add-result");
    if (editAdd) { fetchCatalogItem(editAdd.dataset.id).then((item) => openManualDialog(true, item)).catch((error) => toast(error.message, true)); return; }
    const button = event.target.closest(".add-result");
    if (button) addCatalogItem(button.dataset.id, button.dataset.query).catch((error) => toast(error.message, true));
  });
  $("#estimate-lines").addEventListener("click", (event) => {
    const toggle = event.target.closest(".toggle-details");
    if (toggle) {
      const id=Number(toggle.dataset.lineId);
      if(estimateViewState.expanded.has(id))estimateViewState.expanded.delete(id);else estimateViewState.expanded.add(id);
      renderGroupedEstimate(state.projectData.lines);
    }
    const edit = event.target.closest(".edit-estimate-line");
    if (edit) openEstimateLineEditor(edit.dataset.lineId);
    const remove = event.target.closest(".delete-line");
    if (remove && confirm("Remove this assembly and its detail rows from the estimate?")) removeLine(remove.dataset.lineId).catch((error) => toast(error.message, true));
  });
  $('#estimate-lines').addEventListener('focusin',event=>{if(event.target.matches('.line-category'))showCategorySuggestions(event.target,true);});
  $('#estimate-lines').addEventListener('focusout',event=>{if(event.target.matches('.line-category'))setTimeout(()=>{if(!event.target.parentElement.contains(document.activeElement))event.target.parentElement.querySelector('.category-suggestions').classList.add('hidden');},0);});
  function chooseCategory(event){
    const choice=event.target.closest('.category-choice');if(!choice)return;
    event.preventDefault();
    const editor=choice.closest('.category-editor'),field=editor.querySelector('.line-category');
    field.value=choice.dataset.category;editor.dataset.value=field.value;
    editor.querySelector('.category-suggestions').classList.add('hidden');
    updateLineCategory(field.dataset.lineId,field.value).catch(error=>{toast(error.message,true);renderProject();});
  }
  $('#estimate-lines').addEventListener('pointerdown',chooseCategory);
  $('#estimate-lines').addEventListener('click',event=>{if(event.detail===0)chooseCategory(event);});
  $("#estimate-lines").addEventListener("input", (event) => {
    if(event.target.matches('.line-category'))showCategorySuggestions(event.target);

    if (event.target.matches(".line-category")) event.target.parentElement.dataset.value = event.target.value;
  });
  $("#estimate-lines").addEventListener("change", (event) => {
    const field=event.target;
    const key=field.matches('.line-remarks')?'notes':field.matches('.line-light-reference')?'reference_name':field.matches('.line-estimate-size')?'size_snapshot':field.matches('.line-work-type')?'work_type_snapshot':field.matches('.line-estimate-name')?'name_snapshot':field.matches('.line-supply-quantity')?'supply_quantity_override':field.matches('.line-supply-cost')?'supply_unit_cost_override':null;
    if(key){
      const value=['notes','reference_name','name_snapshot','work_type_snapshot','size_snapshot'].includes(key)?field.value:field.value===''?null:Number(field.value);
      field.disabled=true;
      api(`/api/projects/${state.projectId}/lines/${field.dataset.lineId}`,{method:'PATCH',body:{[key]:value,expected_revision:state.projectData.lines.find(l=>l.id===Number(field.dataset.lineId))?.revision}}).then(result=>{if(result.project.id===state.projectId && Number(result.project.revision)>=Number(state.projectData?.project?.revision||0)){state.projectData=result;renderProject();}}).catch(error=>{field.disabled=false;toast(error.message,true);});
    }
    if (event.target.matches(".line-category")) updateLineCategory(event.target.dataset.lineId, event.target.value).catch((error) => { toast(error.message, true); renderProject(); });
    if (event.target.matches(".line-quantity")) updateLineQuantity(event.target.dataset.lineId, event.target.value).catch((error) => toast(error.message, true));
  });
  $("#toggle-project-settings").addEventListener("click", event => {
    const collapsed = $("#project-settings-form").classList.toggle("hidden");
    const button = event.currentTarget;
    button.textContent = collapsed ? "+" : "−";
    button.setAttribute("aria-expanded", String(!collapsed));
    button.title = `${collapsed ? "Expand" : "Collapse"} rates and mark-ups`;
    button.setAttribute("aria-label", button.title);
  });
  $("#project-settings-form").addEventListener("input",queueProjectSettings);
  $("#project-settings-form").addEventListener("change",()=>saveProjectSettings().catch(()=>{}));
  $("#project-settings-form").addEventListener("submit", (event) => saveProjectSettings(event).catch((error) => toast(error.message, true)));
  $("#delete-project-button").addEventListener("click", () => deleteCurrentProject().catch((error) => toast(error.message, true)));
  $("#floating-search-button").addEventListener("click", () => { $("#smart-search-form").scrollIntoView({behavior:"smooth",block:"center"});$("#smart-search-input").focus({preventScroll:true}); });
  $("#quick-search-form").addEventListener("submit", (event) => { event.preventDefault(); runQuickSearch().catch((error) => toast(error.message, true)); });
  $("#quick-search-input").addEventListener("input", () => {
    ++state.quickSearchRequest;
    clearTimeout(state.quickSearchTimer);
    state.quickSearchTimer = setTimeout(() => runQuickSearch().catch((error) => { $("#quick-search-status").textContent = error.message; }), 180);
  });
  $("#quick-search-results").addEventListener("click", (event) => {
    const more=event.target.closest(".quick-search-more");if(more){more.disabled=true;runQuickSearch(true).catch(error=>{more.disabled=false;toast(error.message,true)});return;}
    const add = event.target.closest(".quick-add");
    if (add) addQuickResult(add).catch((error) => { $("#quick-search-status").textContent = error.message; });
    const edit = event.target.closest(".quick-edit-add");
    if (edit) fetchCatalogItem(edit.dataset.id).then((item) => {
      $("#quick-search-dialog").close();
      openManualDialog(true, item, false, null, Number($("#quick-search-quantity").value || 1));
    }).catch((error) => toast(error.message, true));
  });
  $("#quick-manual-button").addEventListener("click", () => {
    $("#quick-search-dialog").close();
    openManualDialog(true, null, false, null, Number($("#quick-search-quantity").value || 1));
  });
  $("#new-project-button").addEventListener("click", () => openProjectForm());
  $("#home-new-project-button").addEventListener("click", () => openProjectForm());
  $("#new-project-form").addEventListener("submit", (event) => submitWithButton(event, () => createNewProject(event)));
  $$(".close-dialog").forEach((button) => button.addEventListener("click", () => {
    if (button.closest("dialog").id === "manual-dialog" && state.manualSaving) return;
    button.closest("dialog").close();
  }));
  $("#manual-dialog").addEventListener("cancel", (event) => { if (state.manualSaving) event.preventDefault(); });
  $("#manual-item-button").addEventListener("click", () => openManualDialog(true));
  $("#catalog-manual-button").addEventListener("click", () => openManualDialog(false));
  $("#add-component-button").addEventListener("click", () => {
    $("#manual-components").insertAdjacentHTML("beforeend", componentRow({ uom: $("#manual-uom").value || "EA" }));
    refreshManualPricing();
  });
  $("#manual-components").addEventListener("click", (event) => {
    const remove = event.target.closest(".remove-component");
    if (remove && $$("#manual-components .manual-component").length > 1) { remove.closest("tr").remove(); refreshManualPricing(); }
  });
  $("#manual-work-type").addEventListener("change", refreshManualPricing);
  $("#manual-name").addEventListener("input", () => {
    const first = $("#manual-components .manual-component");
    if (first?.dataset.autoDescription === "1") $(".component-description", first).value = $("#manual-name").value;
  });
  $("#manual-uom").addEventListener("input", () => {
    const rows = $$("#manual-components .manual-component");
    if (rows.length === 1 && Number($(".component-ratio", rows[0]).value) === 1 && $(".component-uom", rows[0]).value === state.manualBaseUom) {
      $(".component-uom", rows[0]).value = $("#manual-uom").value;
    }
    state.manualBaseUom = $("#manual-uom").value;
    refreshManualPricing();
  });
  $("#manual-components").addEventListener("change", (event) => {
    if (event.target.matches('.component-fixed-quantity')) {
      const row=event.target.closest('tr'),input=$('.component-ratio',row),original=JSON.parse(row.dataset.component||'{}');
      if(event.target.checked){row.dataset.scaledRatio=input.value;input.value=original.source_quantity??original.quantity_per_unit??input.value;}
      else input.value=row.dataset.scaledRatio??original.quantity_per_unit??input.value;
      refreshManualPricing();
    }
    if (event.target.matches(".component-labor-mode")) {
      const row = event.target.closest("tr");
      const input = $(".component-labor-value", row);
      const values = JSON.parse(row.dataset.component || "{}");
      values[row.dataset.laborMode === "fixed" ? "unit_labor_price" : "unit_hours"] = Number(input.value || 0);
      row.dataset.component = JSON.stringify(values);
      row.dataset.laborMode = event.target.value;
      input.value = values[event.target.value === "fixed" ? "unit_labor_price" : "unit_hours"] || 0;
      input.setAttribute("aria-label", event.target.value === "fixed" ? "Unit labour price" : "Unit labour hours");
      $(".component-labor-label", row).textContent = event.target.value === "fixed" ? "Price / unit" : "Hours / unit";
      refreshManualPricing();
    }
  });
  $('#manual-rating').addEventListener('click',event=>{const button=event.target.closest('[data-rating]');if(button)changeManualRating(Number(button.dataset.rating));});
  $("#manual-item-form").addEventListener("input", (event) => {
    if (event.target.matches(".component-description")) event.target.closest("tr").dataset.autoDescription = "0";
    // Select changes switch the value first in the change handler above.
    if (!event.target.matches(".component-labor-mode")) refreshManualPricing();
  });
  $("#manual-item-form").addEventListener("submit", (event) => saveManualItem(event).catch(showManualSaveError));
  $("#catalog-search-button").addEventListener("click", () => loadCatalog().catch((error) => toast(error.message, true)));
  $('#catalog-search-input').addEventListener('input',()=>{clearTimeout(catalogSearchTimer);catalogSearchRequest++;catalogSearchTimer=setTimeout(()=>loadCatalog().catch(error=>toast(error.message,true)),200);});
  $("#catalog-search-input").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); loadCatalog().catch((error) => toast(error.message, true)); } });
  $("#catalog-category").addEventListener("change", () => loadCatalog().catch((error) => toast(error.message, true)));
  $("#catalog-results").addEventListener("click", (event) => {
    const more=event.target.closest(".catalog-search-more");if(more){more.disabled=true;loadCatalog(null,true).catch(error=>{more.disabled=false;toast(error.message,true)});return;}
    const result = event.target.closest(".catalog-result");
    if (result && result.tagName!=='A') showCatalogDetail(result.dataset.id).catch((error) => toast(error.message, true));
  });
  $("#catalog-detail").addEventListener("click", (event) => {
    if(event.target.closest('.detail-delete')) deleteCurrentCatalog().catch(error=>toast(error.message,true));

    const variant = event.target.closest(".variant-option");
    if (variant && variant.tagName!=='A') {
      showCatalogDetail(variant.dataset.variantId).catch((error) => toast(error.message, true));
      return;
    }
    const add = event.target.closest(".detail-add");
    if (add) addCatalogItem(add.dataset.id, state.currentCatalogItem?.name, 1).then(() => setView("estimate")).catch((error) => toast(error.message, true));
    if (event.target.closest(".detail-clone")) openManualDialog(false, state.currentCatalogItem);
    if (event.target.closest(".detail-edit")) openManualDialog(false, state.currentCatalogItem, true);
  });
  $("#import-form").addEventListener("submit", importWorkbook);
  $("#import-file").addEventListener("change", (event) => { if (event.target.files[0]) { $("#import-progress").textContent = "File selected. Click Preview workbook to continue."; $("#import-progress").classList.remove("hidden"); } });
  $("#app-settings-form").addEventListener("submit", (event) => saveSettings(event).catch((error) => toast(error.message, true)));
  $("#test-llm-button").addEventListener("click", () => testGemini());
  $("#clear-llm-key-button").addEventListener("click", () => clearGeminiKey().catch((error) => toast(error.message, true)));
  $("#toggle-gemini-key").addEventListener("click", () => {
    const input = $("#gemini-api-key");
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    $("#toggle-gemini-key").textContent = showing ? "Show" : "Hide";
  });
  $("#export-button").addEventListener("click", () => { if (state.projectId) window.location.href = `/api/projects/${state.projectId}/export`; });
  document.addEventListener("mouseover", (event) => {
    const target = event.target.closest?.("[data-catalog-preview]");
    if (target && !target.contains(event.relatedTarget)) queueCatalogHover(target);
  });
  document.addEventListener("mouseout", (event) => {
    const target = event.target.closest?.("[data-catalog-preview]");
    if (target && !target.contains(event.relatedTarget) && !$("#catalog-hover-preview")?.contains(event.relatedTarget)) hideCatalogHover();
  });
  $("#catalog-hover-preview").addEventListener("mouseenter", () => {
    clearTimeout(catalogHoverHideTimer);
  });
  $("#catalog-hover-preview").addEventListener("mouseleave", () => hideCatalogHover(40));
}

document.addEventListener("DOMContentLoaded", async () => {
  $('#startup-retry').addEventListener('click',()=>bootWorkspace());
  bindEvents();
  bindProjectSharing();
  bindFrozenEstimateHeader();
  bindWorkspaceEvents();
  if(typeof bindProductivityEvents==='function')bindProductivityEvents();
  await bootWorkspace();
});

;
/* workspace.js */
/* Project board, account administration and deadline calendar. */
const workspaceState = { filter: 'month', reminderRows: [], boardView: 'cards', boardSort: 'newest', users: [], teams: [], notesProjectId: null, notesRequest: 0, noteCounts: {}, noteStatusRequests: {}, noteReadPending: {}, notesSyncBusy: false, teamId: null, briefId: null, userId: null, month: new Date(new Date().getFullYear(), new Date().getMonth(), 1), briefRequest: 0 };
const statusNames = { draft: 'Not started', in_progress: 'In progress', in_review: 'In review', submitted: 'Submitted', closed: 'Closed' };

function localDateKey(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
function dateLabel(value) {
  if (!value) return 'No deadline';
  const [y,m,d] = value.split('-').map(Number);
  return new Date(y,m-1,d).toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'});
}
function isOpenProject(project) { return !['submitted','completed','closed'].includes(project.status); }
function projectDeadline(project) { return project.status==='in_review' ? project.review_deadline : project.submission_deadline; }
function isOverdue(project) { return isOpenProject(project) && projectDeadline(project) && projectDeadline(project) < localDateKey(); }
function projectStatus(project) {
  return `<span class="project-status status-${escapeHtml(project.status)}">${escapeHtml(statusNames[project.status] || project.status)}</span>`;
}
function setAccount(user, token) {
  const changedUser=state.user?.id!==user.id;
  state.user = user; state.csrfToken = token;
  if(changedUser){workspaceState.filter='month';workspaceState.reminderRows=[];workspaceState.boardView='cards';workspaceState.boardSort='newest';
    try{const saved=localStorage.getItem('conest-project-sort-v31-'+user.id);if(['recent','name','name-desc','deadline','deadline-desc','newest','cost-high','cost-low'].includes(saved))workspaceState.boardSort=saved;}catch(_){}
    try{const saved=localStorage.getItem('conest-project-view-'+user.id);if(['cards','list'].includes(saved))workspaceState.boardView=saved;}catch(_){}
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
  document.body.classList.remove('app-loading');
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
  document.body.classList.add('app-loading');
  try {
    setAccount(result.user, result.csrf_token);
    if (state.user.must_change_password) { setView('profile',false); return; }
    if(new URLSearchParams(location.search).get('return')==='tenders'){location.replace('/tenders/');return;}
    await Promise.all([loadSettings(false,result.settings),loadDashboard(false,result.dashboard)]);
    if(typeof restorePage==='function')await restorePage(); else setView('home',false);
  } finally {document.body.classList.remove('app-loading');window.dispatchEvent(new Event('conest:workspace-ready'));}
}
async function bootWorkspace() {
  document.body.classList.add('app-loading');
  $('#startup-screen').classList.remove('loading-failed');
  $('#startup-message').textContent='Loading your workspace…';
  $('#startup-retry').classList.add('hidden');
  try {
    const pending=window.__estimatorBoot;delete window.__estimatorBoot;
    const result=pending ? await pending : await api('/api/bootstrap');
    if(result?.error){const error=new Error(result.error);error.status=result.status;throw error;}
    await enterWorkspace(result);
  }
  catch(error) {
    if(error.status===401){showLogin();return;}
    // A temporary network/server fault does not mean the session expired.
    document.body.classList.add('app-loading');
    $('#startup-screen').classList.add('loading-failed');
    $('#startup-message').textContent=error.message;
    $('#startup-retry').classList.remove('hidden');
  }
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
  renderProjectBoard();
  if(state.view==='home'&&typeof loadReminders==='function')loadReminders().catch(()=>{});
  renderSchedule();
  const values = new Map();
  projects.filter(isOpenProject).forEach(p=>values.set(p.currency,(values.get(p.currency)||0)+Number(p.totals?.quoted||0)));
  $('#portfolio-value').textContent = values.size ? 'Active estimate value: '+[...values].map(([currency,value])=>`${currency} ${fmtMoney(value,currency)}`).join(' · ') : '';
}
function renderSchedule(){
  const reminders=new Map(workspaceState.reminderRows.map(row=>[`${row.project_id}:${row.kind||'submission'}`,row]));
  const due=state.projects.filter(p=>projectDeadline(p)&&isOpenProject(p)).sort((a,b)=>projectDeadline(a).localeCompare(projectDeadline(b))||a.id-b.id);
  const render=p=>{
    const review=p.status==='in_review',deadline=projectDeadline(p);
    const reminder=reminders.get(`${p.id}:${review?'review':'submission'}`);
    const days=reminder?.days??Math.round((new Date(deadline+'T12:00:00')-new Date(localDateKey()+'T12:00:00'))/86400000);
    const timing=days<0?`${-days} day${days===-1?'':'s'} overdue`:days===0?'Due today':`Due in ${days} day${days===1?'':'s'}`;
    return `<article class="schedule-item ${review?'is-review':''} ${isOverdue(p)?'overdue':''}"><div class="schedule-date">${review?'Review by · ':''}${dateLabel(deadline)}${reminder&&!reminder.read?'<span class="schedule-new">New</span>':''}</div><button type="button" class="text-button" data-project-brief="${p.id}">${escapeHtml(p.name)}</button><small class="${isOverdue(p)?'overdue-text':''}">${timing}</small>${reminder&&!reminder.read?`<button type="button" class="schedule-seen text-button" data-read-reminder="${escapeHtml(reminder.key)}">Mark seen</button>`:''}</article>`;
  };
  $('#deadline-agenda').innerHTML=due.length?due.slice(0,5).map(render).join('')+(due.length>5?`<details class="schedule-more"><summary>${due.length-5} more deadlines</summary>${due.slice(5).map(render).join('')}</details>`:''):'<p class="board-empty">You’re up to date. No pending deadlines.</p>';
}

function homeMetricProjects(projects, filter, month) {
  if(filter==='month')return projects.filter(p=>(p.submission_deadline||'').slice(0,7)===month);
  if(filter==='team')return projects.filter(p=>p.is_assigned);
  return projects;
}
function renderHomeMetrics() {
  const projects=homeMetricProjects(state.projects,workspaceState.filter,sydneyMonth());
  const metrics = Object.entries(statusNames).map(([key,label]) => [label,projects.filter(p=>p.status===key).length,key]);
  $('#home-metrics').innerHTML = metrics.map(([label,value,filter]) => `<button class="metric home-metric ${filter==='new'?'accent':''}" type="button" data-filter="${filter}"><span>${label}</span><strong>${value}</strong><small>${filter==='new'?'Open to review new team projects':filter==='draft'?'Ready to begin':filter==='in_progress'?'Estimates being prepared':filter==='in_review'?'Review before the deadline':filter==='closed'?'Closed / not submitted':'Submitted estimate'}</small></button>`).join('');
  $('#home-metrics').classList.add('five-metrics');
  $('#home-metrics').setAttribute('aria-label',workspaceState.filter==='month'?'This month project statistics':workspaceState.filter==='team'?'My team project statistics':'All time project statistics');
}

function renderProjectBoard() {
  const term = $('#project-search').value.trim().toLowerCase();
  const filter = ['all','month','team',...Object.keys(statusNames)].includes(workspaceState.filter)?workspaceState.filter:'all';
  workspaceState.filter=filter;
  renderHomeMetrics();
  const board=$('#project-board');board.dataset.view=workspaceState.boardView;$('#project-view-style').value=workspaceState.boardView;
  $$('#project-tabs button').forEach(b=>{b.classList.toggle('active',b.dataset.filter===filter);b.setAttribute('aria-pressed',String(b.dataset.filter===filter));});
  const projects = state.projects.filter(p=>{
    if (!(p.name+' '+builderText(p)+' '+(p.created_by_name||'')+' '+teamNames(p)+' '+(p.contributors||[]).map(c=>c.name).join(' ')).toLowerCase().includes(term)) return false;
    if (filter==='month') return (p.submission_deadline||'').slice(0,7)===sydneyMonth();
    if (filter==='team') return p.is_assigned;
    if (statusNames[filter]) return p.status===filter;
    return true;
  });
  const sort=workspaceState.boardSort;
  $('#project-sort').value=sort;
  projects.sort((a,b)=>{
    // Different currencies stay in their own groups; do not imply conversion.
    if(sort==='cost-high'||sort==='cost-low')return (a.currency||'').localeCompare(b.currency||'')||(sort==='cost-high'?-1:1)*(Number(a.totals?.quoted||0)-Number(b.totals?.quoted||0))||a.name.localeCompare(b.name);
    if(sort==='name'||sort==='name-desc')return (sort==='name'?1:-1)*a.name.localeCompare(b.name,undefined,{numeric:true,sensitivity:'base'});
    if(sort==='deadline'||sort==='deadline-desc'){const ad=projectDeadline(a),bd=projectDeadline(b);return (!ad)-(!bd)||(sort==='deadline'?1:-1)*(ad||'').localeCompare(bd||'')||a.name.localeCompare(b.name);}
    const key=sort==='newest'?'created_at':'updated_at';
    return (b[key]||'').localeCompare(a[key]||'')||b.id-a.id;
  });
  board.innerHTML = projects.length ? projects.map(p=>`<article class="project-card">
    <div class="project-card-heading"><div>${builderText(p)?`<p>${escapeHtml(builderText(p))}</p>`:''}<h3><button type="button" data-project-brief="${p.id}">${escapeHtml(p.name)}</button></h3></div><div class="project-badges">${inReviewQueue(p)?'<span class="project-status status-new">Newly added</span>':''}${projectStatus(p)}</div></div>
    <div class="project-facts"><span class="${isOverdue(p)?'overdue-text':''}">${isOverdue(p)?'Overdue · ':''}${p.status==='in_review'?'Review by · ':''}${dateLabel(projectDeadline(p))}</span>${projectOutcome(p)}${p.can_edit?'':'<span class="project-readonly-badge">Read-only</span>'}</div>
    <div class="project-card-footer"><span>${p.line_count||0} items <strong>${escapeHtml(p.currency)} ${fmtMoney(p.totals?.quoted,p.currency)}</strong></span><a class="button primary small" href="#/estimate/${p.id}" data-open-project="${p.id}">Open Estimate</a></div>
    <details class="project-more"><summary>Project details</summary>${p.scope_of_work?`<p class="project-scope-excerpt">${escapeHtml(p.scope_of_work)}</p>`:''}<p class="project-team"><strong>Team:</strong> ${escapeHtml(teamNames(p))}<br><strong>Added by:</strong> ${escapeHtml(p.created_by_name||'Creator not recorded')}${p.updated_by_name?`<br>Last edited by ${escapeHtml(p.updated_by_name)}`:''}</p><div class="project-more-actions"><button type="button" class="button secondary small" data-project-brief="${p.id}">${p.can_edit?'Manage Project':'View Project'}</button><button class="button secondary small" type="button" data-copy-project="${p.id}">Copy Project</button></div></details>
  </article>`).join('') : '<div class="board-empty"><h3>No matching projects</h3><p>Try a different search or status, or use New Project to add a project.</p></div>';

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
    $('#user-rows').innerHTML=result.users.map(u=>`<tr><td><strong>${escapeHtml(u.name)}</strong><small class="line-unit">${escapeHtml(u.job_title)}</small></td><td>${escapeHtml(u.username)}</td><td>${u.role==='admin'?'Admin':'User'}</td><td>${escapeHtml(u.role==='admin'?'All projects':u.team_name||'No team')}</td><td>${u.is_active?'Active':'Inactive'}${u.must_change_password?' · Setup pending':''}</td><td><div class="user-action-buttons"><button class="button secondary small" type="button" data-performance="${u.id}">View Contribution</button><button class="button secondary small" type="button" data-edit-user="${u.id}">Edit user</button></div></td></tr>`).join('');
    renderTeams();
  }
  return result.users;
}
function renderTeams() {
  $('#team-cards').innerHTML=workspaceState.teams.map(t=>`<article class="team-card"><div><h3>${escapeHtml(t.name)}</h3><span>${t.members.filter(m=>m.is_active).length} active members</span></div><p>${t.members.length?t.members.map(m=>escapeHtml(m.name)+(m.is_active?'':' (inactive)')).join(', '):'No members yet'}</p><button class="button secondary small" type="button" data-edit-team="${t.id}">Edit team & members</button><button class="button secondary small danger-text" type="button" data-delete-team="${t.id}">Delete team</button></article>`).join('');
}
async function openProjectBrief(id) {
  const request=++workspaceState.briefRequest;
  const dialog=$('#project-brief-dialog');
  workspaceState.briefId=null;workspaceState.briefProject=null;
  $('#brief-title').textContent=state.projects.find(p=>p.id===Number(id))?.name||'Project details';
  $('#brief-client').textContent='';dialog.classList.add('brief-loading');dialog.setAttribute('aria-busy','true');
  if(!dialog.open)dialog.showModal();
  try {
  const result=await api(`/api/projects/${Number(id)}/brief`);
  if(request!==workspaceState.briefRequest||!dialog.open)return;
  const p=await reviewOpenedProject(result.project);
  const {access,history}=result;
  if(request!==workspaceState.briefRequest||!dialog.open) return;
  workspaceState.briefId=p.id; workspaceState.briefProject=p;
  $('#brief-open-estimate').href=`#/estimate/${p.id}`;
  $('#brief-title').textContent=p.name; $('#brief-name').value=p.name; $('#brief-name').disabled=!p.can_manage; $('#brief-name').classList.add('hidden'); $('#brief-title').classList.remove('hidden'); $('#brief-edit-title').classList.toggle('hidden',!p.can_manage); $('#brief-client').textContent=builderText(p, 'Manage project');
  $('#brief-summary').innerHTML=`<div class="brief-meta">${projectStatus(p)}<span>Added by: ${escapeHtml(p.created_by_name||'Creator not recorded')}</span><span>Team: ${escapeHtml(teamNames(p))}</span>${individualNames(p)?`<span>Individual editors: ${escapeHtml(individualNames(p))}</span>`:''}</div><p class="helper-text">Contributors: ${p.contributors?.length?p.contributors.map(u=>escapeHtml(u.name)).join(', '):'No recorded work yet'}</p>`;
  $('#brief-scope').value=p.scope_of_work||''; $('#brief-deadline').value=p.submission_deadline||''; $('#brief-status').value=p.status;
    $('#brief-review-deadline').value=p.review_deadline||'';syncReviewDeadline(p.can_edit);
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
  } catch(error) {if(request===workspaceState.briefRequest)dialog.close();throw error;}
  finally {if(request===workspaceState.briefRequest){dialog.classList.remove('brief-loading');dialog.removeAttribute('aria-busy');}}
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
  if(!dialog.open||!pid||workspaceState.briefProject?.can_edit||workspaceState.briefSyncBusy||workspaceState.activityLoading)return;
  workspaceState.briefSyncBusy=true;
  try {
    const result=await api(`/api/projects/${pid}/brief`);const history=result.history;
    if(!dialog.open||pid!==workspaceState.briefId||request!==workspaceState.briefRequest)return;
    const p=result.project,old=workspaceState.briefProject;
    // Permission changes need to rebuild disabled controls from server truth.
    if(p.can_edit!==old.can_edit||p.can_manage!==old.can_manage||p.can_delete!==old.can_delete){await openProjectBrief(pid);return;}
    workspaceState.briefProject=p;
    $('#brief-title').textContent=p.name;
    $('#brief-client').textContent=builderText(p, 'View project');
    renderBuilderEditor('brief-builders', projectBuilders(p), false);
    $('#brief-scope').value=p.scope_of_work||'';$('#brief-deadline').value=p.submission_deadline||'';$('#brief-status').value=p.status;
    $('#brief-review-deadline').value=p.review_deadline||'';syncReviewDeadline(p.can_edit);
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
function syncReviewDeadline(editable=workspaceState.briefProject?.can_edit) {
  const review=$('#brief-status').value==='in_review';
  $('#brief-review-field').classList.toggle('hidden',!review);
  $('#brief-review-deadline').disabled=!review||!editable;
  $('#brief-review-deadline').required=review&&Boolean(editable);
}
async function saveProjectWorkflow() {
  const p=workspaceState.briefProject;
  if(!p) throw new Error('Project no longer available');
  const payload={status:$('#brief-status').value,review_deadline:$('#brief-status').value==='in_review'?$('#brief-review-deadline').value:null,award_status:$('#brief-award-status').value,expected_revision:p.revision};
  if(p.can_manage) {payload.name=$('#brief-name').value;payload.scope_of_work=$('#brief-scope').value;payload.builders=readBuilderEditor('brief-builders');payload.submission_deadline=$('#brief-deadline').value;}
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
  if(workspaceState.boardRefreshing)return;
  const uid=state.user?.id;
  workspaceState.boardRefreshing=true;
  try{
    const session=await api('/api/auth/session');
    if(uid!==state.user?.id)return;
    setAccount(session.user,session.csrf_token);
    if(session.user.must_change_password){setView('profile',false);return;}
    const result=await api('/api/projects');
    if(uid!==state.user?.id)return;
    if(JSON.stringify(state.projects)===JSON.stringify(result.projects))return;
    state.projects=result.projects;renderProjectSelect();
    if(state.view==='home')renderHome();
    if(state.view==='calendar')renderCalendar();
  }finally{workspaceState.boardRefreshing=false;}
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
  let html=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((d,i)=>`<div class="calendar-weekday ${i>=5?'is-weekend':''}">${d}</div>`).join('');
  const projects=state.projects.filter(p=>p.submission_deadline);
  const reviews=state.projects.filter(p=>p.status==='in_review'&&p.review_deadline);
  for(let i=0;i<cells;i++) {
    const day=new Date(y,m,i-offset+1), key=localDateKey(day);
    const items=projects.filter(p=>p.submission_deadline===key);
    const weekend=day.getDay()===0||day.getDay()===6;
    const reviewItems=reviews.filter(p=>p.review_deadline===key&&p.submission_deadline!==key);
    const event=(p,reviewOnly=false)=>{
      const review=p.status==='in_review',reviewToday=review&&p.review_deadline===key;
      const label=reviewOnly?'Review due':reviewToday?'Submission · Review due':'Submission due';
      return `<button class="calendar-event ${review?'is-review':['submitted','closed'].includes(p.status)?'done':isOverdue(p)?'late':p.is_assigned?'assigned':''}" type="button" data-project-brief="${p.id}" data-event-kind="${reviewOnly?'review':'submission'}" title="${escapeHtml(p.name)} — ${label} — ${escapeHtml(statusNames[p.status])}">${escapeHtml(p.name)}${reviewToday?`<small class="calendar-review-stamp">${label}</small>`:''}</button>`;
    };
    html+=`<div class="calendar-day ${weekend?'is-weekend':''} ${day.getMonth()!==m?'outside-month':''} ${key===localDateKey()?'is-today':''}"><time datetime="${key}" aria-label="${escapeHtml(dateLabel(key))}${weekend?', weekend':''}">${day.getDate()}</time>${items.map(p=>event(p)).join('')}${reviewItems.map(p=>event(p,true)).join('')}</div>`;

  }
  $('#calendar-grid').innerHTML=html;
  const monthProjects=projects.filter(p=>p.submission_deadline.startsWith(`${y}-${String(m+1).padStart(2,'0')}`)).sort((a,b)=>a.submission_deadline.localeCompare(b.submission_deadline));
  // Monetary totals and counts use submission dates only, never review entries.
  renderCalendarSummary(monthProjects);
}
function bindWorkspaceEvents() {
  setInterval(async()=>{
    if(!state.user || state.user.must_change_password || document.hidden || state.apiPendingCount || workspaceState.notesSyncBusy) return;
    workspaceState.notesSyncBusy=true;
    try {
      if($('#notes-dialog').open) await loadProjectNotes();
      else if(state.view==='estimate' && state.projectId) await refreshNoteBadge(state.projectId);
    } catch(_) {} finally {workspaceState.notesSyncBusy=false;}
  },30000+Math.random()*5000);
  setInterval(()=>{if(state.user&&!state.user.must_change_password&&!document.hidden&&!state.apiPendingCount)refreshReadOnlyBrief().catch(()=>{});},30000+Math.random()*5000);

  $('#notes-form').addEventListener('submit',event=>submitWithButton(event,saveProjectNote));
  $('#refresh-notes').addEventListener('click',()=>loadProjectNotes().catch(error=>toast(error.message,true)));
  setInterval(()=>{
    if(state.user && !state.user.must_change_password && ['home','calendar'].includes(state.view) && !document.hidden && !state.apiPendingCount && !$('dialog[open]')) refreshBoard().catch(()=>{});
  },60000+Math.random()*10000);
  $('#login-form').addEventListener('submit',event=>submitWithButton(event,async()=>{
    $('#login-error').textContent='';$('#login-form').setAttribute('aria-busy','true');$('#login-submit').textContent='Signing in…';
    try {
      const result=await api('/api/auth/login',{method:'POST',body:{username:$('#login-username').value,password:$('#login-password').value}});
      $('#login-password').value=''; await enterWorkspace(result);
    } catch(error) { $('#login-error').textContent=error.message; }
    finally {$('#login-form').removeAttribute('aria-busy');$('#login-submit').innerHTML='Sign in <span aria-hidden="true">→</span>';} 
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
  $('#brief-edit-title').addEventListener('click',()=>{if(!workspaceState.briefProject?.can_manage)return;$('#brief-title').classList.add('hidden');$('#brief-name').classList.remove('hidden');$('#brief-name').focus();$('#brief-name').select();});
  $('#brief-status').addEventListener('change',()=>syncReviewDeadline());
  $('#project-workflow-form').addEventListener('submit',event=>submitWithButton(event,saveProjectWorkflow));
  $('#team-form').addEventListener('submit',event=>submitWithButton(event,saveTeam));
  $('#add-team').addEventListener('click',()=>openTeamEditor());
  $('#user-role').addEventListener('change',syncUserRole);
  $('#brief-delete').addEventListener('click',()=>deleteManagedProject().catch(error=>toast(error.message,true)));
  $('#add-user').addEventListener('click',()=>openUserEditor());
  $('#project-search').addEventListener('input',renderProjectBoard);
  $('#project-sort').addEventListener('change',event=>{
    const value=event.target.value;if(!['recent','name','name-desc','deadline','deadline-desc','newest','cost-high','cost-low'].includes(value))return;
    workspaceState.boardSort=value;
    try{localStorage.setItem('conest-project-sort-v31-'+state.user.id,value);}catch(_){}
    renderProjectBoard();
  });
  $('#project-view-style').addEventListener('change',event=>{
    const value=event.target.value;if(!['cards','list'].includes(value))return;
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
    const performance=event.target.closest('[data-performance]');
    if(performance)openPerformance(performance.dataset.performance);
    const user=event.target.closest('[data-edit-user]');
    if(user) openUserEditor(user.dataset.editUser);
    const removedTeam=event.target.closest('[data-delete-team]');
    if(removedTeam && confirm('Delete this team? Members become unassigned and team-based project access is removed. Users and projects are kept.')) {
      api(`/api/teams/${removedTeam.dataset.deleteTeam}`,{method:'DELETE'}).then(async()=>{await loadUsers();await loadDashboard(false);toast('Team deleted');}).catch(error=>toast(error.message,true));
    }
    const team=event.target.closest('[data-edit-team]');
    if(team) openTeamEditor(team.dataset.editTeam);
    const refresh=event.target.closest('[data-refresh-estimate]');
    if(refresh && confirm('Reload the latest estimate? Unsaved fields will be discarded.')) loadProject(Number(refresh.dataset.refreshEstimate)).catch(error=>toast(error.message,true));
    const filter=event.target.closest('[data-filter]');
    if(filter) { workspaceState.filter=filter.dataset.filter; renderProjectBoard(); }
  });
}

;
/* productivity.js */
/* Productivity tools keep draft fields intact during background refreshes. */
const productivityState={tab:Array.from(crypto.getRandomValues(new Uint32Array(4))).join('-'),presence:null,presenceProject:null,busy:false,revisionProject:null,revisionVersion:null,priceItem:null,preview:null,reminderRequest:0};
async function loadReminders(){
  const uid=state.user?.id,request=++productivityState.reminderRequest;
  const result=await api('/api/reminders');
  if(uid!==state.user?.id||request!==productivityState.reminderRequest)return;
  workspaceState.reminderRows=result.reminders;
  renderSchedule();
}
function renderCollaboration(){
  const data=productivityState.presence,pid=state.projectId,box=$('#collaboration-status');
  if(!pid||productivityState.presenceProject!==pid||!data){box.innerHTML='';return;}
  const others=data.people.filter(p=>p.id!==state.user?.id);
  const changed=data.revision>Number(state.projectData?.project.revision||0);
  box.innerHTML=`<span>${others.length?`Also viewing: ${others.map(p=>escapeHtml(p.name)).join(', ')}`:'You are the only active viewer'}</span>${changed?`<div class="change-alert">${escapeHtml(data.updated_by||'A colleague')} updated this estimate. Your unsaved fields are kept. <button class="button secondary small" data-refresh-estimate="${pid}">Review latest changes</button></div>`:''}`;
}
async function pollPresence(){
  if(state.apiPendingCount||productivityState.busy||!state.user||state.user.must_change_password||document.hidden)return;
  const pid=state.view==='estimate'?state.projectId:null,uid=state.user.id;
  productivityState.busy=true;
  try{
    if(productivityState.presenceProject&&productivityState.presenceProject!==pid){
      await api(`/api/projects/${productivityState.presenceProject}/presence`,{method:'POST',body:{tab_id:productivityState.tab,leave:true}}).catch(()=>{});
      productivityState.presenceProject=null;productivityState.presence=null;
    }
    if(pid){
      const result=await api(`/api/projects/${pid}/presence`,{method:'POST',body:{tab_id:productivityState.tab}});
      if(state.user?.id===uid&&state.projectId===pid){
        productivityState.presenceProject=pid;productivityState.presence=result;
        const project=state.projectData?.project;
        const permissionChanged=typeof result.can_edit==='boolean'&&result.can_edit!==project?.can_edit;
        const changed=result.revision>Number(project?.revision||0);
        if((permissionChanged||(!project?.can_edit&&changed))&&!$('dialog[open]')){
          const scroll=window.scrollY;await loadProject(pid);window.scrollTo({top:scroll,behavior:'instant'});
        }
        renderCollaboration();
      }
    }
  }finally{productivityState.busy=false;}
}
async function loadBackups(){
  const result=await api('/api/backups');
  $('#backup-list').innerHTML=result.backups.length?result.backups.map(b=>`<article class="tool-row"><div><strong>${b.database==='tenders'?'Tenders':'Catalog / Estimator'} · ${escapeHtml(b.reason||'Backup')}</strong><small>${escapeHtml(b.created_at||b.name)} · ${(b.bytes/1048576).toFixed(1)} MB</small></div><a class="button secondary small" href="/api/backups/${encodeURIComponent(b.name)}/download">Download</a>${b.database==='tenders'?'':`<button class="button secondary small" data-restore-backup="${escapeHtml(b.name)}">Restore</button>`}</article>`).join(''):'<p>No backups yet. Daily backups are scheduled for 12:10 am server time.</p>';
}
async function openRevisions(pid){
  productivityState.revisionProject=Number(pid);
  productivityState.revisionVersion=state.projectData?.project.id===Number(pid)?state.projectData.project.revision:null;
  $('#revision-label').value='';$('#revision-comparison').innerHTML='';
  $('#revision-form').classList.toggle('hidden',!state.projectData?.project.can_edit);
  $('#revision-list').textContent='Loading…';$('#revision-dialog').showModal();
  const result=await api(`/api/projects/${pid}/revisions`);
  if(productivityState.revisionProject===Number(pid))renderRevisions(result.revisions);
}
function renderRevisions(rows){
  $('#revision-list').innerHTML=rows.length?`<label>Compare selected revision against<select id="revision-compare-target"><option value="current">Current working estimate</option>${rows.map(r=>`<option value="${r.id}">${escapeHtml(r.label)}</option>`).join('')}</select></label>`+rows.map(r=>`<article class="tool-row"><div><strong>${escapeHtml(r.label)}</strong><small>${escapeHtml(r.author||'Unknown')} · ${escapeHtml(new Date(r.created_at).toLocaleString('en-AU'))} · ${escapeHtml(r.currency)} ${fmtMoney(r.quoted,r.currency)}</small></div><div class="revision-actions"><button class="button secondary small" data-compare-revision="${r.id}">View & compare</button><a class="button secondary small" href="/api/projects/${productivityState.revisionProject}/revisions/${r.id}/export">Excel</a>${r.can_redeploy?`<button class="button secondary small" data-redeploy-revision="${r.id}" data-revision-label="${escapeHtml(r.label)}">Redeploy</button>`:''}${r.can_delete?`<button class="button secondary small danger-text" data-delete-revision="${r.id}" data-revision-label="${escapeHtml(r.label)}">Delete</button>`:''}</div></article>`).join(''):'<p>No saved revisions. Save Original before making your next changes.</p>';
}
async function compareRevision(rid){
  const pid=productivityState.revisionProject,target=$('#revision-compare-target').value;
  const result=await api(`/api/projects/${pid}/revisions/${rid}?compare=${target}`);
  if(pid!==productivityState.revisionProject)return;
  const c=result.comparison;
  function val(v){
    if(Array.isArray(v))return '<div class="table-scroll"><table class="mini-table"><thead><tr><th>Component</th><th>Qty/unit</th><th>Material</th><th>Labour</th></tr></thead><tbody>'+v.map(x=>`<tr><td>${escapeHtml(x.description)}</td><td>${fmtNumber(x.quantity_per_unit)} ${escapeHtml(x.uom)}</td><td>${fmtMoney(x.unit_material)} × ${fmtNumber(x.material_factor)}</td><td>${x.labor_pricing==='fixed'?fmtMoney(x.unit_labor_price):fmtNumber(x.unit_hours)+' hrs'} × ${fmtNumber(x.labor_factor)}</td></tr>`).join('')+'</tbody></table></div>';
    return escapeHtml(String(v??'—'));
  }
  $('#revision-comparison').innerHTML=`<h3>Comparison</h3><p>Saved: ${escapeHtml(c.before_currency)} ${fmtMoney(c.before_totals.quoted,c.before_currency)} → ${target==='current'?'Current':'Compared revision'}: ${escapeHtml(c.after_currency)} ${fmtMoney(c.after_totals.quoted,c.after_currency)}</p>${Object.entries(c.settings).map(([k,v])=>`<p><strong>${escapeHtml(k==='client'?'Builders':k.replaceAll('_',' '))}:</strong> ${val(v.before)} → ${val(v.after)}</p>`).join('')}${c.changes.length?c.changes.map(row=>`<details class="revision-change"><summary>${escapeHtml(row.kind)} · ${escapeHtml(row.name)}</summary>${Object.entries(row.fields).map(([k,v])=>`<div class="revision-field"><strong>${escapeHtml(k==='client'?'Builders':k.replaceAll('_',' '))}</strong><div class="revision-values"><section><small>Saved revision</small>${val(v.before)}</section><section><small>Compared estimate</small>${val(v.after)}</section></div></div>`).join('')}</details>`).join(''):'<p>No estimate line changes.</p>'}<details><summary>View saved estimate (${result.snapshot.lines.length} items)</summary><div class="table-scroll"><table class="mini-table"><thead><tr><th>Item</th><th>Category</th><th>Quantity</th><th>Total</th></tr></thead><tbody>${result.snapshot.lines.map(l=>`<tr><td>${escapeHtml(l.name_snapshot)}</td><td>${escapeHtml(l.category_snapshot)}</td><td>${fmtNumber(l.quantity)} ${escapeHtml(l.uom)}</td><td>${fmtMoney(l.quoted_total,c.before_currency)}</td></tr>`).join('')}</tbody></table></div></details>`;
}
function renderImportPreview(preview){
  productivityState.preview=preview;
  const box=$('#import-preview');box.classList.remove('hidden');
  box.innerHTML=`<h3>Review ${preview.name?escapeHtml(preview.name):'workbook'}</h3><p>${preview.rows.filter(r=>r.status==='new').length} new · ${preview.rows.filter(r=>r.status==='changed').length} changed prices · ${preview.rows.filter(r=>r.status==='duplicate').length} duplicates. Identical rows are skipped. Changed prices are saved as separate versions.</p><div class="inline-form"><label>Supplier<input id="import-supplier" maxlength="1000"></label><label>Quote date<input id="import-quote-date" type="date"></label><label>Source / reference<input id="import-source" maxlength="1000"></label></div><div class="inline-form"><button class="button secondary small" data-import-select="new">Select new items</button><button class="button secondary small" data-import-select="all">Select all new & changed</button><button class="button secondary small" data-import-select="none">Clear selection</button></div><div class="table-scroll import-preview-table"><table class="mini-table"><thead><tr><th>Keep</th><th>Item / sheet</th><th>Status</th><th>Existing base allowance</th><th>Incoming base allowance</th></tr></thead><tbody>${preview.rows.map(r=>`<tr><td><input type="checkbox" data-import-row="${r.key}" ${r.status==='new'?'checked':''} ${r.status==='duplicate'?'disabled':''} aria-label="Keep ${escapeHtml(r.name)}"></td><td>${escapeHtml(r.name)}<small>${escapeHtml(r.sheet)} · ${escapeHtml(r.unit)}</small></td><td>${escapeHtml(r.status)}</td><td>${previewAllowance(r.before)}</td><td>${previewAllowance(r.after)}</td></tr>`).join('')}</tbody></table></div>${preview.issues.length?`<details><summary>${preview.issues.length} parsing issues — review before importing</summary>${preview.issues.map(i=>`<p>${escapeHtml(i.sheet)} · row ${i.row_no||'—'}: ${escapeHtml(i.message)}</p>`).join('')}</details>`:''}<button class="button primary" id="commit-import-preview">Back up & import selected items</button>`;
}
function previewAllowance(a){return a?`${fmtMoney(a.material)} material · ${fmtNumber(a.hours)} hrs · ${fmtMoney(a.fixed_labor)} fixed labour`:'—';}
async function openPriceHistory(id){
  productivityState.priceItem=Number(id);$('#price-source-form').reset();$('#price-history-list').textContent='Loading…';$('#price-dialog').showModal();
  const result=await api(`/api/catalog/${id}/price-history`);if(productivityState.priceItem===Number(id))renderPriceHistory(result);
}
function renderPriceHistory(result){
  $('#price-history-list').innerHTML=result.history.map(h=>`<article class="check-row"><strong>${escapeHtml(h.snapshot.name)} · ${escapeHtml(h.supplier||'Supplier not recorded')}</strong><p>Quote date: ${escapeHtml(h.quote_date||'Not recorded')} · Source: ${escapeHtml(h.source||'Not recorded')}</p><p>Material ${fmtMoney(h.snapshot.unit_material)} · Labour ${fmtNumber(h.snapshot.unit_hours)} hrs + ${fmtMoney(h.snapshot.unit_labor_price||0)} fixed / ${escapeHtml(h.snapshot.base_uom)}</p><small>Recorded ${escapeHtml(h.created_at)} by ${escapeHtml(h.author||'System')}</small><details><summary>Component prices</summary><div class="table-scroll"><table class="mini-table"><tbody>${(h.snapshot.components||[]).map(c=>`<tr><td>${escapeHtml(c.description)}</td><td>${fmtMoney(c.unit_material)}</td><td>${componentLaborLabel(c)}</td></tr>`).join('')}</tbody></table></div></details></article>`).join('')+`<h3>Original workbook sources</h3>${result.sources.map(s=>`<p>${escapeHtml(s.file_name)} · ${escapeHtml(s.sheet_name)} · imported ${escapeHtml(s.imported_at)}</p>`).join('')||'<p>No source dates recorded.</p>'}`;
}
function bindProductivityEvents(){
  $('#refresh-backups').addEventListener('click',()=>loadBackups().catch(e=>toast(e.message,true)));
  $('#create-backup').addEventListener('click',async event=>{event.target.disabled=true;try{await api('/api/backups',{method:'POST',body:{}});await loadBackups();toast('Database backup saved');}catch(e){toast(e.message,true);}finally{event.target.disabled=false;}});
  $('#revision-form').addEventListener('submit',event=>submitWithButton(event,async()=>{const pid=productivityState.revisionProject;const result=await api(`/api/projects/${pid}/revisions`,{method:'POST',body:{label:$('#revision-label').value,expected_revision:productivityState.revisionVersion}});renderRevisions(result.revisions);$('#revision-label').value='';toast('Tender revision saved');}));
  $('#price-source-form').addEventListener('submit',event=>submitWithButton(event,async()=>{const result=await api(`/api/catalog/${productivityState.priceItem}/price-history`,{method:'POST',body:{supplier:$('#price-supplier').value,quote_date:$('#price-date').value,source:$('#price-source').value}});renderPriceHistory(result);toast('Price source recorded');}));
  document.addEventListener('click',async event=>{
    const target=event.target.closest('button');if(!target)return;
    try{
      if(target.dataset.close)$('#'+target.dataset.close).close();
      if(target.dataset.revisions)await openRevisions(target.dataset.revisions);
      if(target.dataset.compareRevision)await compareRevision(target.dataset.compareRevision);
      if(target.dataset.redeployRevision){
        if(projectSettingsBusy||projectSettingsQueued){toast('Wait for your current changes to finish saving, then reopen revisions.',true);return;}
        if(!confirm(`Redeploy “${target.dataset.revisionLabel}” as the working estimate? A safety revision of the current estimate will be saved first. Project access, deadlines and progress will stay unchanged.`))return;
        target.disabled=true;
        const pid=productivityState.revisionProject;
        await api(`/api/projects/${pid}/revisions/${target.dataset.redeployRevision}/redeploy`,{method:'POST',body:{expected_revision:productivityState.revisionVersion}});
        $('#revision-dialog').close();
        await loadDashboard(false);
        await loadProject(pid);
        toast('Revision redeployed. Previous estimate saved as a safety revision.');
      }
      if(target.dataset.deleteRevision && confirm(`Delete revision “${target.dataset.revisionLabel}”? The current estimate will stay unchanged.`)){
        target.disabled=true;
        const pid=productivityState.revisionProject;
        const result=await api(`/api/projects/${pid}/revisions/${target.dataset.deleteRevision}`,{method:'DELETE',body:{}});
        if(pid===productivityState.revisionProject){renderRevisions(result.revisions);$('#revision-comparison').innerHTML='';}
        toast('Revision deleted');
      }
      if(target.dataset.priceHistory)await openPriceHistory(target.dataset.priceHistory);
      if(target.dataset.readReminder){await api('/api/reminders/read',{method:'POST',body:{key:target.dataset.readReminder}});await loadReminders();}
      if(target.dataset.restoreBackup){
        const confirmation=prompt('Restore this backup? This replaces ALL current projects, catalogue data, users and settings. A safety backup is saved first. Everyone must sign in again. Type RESTORE to proceed.');
        if(confirmation==='RESTORE'){target.disabled=true;await api(`/api/backups/${encodeURIComponent(target.dataset.restoreBackup)}/restore`,{method:'POST',body:{confirmation}});showLogin();toast('Restored. Sign in using the accounts from the backup.');}
      }
      if(target.dataset.importSelect){
        const mode=target.dataset.importSelect;
        $$('[data-import-row]').forEach(box=>{const row=productivityState.preview.rows.find(r=>r.key===Number(box.dataset.importRow));box.checked=!box.disabled&&(mode==='all'||mode==='new'&&row.status==='new');});
      }
      if(target.id==='commit-import-preview'){
        target.disabled=true;
        try{
          const result=await api(`/api/import-previews/${productivityState.preview.token}/commit`,{method:'POST',body:{selected:$$('[data-import-row]:checked').map(b=>Number(b.dataset.importRow)),supplier:$('#import-supplier').value,quote_date:$('#import-quote-date').value,source:$('#import-source').value}});
          $('#import-preview').classList.add('hidden');$('#import-progress').textContent=`Saved ${result.report.catalog_items_created} catalogue versions. A database backup was created before import.`;
          state.catalogCache.clear();await loadDashboard(false);await loadImports();toast('Selected items imported');
        }finally{target.disabled=false;}
      }
    }catch(error){toast(error.message,true);target.disabled=false;}
  });
  setInterval(()=>pollPresence().catch(()=>{}),30000+Math.random()*5000);
  setInterval(()=>{if(state.user&&!state.user.must_change_password&&!document.hidden&&!state.apiPendingCount&&state.view==='home')loadReminders().catch(()=>{});},60000+Math.random()*10000);
}

;
/* estimate_workspace.js */
/* Estimate navigation and editing. Saved data is always updated through guarded APIs. */
const estimateViewState={collapsed:new Set(),expanded:new Set(),query:'',drag:null,busy:false};
function scopeKey(category){return `${state.projectId}:${category}`;}
// The server key is authoritative; the fallback matches Python clean_text for old snapshots.
function estimateSectionName(line){return line?.category_key||String(line?.category_snapshot??'').replace(/[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/g,' ').replace(/^ | $/g,'')||'Other';}
function fitEstimateText(){
  if(!$('#estimate-view').classList.contains('active'))return;
  const fields=$$('#estimate-lines textarea');
  fields.forEach(field=>field.style.height='auto');
  const heights=fields.map(field=>field.scrollHeight+2);
  fields.forEach((field,i)=>field.style.height=`${heights[i]}px`);
}
function renderGroupedEstimate(lines){
  const groups=new Map();
  const query=estimateViewState.query.normalize('NFKC').trim().toLowerCase();
  const matches=lines.filter(l=>!query||[l.display_name,l.name_snapshot,l.reference_name,l.notes,l.size_snapshot,l.category_snapshot,estimateSectionName(l),...(l.components||[]).map(c=>`${c.description} ${c.size}`)].join(' ').normalize('NFKC').toLowerCase().includes(query));
  for(const line of matches){const key=estimateSectionName(line);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(line);}
  const scopeTotals=new Map();
  for(const line of (state.projectData?.lines||lines)){
    const key=estimateSectionName(line),totals=scopeTotals.get(key)||{material:0,hours:0,labor:0,quoted:0};
    totals.material+=Number(line.total_material||0);totals.hours+=Number(line.total_hours||0);totals.labor+=Number(line.total_labor||0);totals.quoted+=Number(line.quoted_total||0);scopeTotals.set(key,totals);
  }
  $('#estimate-lines').innerHTML=[...groups].map(([category,items])=>{
    const totals=scopeTotals.get(category),currency=state.projectData?.project?.currency;
    const collapsed=estimateViewState.collapsed.has(scopeKey(category))&&(!query||estimateViewState.bulkCollapsed);
    const included=items[0]?.included_in_total!==false;
    return `<tr class="scope-divider ${included?'':'scope-is-excluded'}" data-scope="${escapeHtml(category)}"><td colspan="11"><div class="scope-heading-row"><button class="toggle-scope" type="button" data-scope="${escapeHtml(category)}" aria-expanded="${!collapsed}">${collapsed?'+':'−'}</button><button type="button" class="scope-inclusion" role="switch" aria-checked="${included}" data-scope="${escapeHtml(category)}" aria-label="Include ${escapeHtml(category)} in estimate total" title="${included?'Included in estimate total. Switch to optional cost.':'Optional cost, excluded from estimate total. Switch to include.'}"><span class="scope-switch-track" aria-hidden="true"></span></button><span class="drag-handle scope-drag" draggable="true" data-drag-kind="scope" data-scope="${escapeHtml(category)}" title="Drag this category above or below another">⠿</span><strong>${escapeHtml(category)}</strong><span class="scope-item-count">${items.length} items${included?'':'<small class="scope-excluded-label">Optional cost</small>'}</span><span class="scope-totals"><span class="scope-metric">Total Material <b>${fmtMoney(totals.material,currency)}</b></span><span class="scope-metric">Total Hours <b>${fmtNumber(totals.hours)} hrs</b></span><span class="scope-metric">Total Labour <b>${fmtMoney(totals.labor,currency)}</b></span><span class="scope-metric scope-quoted">Quoted Total <b>${fmtMoney(totals.quoted,currency)}</b></span></span><span class="scope-order-actions"><button type="button" class="scope-move" data-scope="${escapeHtml(category)}" data-direction="-1" aria-label="Move ${escapeHtml(category)} up" title="Move category up">↑</button><button type="button" class="scope-move" data-scope="${escapeHtml(category)}" data-direction="1" aria-label="Move ${escapeHtml(category)} down" title="Move category down">↓</button><button type="button" class="scope-delete danger-text" data-scope="${escapeHtml(category)}" aria-label="Delete ${escapeHtml(category)} section" title="Delete whole section">×</button></span></div></td></tr>`+(collapsed?'':items.map(renderEstimateLine).join(''));
  }).join('');
  if(query&&!matches.length)$('#estimate-lines').innerHTML='<tr><td colspan="11" class="scope-empty">No matching item in this estimate.</td></tr>';
  for(const id of estimateViewState.expanded){
    $$(`.detail-row[data-parent="${id}"]`).forEach(row=>row.classList.remove('hidden-row'));
    const toggle=$(`.toggle-details[data-line-id="${id}"]`);if(toggle){toggle.textContent='−';toggle.setAttribute('aria-expanded','true');}
  }
  const names=scopeNames();
  $$('.scope-move').forEach(button=>{const at=names.indexOf(button.dataset.scope);button.disabled=!names[at+Number(button.dataset.direction)]||!state.projectData?.project?.can_edit;});
  fitEstimateText();
  syncCategoryToggle();
  syncExpandEstimateAll();
  if(state.projectData?.project?.can_edit===false){
    $$('#estimate-lines input, #estimate-lines textarea, #estimate-lines select, #estimate-lines button').forEach(field=>field.disabled=!field.matches('.toggle-details,.toggle-scope'));
  }
  $('#estimate-line-count').textContent=query?`${matches.length} of ${lines.length} items`:`${lines.length} items`;
  $('#floating-bottom-button').classList.toggle('hidden',state.view!=='estimate'||!state.projectId);
}
async function estimateOperation(path,payload,record){
  if(estimateViewState.busy){toast('Please wait for the current change to finish.');return;}
  if(!state.projectData?.project?.can_edit)throw new Error('This estimate is read-only');
  estimateViewState.busy=true;
  const pid=state.projectId,before=state.projectData,table=$('#estimate-lines');
  table.inert=true;table.setAttribute('aria-busy','true');
  const reorder=/\/projects\/\d+\/reorder$/.test(path);
  if(reorder){
    const rows=new Map(before.lines.map(line=>[line.id,line]));
    state.projectData={...before,lines:payload.ids.map(id=>rows.get(id))};
    renderGroupedEstimate(state.projectData.lines);
  }
  try{
    const result=await api(path,{method:'POST',body:{...payload,expected_revision:record.revision}});
    if(state.projectId===pid && Number(result.project.revision)>=Number(state.projectData?.project?.revision||0)){state.projectData=result;if(Array.isArray(state.projects)){const index=state.projects.findIndex(p=>p.id===pid);if(index>=0)state.projects[index]={...state.projects[index],...result.project,totals:result.totals};}if(reorder)renderGroupedEstimate(result.lines);else renderProject();}
  }catch(error){
    if(state.projectId===pid&&reorder&&state.projectData?.project?.revision===before.project.revision){state.projectData=before;renderGroupedEstimate(before.lines);}
    throw error;
  }finally{estimateViewState.busy=false;table.inert=false;table.removeAttribute('aria-busy');}
}

function lineById(id){return state.projectData.lines.find(l=>l.id===Number(id));}
async function deleteSearchItem(id){
  const item=await fetchCatalogItem(id);
  if(!confirm(`Delete "${item.display_name||cleanEstimateTitle(item.name)}" from the catalog? Saved estimates keep their descriptions and prices. Only this version is deleted.`))return;
  await api(`/api/catalog/${id}`,{method:'DELETE',body:{}});
  state.catalogCache.clear();clearSmartSearch();hideCatalogHover(0);
  if(state.currentCatalogItem?.id===Number(id)){state.currentCatalogItem=null;$('#catalog-detail').innerHTML='Select another catalog item.';}
  await loadDashboard();toast('Catalog item deleted; saved estimates are preserved.');
}
async function copyProject(id){
  const result=await api(`/api/projects/${Number(id)}`);
  openProjectForm(result.project);
}
function moveId(ids,id,target,after){const result=ids.filter(x=>x!==id),at=result.indexOf(target);result.splice(at+(after?1:0),0,id);return result;}

function scopeNames(){return [...new Set((state.projectData?.lines||[]).map(l=>estimateSectionName(l)))];}
async function moveScope(source,target,after){
  if(estimateViewState.busy){toast('Please wait for the current change to finish.');return;}
  const names=scopeNames();if(source===target||!names.includes(source)||!names.includes(target))return;
  const scope_order=moveId(names,source,target,after);
  const ids=scope_order.flatMap(category=>state.projectData.lines.filter(l=>(estimateSectionName(l))===category).map(l=>l.id));
  await estimateOperation(`/api/projects/${state.projectId}/reorder`,{ids,scope_order},state.projectData.project);
  toast('Category order saved');
}
function clearDropHint(){$$('.drop-before,.drop-after').forEach(row=>row.classList.remove('drop-before','drop-after'));}

document.addEventListener('DOMContentLoaded',()=>{
  new MutationObserver(fitEstimateText).observe($('#estimate-view'),{attributes:true,attributeFilter:['class']});
  if(typeof window!=='undefined')window.addEventListener('resize',fitEstimateText);
  $('#floating-bottom-button').addEventListener('click',()=>$('#estimate-lines').closest('section').scrollIntoView({behavior:'smooth',block:'end'}));
  // Visibility follows the existing floating search control when changing views.
  new MutationObserver(()=>$('#floating-bottom-button').classList.toggle('hidden',$('#floating-search-button').classList.contains('hidden'))).observe($('#floating-search-button'),{attributes:true,attributeFilter:['class']});
  $('#find-estimate-button').addEventListener('click',()=>{$('#estimate-find-input').classList.remove('hidden');$('#estimate-find-input').focus();});
  $('#estimate-find-input').addEventListener('input',event=>{estimateViewState.query=event.target.value;estimateViewState.bulkCollapsed=false;renderGroupedEstimate(state.projectData?.lines||[]);});
  document.addEventListener('click',event=>{
    const copy=event.target.closest('[data-copy-project]');if(copy)copyProject(copy.dataset.copyProject).catch(error=>toast(error.message,true));
    const del=event.target.closest('.search-delete-item');if(del)deleteSearchItem(del.dataset.id).catch(error=>toast(error.message,true));
  });
  $('#estimate-lines').addEventListener('input',event=>{if(event.target.matches('textarea')){event.target.style.height='auto';event.target.style.height=`${event.target.scrollHeight+2}px`;}});
  $('#estimate-lines').addEventListener('click',event=>{
    const inclusion=event.target.closest('.scope-inclusion');
    if(inclusion){
      const category=inclusion.dataset.scope,included=inclusion.getAttribute('aria-checked')!=='true';
      estimateOperation(`/api/projects/${state.projectId}/sections/inclusion`,{category,included},state.projectData.project).then(()=>{const replacement=[...$$('.scope-inclusion')].find(button=>button.dataset.scope===category);replacement?.focus({preventScroll:true});toast(`${category} ${included?'included in estimate total':'saved as optional cost'}`);}).catch(error=>toast(error.message,true));
      return;
    }
    const sectionDelete=event.target.closest('.scope-delete');
    if(sectionDelete){
      const category=sectionDelete.dataset.scope,count=state.projectData.lines.filter(l=>(estimateSectionName(l))===category).length;
      if(confirm(`Delete the whole “${category}” section and all ${count} items from this estimate? A safety revision will be saved first. Catalogue items stay unchanged.`))estimateOperation(`/api/projects/${state.projectId}/sections/remove`,{category},state.projectData.project).then(()=>toast('Section removed. Restore its safety revision from Revisions if needed.')).catch(error=>toast(error.message,true));
      return;
    }
    const move=event.target.closest('.scope-move');
    if(move){const names=scopeNames(),at=names.indexOf(move.dataset.scope),direction=Number(move.dataset.direction);if(names[at+direction])moveScope(move.dataset.scope,names[at+direction],direction>0).catch(error=>toast(error.message,true));return;}
    const scope=event.target.closest('.toggle-scope');
    if(scope){const key=scopeKey(scope.dataset.scope);if(estimateViewState.collapsed.has(key))estimateViewState.collapsed.delete(key);else estimateViewState.collapsed.add(key);renderGroupedEstimate(state.projectData.lines);return;}

    const copy=event.target.closest('.copy-estimate-line');
    if(copy){const line=lineById(copy.dataset.lineId);estimateOperation(`/api/projects/${state.projectId}/lines/${line.id}/copy`,{},line).catch(error=>toast(error.message,true));}
    const remove=event.target.closest('.component-remove-live');
    if(remove){const line=lineById(remove.dataset.lineId);estimateViewState.expanded.add(line.id);estimateOperation(`/api/projects/${state.projectId}/lines/${line.id}/components/${remove.dataset.componentId}/remove`,{},line).then(()=>toast('Component removed from this estimate only')).catch(error=>toast(error.message,true));return;}
    const component=event.target.closest('.component-copy-live');
    if(component){const line=lineById(component.dataset.lineId);estimateViewState.expanded.add(line.id);estimateOperation(`/api/projects/${state.projectId}/lines/${line.id}/components/${component.dataset.componentId}/copy`,{},line).catch(error=>toast(error.message,true));}
  });
  $('#manual-components').addEventListener('click',event=>{
    const copy=event.target.closest('.copy-manual-component');if(!copy)return;
    const row=copy.closest('.manual-component'),rows=$$('#manual-components .manual-component');
    const component=readManualComponents()[rows.indexOf(row)];row.insertAdjacentHTML('afterend',componentRow({...component,is_parent:0,is_supply_copy:component.is_supply_copy||(['Lighting','Emergency & Exit Lighting'].includes($('#manual-category').value)&&component.is_parent?1:0)}));refreshManualPricing();
  });
  document.addEventListener('dragstart',event=>{
    const handle=event.target.closest('.drag-handle');if(!handle)return;
    const kind=handle.dataset.dragKind;
    if(kind!=='manual'&&(estimateViewState.busy||!state.projectData?.project?.can_edit)){event.preventDefault();return;}
    estimateViewState.drag={kind,scope:handle.dataset.scope,lineId:Number(handle.dataset.lineId),componentId:Number(handle.dataset.componentId),row:handle.closest('tr')};
    event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',kind);
  });
  document.addEventListener('dragover',event=>{const row=event.target.closest('#estimate-lines tr, #manual-components tr');if(estimateViewState.drag&&row){event.preventDefault();event.dataTransfer.dropEffect='move';clearDropHint();const after=event.clientY>row.getBoundingClientRect().top+row.getBoundingClientRect().height/2;row.classList.add(after?'drop-after':'drop-before');}});
  document.addEventListener('drop',event=>{
    const drag=estimateViewState.drag;if(!drag)return;estimateViewState.drag=null;clearDropHint();
    const row=event.target.closest('tr');if(!row)return;event.preventDefault();
    const after=event.clientY>row.getBoundingClientRect().top+row.getBoundingClientRect().height/2;
    if(drag.kind==='scope'){
      let category=row.dataset.scope;
      if(row.matches('.assembly-row'))category=estimateSectionName(lineById(row.dataset.lineId));
      if(row.matches('.detail-row'))category=estimateSectionName(lineById(row.dataset.parent));
      if(category)moveScope(drag.scope,category,after).catch(error=>toast(error.message,true));return;
    }
    if(drag.kind==='manual'){
      if(!row.matches('.manual-component')||row===drag.row)return;
      row.insertAdjacentElement(after?'afterend':'beforebegin',drag.row);refreshManualPricing();return;
    }
    let path,payload,record;
    if(drag.kind==='line'){
      if(!row.matches('.assembly-row,.detail-row'))return;
      const target=lineById(row.dataset.lineId||row.dataset.parent),source=lineById(drag.lineId);if(target.id===source.id)return;
      if(estimateSectionName(target)!==estimateSectionName(source)){toast('Move items within the same scope. Change Category to move between scopes.');return;}
      payload={ids:moveId(state.projectData.lines.map(l=>l.id),source.id,target.id,after)};record=state.projectData.project;path=`/api/projects/${state.projectId}/reorder`;
    } else {
      if(!row.matches('.detail-row')||Number(row.dataset.parent)!==drag.lineId)return;
      const line=lineById(drag.lineId),target=Number(row.dataset.componentId);if(target===drag.componentId)return;
      payload={ids:moveId(line.components.map(c=>c.id),drag.componentId,target,after)};record=line;path=`/api/projects/${state.projectId}/lines/${line.id}/components/reorder`;
    }
    estimateOperation(path,payload,record).catch(error=>toast(error.message,true));
  });
  document.addEventListener('dragend',()=>{estimateViewState.drag=null;clearDropHint();});
});

function syncExpandEstimateAll(){
 const button=$('#expand-estimate-all');if(!button)return;
 const lines=state.projectData?.lines||[];
 const all=lines.length>0&&lines.every(l=>!estimateViewState.collapsed.has(scopeKey(estimateSectionName(l)))&&estimateViewState.expanded.has(l.id));
 button.textContent=all?'Shrink All':'Expand All';button.setAttribute('aria-expanded',String(all));button.disabled=!lines.length;
}
$('#expand-estimate-all')?.addEventListener('click',()=>{
 const lines=state.projectData?.lines||[],shrink=$('#expand-estimate-all').getAttribute('aria-expanded')==='true';
 for(const line of lines){const key=scopeKey(estimateSectionName(line));if(shrink){estimateViewState.collapsed.add(key);estimateViewState.expanded.delete(line.id);}else{estimateViewState.collapsed.delete(key);estimateViewState.expanded.add(line.id);}}
 estimateViewState.bulkCollapsed=shrink;renderGroupedEstimate(lines);
});

;
/* navigation.js */
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

;
/* help_chat.js */
/* Shared, account-scoped assistant for Estimator and Tenders. */
(function(){
 let user=null,csrf='',busy=false,generation=0,chatMode='project';
 const el=id=>document.getElementById(id);
 async function request(path,body){const r=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-ConEst-Request':'1','X-CSRF-Token':csrf},...(body===undefined?{}:{body:JSON.stringify(body)})});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d;}
 function message(text,kind,sources=[]){const article=document.createElement('div');article.className='help-message '+kind;const p=document.createElement('p');p.textContent=text;article.append(p);for(const source of sources){if(!/^#\/(catalog|estimate|light-prices)\/\d+$/.test(source.url)&&source.url!=='/tenders/chase-up')continue;const a=document.createElement('a');a.href=source.url.startsWith('#')?'/'+source.url:source.url;a.textContent=source.label;a.className='help-source-link';article.append(a);}el('help-chat-messages').append(article);el('help-chat-messages').scrollTop=el('help-chat-messages').scrollHeight;return article;}
 function renderMemory(data){if(data.models){const select=el('help-model'),previous=select.value;select.replaceChildren(new Option('App default',''));for(const model of data.models)select.add(new Option(model,model));select.value=previous;}el('help-chat-messages').textContent='';for(const m of data.messages||[])message(m.text,m.role,m.sources||[]);el('help-memory-note').value=data.note||'';el('help-documents').textContent='';for(const d of data.documents||[]){const row=document.createElement('div');row.textContent=d.name+' · '+d.characters.toLocaleString()+' text characters ';const remove=document.createElement('button');remove.type='button';remove.className='button secondary small';remove.textContent='Remove';remove.onclick=async()=>{try{renderMemory(await request('/api/assistant/memory',{removeDocument:d.id}));}catch(e){message(e.message,'answer');}};row.append(remove);el('help-documents').append(row);}}
 function pageContext(){if(typeof state!=='undefined'){return {page:state.view,project_id:state.view==='estimate'?state.projectId:null,catalog_item_id:state.view==='catalog'?state.currentCatalogItem?.id:null,light_group_id:state.view==='light-prices'&&typeof lightPriceState!=='undefined'?lightPriceState.selected:null};}return {page:'tenders'};}
 async function open(){try{const session=await request('/api/auth/session');if(!session.user||session.user.must_change_password)throw Error('Complete sign-in before using Help.');user=session.user;csrf=session.csrf_token;generation++;el('help-chat-dialog').showModal();renderMemory(await request('/api/assistant/memory'));el('help-chat-question').focus();}catch(e){if(el('help-chat-dialog').open)message(e.message,'answer');else alert(e.message);}}
 function resetHelpChat(){generation++;user=null;csrf='';if(el('help-chat-dialog')){el('help-chat-dialog').close();el('help-chat-messages').textContent='';el('help-memory-note').value='';el('help-documents').textContent='';}}
 window.resetHelpChat=resetHelpChat;
 function init(){
  el('help-chat-dialog')?.remove();el('help-chat-button')?.remove();
  const host=document.createElement('div');host.innerHTML=`<button id="help-chat-button" class="help-chat-launch" type="button">? <span>Help</span></button><dialog id="help-chat-dialog" class="help-chat-dialog" aria-labelledby="help-chat-title"><header class="help-chat-heading"><div><h2 id="help-chat-title">TEC ConEst Help</h2><p>Estimator · Tenders · Documents</p></div><nav class="help-header-actions"><button id="help-mode-button" type="button" class="button secondary small" aria-label="Switch to Normal chat">Project</button><button id="help-settings-button" type="button" class="button secondary small" aria-expanded="false" aria-controls="help-settings">Settings</button><button id="help-clear-memory" type="button" class="button secondary small">Clear</button><button id="close-help-chat" class="button secondary small" type="button">Close</button></nav></header><section id="help-settings" class="help-memory" hidden><h3>Help settings</h3><label class="help-ai-choice"><input type="checkbox" id="help-use-ai">Use configured Gemini — sends question, relevant records, memory and document excerpts</label><label>Memory<textarea id="help-memory-note" maxlength="2000" rows="2" placeholder="Your preferences or working context"></textarea></label><button id="help-save-memory" type="button" class="button secondary small">Save memory</button><h4>Attachments</h4><div id="help-documents"></div><small>Up to 3 files, 10 MB each. Text PDF, XLSX, DOCX, TXT, CSV, JSON, MD. Reads up to 60,000 characters per file; scanned PDFs need OCR.</small><button id="help-reset-memory" class="button secondary small" type="button">Reset memory, files & conversation</button></section><main id="help-chat-messages" class="help-chat-messages" role="log" aria-live="polite"></main><form id="help-chat-form"><div class="help-chat-compose"><button id="help-attach-button" class="button secondary small" type="button" aria-label="Attach a file" title="Attach a file">+</button><input id="help-file" type="file" accept=".pdf,.xlsx,.docx,.txt,.csv,.json,.md" hidden><textarea id="help-chat-question" aria-label="Your question" rows="2" maxlength="1000" required placeholder="Ask anything about your estimates, tenders or files…"></textarea><button id="send-help-chat" class="button primary" type="submit" aria-label="Send message">↑</button></div><div class="help-compose-options"><label>Model <select id="help-model" aria-label="Chat model"><option value="">App default</option></select></label><span id="help-mode-description">Project chat · searches workspace records</span></div><p class="help-composer-note">Enter to send · Shift+Enter for a new line · Read-only answers</p></form></dialog>`;document.body.append(host);
  el('help-chat-button').onclick=open;el('close-help-chat').onclick=()=>el('help-chat-dialog').close();
  const app=el('authenticated-app');if(app){const sync=()=>{const active=typeof state!=='undefined'&&state.user&&!state.user.must_change_password;el('help-chat-button').classList.toggle('hidden',!active);if(!active)resetHelpChat();};new MutationObserver(sync).observe(app,{attributes:true,attributeFilter:['class']});sync();}
  el('help-save-memory').onclick=async()=>{try{await request('/api/assistant/memory',{note:el('help-memory-note').value});message('Memory saved.','answer');}catch(e){message(e.message,'answer');}};
  el('help-clear-memory').onclick=async()=>{try{generation++;renderMemory(await request('/api/assistant/memory',{clearConversation:true}));}catch(e){message(e.message,'answer');}};
  el('help-reset-memory').onclick=async()=>{try{generation++;renderMemory(await request('/api/assistant/memory',{clear:true}));}catch(e){message(e.message,'answer');}};
  el('help-settings-button').onclick=()=>{const panel=el('help-settings');panel.hidden=!panel.hidden;el('help-settings-button').setAttribute('aria-expanded',String(!panel.hidden));};
  el('help-mode-button').onclick=()=>{chatMode=chatMode==='project'?'normal':'project';el('help-mode-button').textContent=chatMode==='project'?'Project':'Normal';el('help-mode-button').setAttribute('aria-label','Switch to '+(chatMode==='project'?'Normal':'Project')+' chat');el('help-mode-description').textContent=chatMode==='project'?'Project chat · searches workspace records':'Normal chat · no workspace lookup';el('help-chat-question').placeholder=chatMode==='project'?'Ask about your estimates, tenders or files…':'Ask a general question…';};
  el('help-attach-button').onclick=()=>el('help-file').click();
  el('help-chat-question').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();el('help-chat-form').requestSubmit();}});
  el('help-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;e.target.disabled=true;try{if(file.size>10*1024*1024)throw Error('Choose a file up to 10 MB.');const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Cannot read file'));reader.readAsDataURL(file);});renderMemory(await request('/api/assistant/document',{name:file.name,content}));message('File ready. Ask a question about '+file.name+'.','answer');}catch(error){message(error.message,'answer');}finally{e.target.disabled=false;e.target.value='';}};
  el('help-chat-form').onsubmit=async e=>{e.preventDefault();if(busy)return;const question=el('help-chat-question').value.trim();if(!question)return;busy=true;const token=generation;el('send-help-chat').disabled=true;message(question,'question');el('help-chat-question').value='';const pending=message('Reading…','answer');try{const d=await request('/api/assistant/chat',{question,chatMode,model:el('help-model').value,scope:'auto',useAI:el('help-use-ai').checked,...pageContext()});if(token!==generation)return;pending.remove();message(d.answer+'\n\n'+d.mode,'answer',d.sources||[]);}catch(error){if(token===generation)pending.textContent=error.message;}finally{busy=false;el('send-help-chat').disabled=false;}};
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();

;
/* estimate_extras.js */
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
  $('#floating-estimate-total').classList.toggle('hidden',state.view!=='estimate'||!state.projectId);
}
document.addEventListener('DOMContentLoaded',()=>{
  ['#project-hours-per-day','#project-crew-size'].forEach(selector=>$(selector).addEventListener('input',previewEstimateTimeSummary));
  document.addEventListener('click',event=>{const button=event.target.closest('[data-password-target]');if(!button)return;const input=document.getElementById(button.dataset.passwordTarget),show=input.type==='password';input.type=show?'text':'password';if(!button.classList.contains('login-eye'))button.textContent=show?'Hide':'Show';button.setAttribute('aria-pressed',String(show));button.setAttribute('aria-label',show?'Hide password':'Show password');});
  document.addEventListener('submit',event=>{event.target.querySelectorAll('[data-password-target]').forEach(button=>{document.getElementById(button.dataset.passwordTarget).type='password';if(!button.classList.contains('login-eye'))button.textContent='Show';button.setAttribute('aria-pressed','false');button.setAttribute('aria-label','Show password');});},true);
  window.addEventListener('scroll',refreshFloatingTotal,{passive:true});window.addEventListener('resize',refreshFloatingTotal);
  new MutationObserver(refreshFloatingTotal).observe($('#estimate-view'),{attributes:true,attributeFilter:['class']});
  $('#floating-estimate-total').addEventListener('click',()=>$('#metric-quoted').scrollIntoView({behavior:'smooth',block:'center'}));
  $('#toggle-all-categories').addEventListener('click',()=>{
    const lines=state.projectData?.lines||[];
    const allCollapsed=lines.length>0&&lines.every(line=>estimateViewState.collapsed.has(scopeKey(estimateSectionName(line))));
    estimateViewState.bulkCollapsed=!allCollapsed;
    for(const line of lines){const key=scopeKey(estimateSectionName(line));if(allCollapsed)estimateViewState.collapsed.delete(key);else estimateViewState.collapsed.add(key);}
    renderGroupedEstimate(lines);
  });
});
function syncCategoryToggle(){
  const button=$('#toggle-all-categories'),lines=state.projectData?.lines||[];
  button.classList.toggle('hidden',state.view!=='estimate'||!state.projectId);
  button.disabled=!lines.length;
  const collapsed=lines.length>0&&lines.every(line=>estimateViewState.collapsed.has(scopeKey(estimateSectionName(line))));
  const label=collapsed?'Expand all categories':'Collapse all categories';
  button.textContent=collapsed?'+':'−';
  button.title=label;button.setAttribute('aria-label',label);button.setAttribute('aria-expanded',String(!collapsed));
}

;
/* light_prices.js */
/* Quoted lighting packages: inline details, explicit arithmetic, editable working copies. */
const lightPriceState={request:0,detailRequest:0,offset:0,total:0,selected:null,item:null,results:[],suppliers:[],editing:false,dirty:false,busy:false,photoDataUrl:null,removePhoto:false,photoLoading:false,photoReadId:0};
function renderSupplierPicker(options){
  const active=document.activeElement,preserve=$('#light-price-supplier').contains(active)&&active.matches('input'),all=active?.dataset?.allSuppliers!==undefined,activeValue=active?.value;
  lightPriceState.supplierOptions=options;
  const selected=lightPriceState.suppliers;
  $('#light-price-supplier summary').textContent=selected.length===0?'All suppliers':selected.length===1?selected[0]:`${selected.length} suppliers`;
  $('#light-price-supplier .supplier-choices').innerHTML=`<label><input type="checkbox" data-all-suppliers ${selected.length?'':'checked'}>All suppliers</label>`+options.map(s=>`<label><input type="checkbox" data-supplier value="${escapeHtml(s)}" ${selected.includes(s)?'checked':''}>${escapeHtml(s)}</label>`).join('');
  filterSupplierOptions();
  if(preserve){const control=$$('#light-price-supplier input').find(el=>all?el.dataset.allSuppliers!==undefined:el.value===activeValue);control?.focus();}
}
function filterSupplierOptions(){
  const term=$('#supplier-filter').value.trim().toLocaleLowerCase();
  $$('#light-price-supplier .supplier-choices label').forEach(label=>{label.hidden=!label.querySelector('[data-all-suppliers]')&&!label.textContent.toLocaleLowerCase().includes(term);});
  const box=$('#light-price-supplier .supplier-choices');box.querySelector('.supplier-no-match')?.remove();
  if(!$$('#light-price-supplier input[data-supplier]').some(el=>!el.parentElement.hidden))box.insertAdjacentHTML('beforeend','<p class="supplier-no-match helper-text">No matching suppliers.</p>');
}
function lightMoney(value){return value===null||value===undefined?'Not priced':fmtMoney(value,'AUD');}
function lightRate(value){return value===null||value===undefined?'Not priced':new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD',minimumFractionDigits:2,maximumFractionDigits:4}).format(value);}
function lightQty(value){return value===null||value===undefined?'Not set':fmtNumber(value,4);}
function lightPhotoURL(item){return `/api/light-prices/${item.id}/photo?v=${item.revision||0}`;}
function resetLightPrices(){
  if(typeof resetQuoteReview==='function')resetQuoteReview();
  $('#light-price-import-form').reset();$('#light-price-import-status').textContent='';
  lightPriceState.request++;lightPriceState.detailRequest++;
  Object.assign(lightPriceState,{selected:null,item:null,results:[],suppliers:[],editing:false,dirty:false,busy:false,photoDataUrl:null,removePhoto:false,photoLoading:false,photoReadId:(lightPriceState.photoReadId||0)+1});
  const box=$('#light-price-detail');box.classList.add('hidden');$('#light-prices-view').appendChild(box);box.innerHTML='';
  $('#light-price-results').innerHTML='';$('#light-price-search').value='';$('#supplier-filter').value='';renderSupplierPicker([]);
}
function confirmLightDiscard(){return !lightPriceState.dirty||confirm('Discard the unsaved changes to this light?');}
function closeLightPrice(remember=true){
  if(lightPriceState.busy||!confirmLightDiscard())return false;
  lightPriceState.detailRequest++;
  Object.assign(lightPriceState,{selected:null,item:null,editing:false,dirty:false,photoDataUrl:null,removePhoto:false,photoLoading:false,photoReadId:(lightPriceState.photoReadId||0)+1});
  const box=$('#light-price-detail');box.classList.add('hidden');$('#light-prices-view').appendChild(box);box.innerHTML='';
  $$('.light-price-card').forEach(card=>card.setAttribute('aria-expanded','false'));
  $$('.light-price-result').forEach(card=>card.classList.remove('is-expanded'));
  if(remember)rememberPage('light-prices',null);
  return true;
}
function lightCard(item){
  const warnings=[item.missing_prices?`${item.missing_prices} unpriced included row(s)`:null,item.difference_count?`${item.difference_count} row total(s) differ from qty x rate`:null,!item.included_count?'No rows included':null].filter(Boolean);
  return `<a class="light-price-card" href="#/light-prices/${item.id}" data-light-open="${item.id}" aria-expanded="false"><div class="light-card-main">${item.has_photo?`<img class="light-card-photo" src="${lightPhotoURL(item)}" alt="" loading="lazy">`:'<span class="light-card-placeholder" aria-hidden="true">&#9788;</span>'}<div><strong>${escapeHtml(item.description)}</strong>${item.nickname?`<span class="light-nickname">${escapeHtml(item.nickname)}</span>`:''}<small>${escapeHtml(item.supplier||'Supplier not set')} &middot; ${escapeHtml(item.cat_no||'No catalogue number')}</small><small>${escapeHtml(item.project||'Project not set')} &middot; ${escapeHtml(item.quote_date||'Date not set')} &middot; ${escapeHtml(item.reference)}</small>${warnings.map(text=>`<small class="light-caution">${escapeHtml(text)}</small>`).join('')}</div></div><div class="light-price-card-cost"><span>Package supply / ${escapeHtml(item.primary_unit||'primary unit')} (ex GST)</span><b>${lightMoney(item.connected_unit_ex)}</b><small>${item.missing_prices?'Partial included total':'Included row total'} ${lightMoney(item.connected_total_ex)} &divide; ${lightQty(item.base_qty)}</small><small>${item.included_count} of ${item.component_count} rows included &middot; <span class="light-expand-text">Details / edit &#9662;</span></small></div></a>`;
}
async function loadLightPrices(offset=0){
  if(lightPriceState.busy||!confirmLightDiscard())return false;
  const request=++lightPriceState.request;lightPriceState.detailRequest++;
  const query=$('#light-price-search').value.trim(),suppliers=[...lightPriceState.suppliers];
  $('#light-price-status').textContent='Searching supplier quotes...';
  const data=await api(`/api/light-prices?q=${encodeURIComponent(query)}&offset=${offset}${suppliers.map(s=>'&supplier='+encodeURIComponent(s)).join('')}`);
  if(request!==lightPriceState.request)return false;
  lightPriceState.dirty=false;closeLightPrice(false);
  Object.assign(lightPriceState,{offset,total:data.total,results:data.results});
  renderSupplierPicker(data.suppliers||[]);
  $('#light-price-status').textContent=data.total?`${offset+1}-${offset+data.results.length} of ${data.total} matches. Click a result to expand it here.`:'No matches. Try a name, nickname, supplier or catalogue number.';
  $('#light-price-results').innerHTML=data.results.map(item=>`<article class="light-price-result" data-light-id="${item.id}">${lightCard(item)}</article>`).join('');
  $('#light-price-prev').disabled=offset===0;$('#light-price-next').disabled=offset+data.results.length>=data.total;
  if(state.view==='light-prices')rememberPage('light-prices',null,true);
  return true;
}
function lightTotals(item){
  return `<div class="light-total-grid"><div><span>Main row unit rate</span><strong>${lightRate(item.main_row_unit_ex)}</strong><small>Not the combined package price</small></div><div><span>${item.missing_prices?'Partial included row total':'Included row total'}</span><strong>${lightMoney(item.connected_total_ex)}</strong><small>${item.included_count} of ${item.component_count} rows included</small></div><div><span>Division quantity</span><strong>${lightQty(item.base_qty)}</strong><small>${escapeHtml(item.primary_unit||'primary unit')}(s)</small></div><div class="light-package-total"><span>Package supply / ${escapeHtml(item.primary_unit||'primary unit')}</span><strong>${lightRate(item.connected_unit_ex)}</strong><small>AUD excluding GST</small></div></div><p class="light-formula">${item.connected_unit_ex===null?'A complete package unit price is unavailable. Check the included rows and division quantity.':`${lightMoney(item.connected_total_ex)} included row total &divide; ${lightQty(item.base_qty)} ${escapeHtml(item.primary_unit||'primary unit')}(s) = <strong>${lightRate(item.connected_unit_ex)} per ${escapeHtml(item.primary_unit||'primary unit')}</strong>`}</p>`;
}
function lightWarnings(item){
  const messages=[];
  if(item.missing_prices)messages.push(`${item.missing_prices} included row(s) have no usable total. The sum is partial, and the package unit price is deliberately withheld. A blank price is not treated as a quoted zero.`);
  if(!item.base_qty||item.base_qty<0)messages.push('The division quantity is missing or zero. Enter the number of primary units before calculating a package unit price.');
  if(!item.included_count)messages.push('No component rows are included in this package.');
  if(item.difference_count)messages.push(`${item.difference_count} included quoted row total(s) differ from quantity x rate. The selected quoted totals are used, not silently replaced. Change the total basis in Edit details when appropriate.`);
  if(item.implicit_links)messages.push(`${item.implicit_links} included row(s) were linked to the preceding light because the source type was blank. Check that accessories or freight belong to this light; untick Include when they do not.`);
  if(item.base_differs)messages.push('The division quantity differs from the first row quantity. This may be intentional for sets or lengths; confirm the correct package basis.');
  return messages.length?`<div class="light-warning-box" role="note">${messages.map(message=>`<p>${escapeHtml(message)}</p>`).join('')}</div>`:'';
}
function lightReadTable(item){
  return `<div class="table-scroll"><table class="mini-table light-calculation-table"><caption>All amounts are AUD ex GST. Only included rows contribute. Per-primary amounts show up to 4 decimals; displayed rounding can differ slightly from the unrounded division.</caption><thead><tr><th>Include</th><th>Component / source</th><th>Quote qty</th><th>Unit rate</th><th>Qty &times; rate</th><th>Quoted row total</th><th>Total used</th><th>Qty / primary</th><th>Cost / primary</th></tr></thead><tbody>${item.components.map((c,index)=>`<tr class="${c.included?'':'light-excluded'}"><td>${c.included?'&#10003; Yes':'&#10007; No'}</td><td><strong>${escapeHtml(c.description)}</strong><small>${escapeHtml(c.supplier)} &middot; ${escapeHtml(c.cat_no)}</small><small>Row ${index+1} &middot; ${c.page?`PDF page ${c.page}`:'Manual / workbook row'} &middot; ${escapeHtml(c.connection_basis||'Imported connection')}</small>${c.status?`<small>${escapeHtml(c.status)}</small>`:''}</td><td>${lightQty(c.quantity)}</td><td>${lightRate(c.unit_ex)}</td><td>${lightMoney(c.calculated_total_ex)}</td><td>${lightMoney(c.total_ex)}${c.has_difference?`<small class="light-caution">Difference ${c.difference_ex>0?'+':''}${lightMoney(c.difference_ex)}</small>`:''}</td><td><strong>${c.included?lightMoney(c.resolved_total_ex):'Excluded'}</strong><small>${c.total_mode==='calculated'?'Qty x rate':'Quoted total'}</small></td><td>${lightQty(c.quantity_per_primary)}</td><td>${c.included?lightRate(c.contribution_unit_ex):'Excluded'}</td></tr>`).join('')}</tbody><tfoot><tr><th colspan="6">${item.missing_prices?'Partial sum of included totals':'Sum of included totals'}</th><th>${lightMoney(item.connected_total_ex)}</th><th>&divide; ${lightQty(item.base_qty)}</th><th>${lightRate(item.connected_unit_ex)}</th></tr></tfoot></table></div>`;
}
function lightSource(item){
  return `<details class="light-source-record"><summary>Original import / audit information</summary><p class="helper-text">Source: ${escapeHtml(item.source||'Not recorded')}<br>Original quote: ${escapeHtml(item.original_reference||'')} &middot; ${escapeHtml(item.original_project||'')} &middot; ${escapeHtml(item.original_quote_date||'')}<br>${item.edit_count||0} saved edit(s). ${item.updated_at?`Last saved ${escapeHtml(item.updated_at)}${item.edited_by?' by '+escapeHtml(item.edited_by):''}.`:''} Working edits stay in this price library; the source PDF and shared estimating catalogue are not changed.</p><div class="table-scroll"><table class="mini-table"><thead><tr><th>Row</th><th>Original description / cat no</th><th>Original qty</th><th>Original rate</th><th>Original total</th></tr></thead><tbody>${item.components.map((c,i)=>`<tr><td>${i+1}</td><td>${escapeHtml(c.original?.Description||'Manually added / original not recorded')}<small>${escapeHtml(c.original?.['Cat No']||'')}</small></td><td>${escapeHtml(String(c.original?.Qty??''))}</td><td>${escapeHtml(String(c.original?.['Unit Ex GST']??''))}</td><td>${escapeHtml(String(c.original?.['Total Ex GST']??''))}</td></tr>`).join('')}</tbody></table></div></details>`;
}
function renderLightDetail(item){
  Object.assign(lightPriceState,{item,editing:false,dirty:false,photoDataUrl:null,removePhoto:false,photoLoading:false,photoReadId:(lightPriceState.photoReadId||0)+1});
  const box=$('#light-price-detail');
  box.innerHTML=`<div class="panel-heading light-detail-heading"><div><p class="eyebrow">Connected supply calculation</p><h3>${escapeHtml(item.description)}</h3>${item.nickname?`<p class="light-nickname">${escapeHtml(item.nickname)}</p>`:''}<p class="helper-text">${escapeHtml(item.project||'')} &middot; ${escapeHtml(item.reference)} &middot; ${escapeHtml(item.quote_date||'Date not set')}</p></div><div class="inline-actions"><button type="button" class="button primary small" data-light-edit>Edit details / photo</button><button type="button" class="button secondary small" data-light-close>Close</button></div></div>${item.has_photo?`<img class="light-detail-photo" src="${lightPhotoURL(item)}" alt="${escapeHtml(item.description)}">`:''}${lightTotals(item)}${lightWarnings(item)}${item.notes?`<p class="light-item-notes">${escapeHtml(item.notes)}</p>`:''}${lightReadTable(item)}${lightSource(item)}`;
}
async function showLightPrice(id){
  id=Number(id);if(lightPriceState.busy)return;
  if(lightPriceState.selected===id){closeLightPrice();return;}
  if(!confirmLightDiscard())return;
  const request=++lightPriceState.detailRequest;
  const data=await api(`/api/light-prices/${id}`);
  if(request!==lightPriceState.detailRequest||state.view!=='light-prices')return;
  const item=data.item;
  lightPriceState.dirty=false;closeLightPrice(false);
  lightPriceState.selected=item.id;
  let card=$(`[data-light-id="${item.id}"]`);
  if(!card){$('#light-price-results').insertAdjacentHTML('afterbegin',`<article class="light-price-result" data-light-id="${item.id}">${lightCard(item)}</article>`);card=$(`[data-light-id="${item.id}"]`);}
  const box=$('#light-price-detail');card.appendChild(box);card.classList.add('is-expanded');card.querySelector('.light-price-card').setAttribute('aria-expanded','true');
  box.classList.remove('hidden');renderLightDetail(item);rememberPage('light-prices',item.id);
  // Deliberately no scrollIntoView: expand immediately under the clicked result.
}
function lightEditRow(c){
  const field=(key,label,value,attributes='')=>`<input name="${key}" aria-label="${label}" ${attributes} value="${escapeHtml(String(value??''))}">`;
  return `<tr data-light-component="${c.id||''}"><td><input name="included" type="checkbox" aria-label="Include this component in package total" ${c.included?'checked':''}></td><td><textarea name="description" aria-label="Component description" rows="2" maxlength="4000" required>${escapeHtml(c.description||'')}</textarea><div class="light-component-identifiers">${field('supplier','Component supplier',c.supplier,'maxlength="250" placeholder="Supplier"')}${field('cat_no','Catalogue number',c.cat_no,'maxlength="250" placeholder="Cat no"')}</div>${field('status','Pricing status',c.status,'maxlength="100" placeholder="Status / note"')}</td><td>${field('quantity','Quoted component quantity',c.quantity,'type="number" min="0" max="1000000000000" step="any"')}</td><td>${field('unit_ex','Unit rate excluding GST',c.unit_ex,'type="number" min="0" max="1000000000000" step="any"')}</td><td><span data-calculated-total>${lightMoney(c.calculated_total_ex)}</span><small>Qty x rate</small></td><td>${field('total_ex','Quoted row total excluding GST',c.total_ex,'type="number" min="0" max="1000000000000" step="any"')}<small>Retained when not used</small></td><td><select name="total_mode" aria-label="Which row total to use"><option value="quoted" ${c.total_mode!=='calculated'?'selected':''}>Quoted total</option><option value="calculated" ${c.total_mode==='calculated'?'selected':''}>Qty x rate</option></select><strong data-used-total>${lightMoney(c.resolved_total_ex)}</strong><small data-row-difference></small></td></tr>`;
}
function renderLightEditor(){
  const item=lightPriceState.item;if(!item)return;
  Object.assign(lightPriceState,{editing:true,dirty:false,photoDataUrl:null,removePhoto:false,photoLoading:false,photoReadId:(lightPriceState.photoReadId||0)+1});
  const input=(key,label,value,attrs='')=>`<label>${label}<input name="${key}" value="${escapeHtml(String(value??''))}" ${attrs}></label>`;
  $('#light-price-detail').innerHTML=`<form id="light-edit-form"><div class="panel-heading"><div><p class="eyebrow">Edit price library working copy</p><h3>Light details, nickname &amp; photo</h3></div><button type="button" class="button secondary small" data-light-cancel>Cancel</button></div><p class="helper-text">These edits apply to this quoted lighting package only. Existing project estimates and the shared estimating catalogue are unchanged. Source rows remain available in Original import / audit information.</p><div class="light-editor-top"><div class="light-editor-fields">${input('description','Light name',item.description,'required maxlength="1000"')}${input('nickname','Searchable nickname',item.nickname,'maxlength="120" placeholder="For example: Office batten"')}<div class="light-editor-pair">${input('base_qty','Primary quantity / divisor',item.base_qty,'type="number" min="0" max="1000000000000" step="any"')}${input('primary_unit','Primary unit label',item.primary_unit,'required maxlength="40" placeholder="For example: fitting, set, m"')}</div><div class="light-editor-pair">${input('reference','Quote reference (working label)',item.reference,'required maxlength="250"')}${input('quote_date','Quote date',item.quote_date,'type="date"')}</div>${input('project','Quoted project',item.project,'maxlength="500"')}<label>Light notes / specification<textarea name="notes" rows="3" maxlength="10000">${escapeHtml(item.notes||'')}</textarea></label></div><div class="light-photo-editor"><div class="light-photo-zone" id="light-photo-zone" tabindex="0" role="group" aria-label="Light photo. Drop an image here or click here and press Control V to paste."><div id="light-photo-preview"></div><strong>Drop or paste a light photo</strong><p>Copy image (not the image address), click here, then press Ctrl+V / Cmd+V.</p><label class="button secondary small light-photo-choose">Choose image<input id="light-photo-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif,image/bmp"></label><small>PNG, JPEG, WebP, GIF or BMP &middot; up to 12 MB</small></div><button type="button" class="text-button danger-text" data-light-remove-photo>Remove photo</button><p id="light-photo-status" class="helper-text" role="status"></p></div></div><div class="panel-heading"><div><h3>Connected component rows</h3><p class="helper-text">Untick Include to leave a row out of the package. Choose which total to use explicitly. Blank means unpriced; enter 0 only when it really is a quoted zero.</p></div><button type="button" class="button secondary small" data-light-add-component>+ Component</button></div><div class="table-scroll"><table class="mini-table light-edit-table"><thead><tr><th>Include</th><th>Component / supplier / cat no</th><th>Qty</th><th>Unit rate ex GST</th><th>Calculated</th><th>Quoted total ex GST</th><th>Total to use</th></tr></thead><tbody id="light-edit-rows">${item.components.map(lightEditRow).join('')}</tbody></table></div><div id="light-live-totals" aria-live="polite"></div><p id="light-save-error" class="form-error" role="alert"></p><div class="light-edit-actions"><span id="light-dirty-label" class="helper-text">No unsaved changes</span><button type="button" class="button secondary" data-light-cancel>Cancel</button><button type="submit" class="button primary">Save light details</button></div></form>`;
  renderLightPhotoPreview();updateLightPreview();
  const form=$('#light-edit-form');
  form.addEventListener('input',()=>{markLightDirty();updateLightPreview();});
  form.addEventListener('change',event=>{if(event.target.type!=='file'){markLightDirty();updateLightPreview();}});
  form.addEventListener('submit',event=>{event.preventDefault();saveLightDetails().catch(error=>{const box=$('#light-save-error');if(box)box.textContent=error.message;toast(error.message,true);});});
  $('#light-photo-file').addEventListener('change',event=>{const file=event.target.files?.[0];if(file)readLightPhoto(file);});
  const zone=$('#light-photo-zone');
  zone.addEventListener('click',event=>{if(!event.target.closest('label,input,button'))zone.focus({preventScroll:true});});
  ['dragenter','dragover'].forEach(name=>zone.addEventListener(name,event=>{event.preventDefault();event.stopPropagation();zone.classList.add('dragover');}));
  zone.addEventListener('dragleave',()=>zone.classList.remove('dragover'));
  zone.addEventListener('drop',event=>{event.preventDefault();event.stopPropagation();zone.classList.remove('dragover');const file=event.dataTransfer?.files?.[0];if(file)readLightPhoto(file);else $('#light-photo-status').textContent='Drop an image file, or use Copy image and paste here. Image links are not imported.';});
  form.addEventListener('paste',event=>{
    const images=[...(event.clipboardData?.items||[])].filter(item=>item.kind==='file'&&item.type.startsWith('image/'));
    const file=images[0]?.getAsFile();
    if(file){event.preventDefault();event.stopPropagation();readLightPhoto(file);}
    else if(event.target.closest('#light-photo-zone')){event.preventDefault();$('#light-photo-status').textContent='No image was found on the clipboard. Use Copy image rather than Copy image address, or choose an image file.';}
  });
}
function markLightDirty(){lightPriceState.dirty=true;const label=$('#light-dirty-label');if(label)label.textContent='Unsaved changes - Save light details to apply';}
function renderLightPhotoPreview(){
  const item=lightPriceState.item;
  const src=lightPriceState.photoDataUrl||(!lightPriceState.removePhoto&&item.has_photo?lightPhotoURL(item):null);
  $('#light-photo-preview').innerHTML=src?`<img src="${src}" alt="Light photo preview">`:'<span class="light-photo-empty" aria-hidden="true">&#9788;</span>';
}
function readLightPhoto(file){
  const status=$('#light-photo-status');
  if(lightPriceState.busy)return;
  if(!/^image\/(png|jpeg|webp|gif|bmp)$/.test(file.type)){status.textContent='Choose a PNG, JPEG, WebP, GIF or BMP image.';return;}
  if(file.size>12*1024*1024){status.textContent='The image must be smaller than 12 MB.';return;}
  const itemId=lightPriceState.selected;const readId=(lightPriceState.photoReadId||0)+1;lightPriceState.photoReadId=readId;lightPriceState.photoLoading=true;markLightDirty();status.textContent='Reading image...';
  const reader=new FileReader();reader.onload=()=>{
    if(lightPriceState.photoReadId!==readId)return;lightPriceState.photoLoading=false;
    if(!lightPriceState.editing||lightPriceState.selected!==itemId)return;
    lightPriceState.photoDataUrl=String(reader.result);lightPriceState.removePhoto=false;
    renderLightPhotoPreview();markLightDirty();status.textContent='Photo ready. Save light details to store it with this light.';
  };reader.onerror=()=>{if(lightPriceState.photoReadId!==readId)return;lightPriceState.photoLoading=false;status.textContent='The image could not be read. Try choosing the file again.';};reader.readAsDataURL(file);
}
function readLightEdit(){
  const form=$('#light-edit-form');
  const payload={expected_revision:lightPriceState.item.revision};
  ['description','nickname','notes','primary_unit','reference','quote_date','project'].forEach(key=>payload[key]=form.querySelector(`.light-editor-fields [name="${key}"]`).value);
  const numeric=value=>value.trim()===''?null:Number(value);
  payload.base_qty=numeric(form.elements.namedItem('base_qty').value);
  payload.components=$$('#light-edit-rows tr').map(row=>{
    const component={id:row.dataset.lightComponent?Number(row.dataset.lightComponent):null,included:row.querySelector('[name="included"]').checked};
    ['description','supplier','cat_no','status','total_mode'].forEach(key=>component[key]=row.querySelector(`[name="${key}"]`).value);
    ['quantity','unit_ex','total_ex'].forEach(key=>component[key]=numeric(row.querySelector(`[name="${key}"]`).value));return component;
  });
  if(lightPriceState.photoDataUrl)payload.photo_data_url=lightPriceState.photoDataUrl;
  else if(lightPriceState.removePhoto)payload.remove_photo=true;
  return payload;
}
function lightPreviewProduct(quantity,rate){
  if(quantity===null||rate===null||!Number.isFinite(quantity)||!Number.isFinite(rate)||quantity<0||rate<0)return null;
  // Decimal multiplication with cents rounding, matching the server's ROUND_HALF_UP.
  const decimal=value=>{const [mantissa,exponent='0']=String(value).toLowerCase().split('e');const fraction=(mantissa.split('.')[1]||'').length;return [BigInt(mantissa.replace('.','')),fraction-Number(exponent)];};
  const [a,as]=decimal(quantity),[b,bs]=decimal(rate),scale=as+bs-2,product=a*b;
  const cents=scale<=0?product*10n**BigInt(-scale):(product+10n**BigInt(scale)/2n)/(10n**BigInt(scale));
  return Number(cents)/100;
}
function updateLightPreview(){
  if(!$('#light-edit-form'))return;
  const data=readLightEdit(),old=lightPriceState.item;
  const item={...old,...data,components:data.components.map((c,index)=>({...old.components[index],...c})),component_count:data.components.length,included_count:0,missing_prices:0,connected_total_ex:0,difference_count:0,implicit_links:0};
  item.components.forEach((c,index)=>{
    c.calculated_total_ex=lightPreviewProduct(c.quantity,c.unit_ex);
    c.resolved_total_ex=c.total_mode==='calculated'?c.calculated_total_ex:c.total_ex;
    c.difference_ex=c.total_ex!==null&&c.calculated_total_ex!==null?c.total_ex-c.calculated_total_ex:null;
    c.has_difference=c.difference_ex!==null&&Math.abs(c.difference_ex)>=.009;
    if(c.included){item.included_count++;if(c.resolved_total_ex===null)item.missing_prices++;else item.connected_total_ex+=c.resolved_total_ex;if(c.has_difference&&c.total_mode==='quoted')item.difference_count++;if((c.connection_basis||'').toLowerCase().includes('previous'))item.implicit_links++;}
    const row=$$('#light-edit-rows tr')[index];row.querySelector('[data-calculated-total]').textContent=lightMoney(c.calculated_total_ex);row.querySelector('[data-used-total]').textContent=c.included?lightMoney(c.resolved_total_ex):'Excluded';row.querySelector('[data-row-difference]').textContent=c.has_difference?`Quoted difference: ${lightMoney(c.difference_ex)}`:'';row.classList.toggle('light-excluded',!c.included);
  });
  item.main_row_unit_ex=item.components[0]?.unit_ex??null;item.base_differs=Boolean(item.components.length&&item.base_qty!==item.components[0].quantity);
  item.connected_unit_ex=item.base_qty>0&&!item.missing_prices&&item.included_count?item.connected_total_ex/item.base_qty:null;
  $('#light-live-totals').innerHTML='<h3>Live calculation preview</h3>'+lightTotals(item)+lightWarnings(item);
}
async function saveLightDetails(){
  const form=$('#light-edit-form');if(!form||!form.reportValidity()||lightPriceState.busy)return;
  if(lightPriceState.photoLoading){$('#light-save-error').textContent='Please wait for the image to finish loading, then save.';return;}
  const payload=readLightEdit();lightPriceState.busy=true;$('#light-save-error').textContent='';
  const buttons=$$('button,input,textarea,select',form);buttons.forEach(button=>button.disabled=true);
  try{
    const result=await api(`/api/light-prices/${lightPriceState.selected}`,{method:'PATCH',body:payload});
    const item=result.item,card=$(`[data-light-id="${item.id}"]`);
    if(card){const oldCard=card.querySelector('.light-price-card');oldCard.outerHTML=lightCard(item);card.querySelector('.light-price-card').setAttribute('aria-expanded','true');}
    lightPriceState.results=lightPriceState.results.map(row=>row.id===item.id?item:row);
    renderLightDetail(item);toast('Light details saved. Nickname and photo are available in the price library.');
  }finally{lightPriceState.busy=false;buttons.forEach(button=>button.disabled=false);}
}
document.addEventListener('DOMContentLoaded',()=>{
  let timer;
  const runSearch=()=>loadLightPrices().catch(error=>toast(error.message,true));
  $('#supplier-filter').addEventListener('input',filterSupplierOptions);
  $('#supplier-filter').addEventListener('keydown',event=>{if(event.key==='Enter')event.preventDefault();});
  $('#light-price-supplier').addEventListener('change',event=>{if(event.target.id==='supplier-filter')return;clearTimeout(timer);if(event.target.dataset.allSuppliers!==undefined){lightPriceState.suppliers=[];}else{lightPriceState.suppliers=$$('#light-price-supplier input[data-supplier]:checked').map(el=>el.value);}renderSupplierPicker(lightPriceState.supplierOptions||[]);runSearch();});
  document.addEventListener('click',event=>{const picker=$('#light-price-supplier');if(!picker.contains(event.target))picker.open=false;});
  $('#light-price-supplier').addEventListener('keydown',event=>{if(event.key==='Escape'){event.currentTarget.open=false;event.currentTarget.querySelector('summary').focus();}});
  $('#light-price-search').addEventListener('input',()=>{clearTimeout(timer);lightPriceState.request++;timer=setTimeout(runSearch,250);});
  $('#light-price-search-form').addEventListener('submit',event=>{event.preventDefault();clearTimeout(timer);runSearch();});
  $('#light-price-prev').addEventListener('click',()=>loadLightPrices(Math.max(0,lightPriceState.offset-40)).catch(error=>toast(error.message,true)));
  $('#light-price-next').addEventListener('click',()=>loadLightPrices(lightPriceState.offset+40).catch(error=>toast(error.message,true)));
  $('#light-price-results').addEventListener('click',event=>{
    const open=event.target.closest('[data-light-open]');
    if(open&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey){event.preventDefault();showLightPrice(open.dataset.lightOpen).catch(error=>toast(error.message,true));}
    if(event.target.closest('[data-light-edit]'))renderLightEditor();
    if(event.target.closest('[data-light-close]'))closeLightPrice();
    if(event.target.closest('[data-light-cancel]')&&!lightPriceState.busy&&confirmLightDiscard())renderLightDetail(lightPriceState.item);
    if(event.target.closest('[data-light-add-component]')){
      $('#light-edit-rows').insertAdjacentHTML('beforeend',lightEditRow({id:null,description:'',supplier:'',cat_no:'',status:'Manual',included:1,total_mode:'calculated',quantity:1,unit_ex:null,total_ex:null}));markLightDirty();updateLightPreview();
    }
    if(event.target.closest('[data-light-remove-photo]')){lightPriceState.photoReadId=(lightPriceState.photoReadId||0)+1;lightPriceState.photoLoading=false;lightPriceState.photoDataUrl=null;lightPriceState.removePhoto=true;renderLightPhotoPreview();markLightDirty();$('#light-photo-status').textContent='Photo will be removed when you save.';}
  });
  $('#light-price-floating-search').addEventListener('click',()=>{$('#light-price-search-form').scrollIntoView({behavior:'smooth',block:'center'});$('#light-price-search').focus({preventScroll:true});});
  document.addEventListener('click',event=>{
    if(event.target.closest('.nav-button,.brand-home')&&!event.ctrlKey&&!event.metaKey&&state.view==='light-prices'&&lightPriceState.dirty&&!confirmLightDiscard()){event.preventDefault();event.stopImmediatePropagation();}
  },true);
});
window.addEventListener('beforeunload',event=>{if(lightPriceState.dirty){event.preventDefault();event.returnValue='';}});

;
/* v23.js */
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

;
/* profile.js */
/* Account photos are staged locally and saved with the profile, never in a catalogue. */
const profilePhotoState={dataUrl:null,remove:false,reading:false,readId:0,dirty:false,busy:false};
function profileInitials(name){
  const words=String(name||'').trim().split(/\s+/).filter(Boolean);
  if(!words.length)return '?';
  return (Array.from(words[0])[0]+(words.length>1?Array.from(words.at(-1))[0]:'')).toLocaleUpperCase();
}
function profilePhotoURL(user){return `/api/auth/profile/photo?v=${Number(user.avatar_version||0)}`;}
function fillAvatar(element,user,source){
  if(!element)return;
  const initials=profileInitials(user?.name||user?.username);
  element.replaceChildren();
  const fallback=()=>{element.replaceChildren();const span=document.createElement('span');span.className='avatar-initials';span.textContent=initials;span.setAttribute('aria-hidden','true');element.append(span);};
  if(!source){fallback();return;}
  const image=document.createElement('img');image.alt='';image.src=source;
  image.addEventListener('error',fallback,{once:true});element.append(image);
}
function renderAccountAvatar(user){fillAvatar($('#account-avatar'),user,user.has_avatar?profilePhotoURL(user):null);}
function clearProfilePhoto(){
  profilePhotoState.readId++;
  Object.assign(profilePhotoState,{dataUrl:null,remove:false,reading:false,dirty:false,busy:false});
  const input=$('#profile-photo-file');if(input)input.value='';
  if($('#profile-photo-preview'))$('#profile-photo-preview').replaceChildren();
}
function resetProfilePhoto(user){
  clearProfilePhoto();
  renderProfilePhoto();
  $('#profile-photo-status').textContent='';
}
function renderProfilePhoto(){
  const user={...state.user,name:$('#profile-name').value||state.user?.name};
  const source=profilePhotoState.dataUrl||(!profilePhotoState.remove&&user.has_avatar?profilePhotoURL(user):null);
  fillAvatar($('#profile-photo-preview'),user,source);
  $('#profile-remove-photo').disabled=profilePhotoState.busy||(!source&&!profilePhotoState.reading);
}
function readProfilePhoto(file){
  const status=$('#profile-photo-status');if(profilePhotoState.busy||!file)return;
  if(!/^image\/(png|jpeg|webp|gif|bmp)$/.test(file.type)){status.textContent='Choose a PNG, JPG, WebP, GIF or BMP image file.';return;}
  if(!file.size||file.size>8*1024*1024){status.textContent='Choose a non-empty image smaller than 8 MB.';return;}
  const request=++profilePhotoState.readId,userId=state.user?.id;
  profilePhotoState.reading=true;status.textContent='Preparing photo preview...';
  const reader=new FileReader();
  reader.onload=()=>{
    if(request!==profilePhotoState.readId||state.user?.id!==userId)return;
    const image=new Image();
    image.onload=()=>{
      if(request!==profilePhotoState.readId||state.user?.id!==userId)return;
      profilePhotoState.reading=false;
      if(image.naturalWidth*image.naturalHeight>20000000){status.textContent='Use an image with at most 20 megapixels.';return;}
      profilePhotoState.dataUrl=String(reader.result);profilePhotoState.remove=false;profilePhotoState.dirty=true;
      renderProfilePhoto();status.textContent='Photo ready. Select Save profile to apply it.';
    };
    image.onerror=()=>{if(request===profilePhotoState.readId){profilePhotoState.reading=false;status.textContent='The image could not be read. Choose another file.';}};
    image.src=String(reader.result);
  };
  reader.onerror=()=>{if(request===profilePhotoState.readId){profilePhotoState.reading=false;status.textContent='The photo could not be read. Try again.';}};
  reader.readAsDataURL(file);
}
document.addEventListener('DOMContentLoaded',()=>{
  const file=$('#profile-photo-file'),zone=$('#profile-photo-area');
  [$('#profile-photo-ring'),$('#profile-upload-photo')].forEach(button=>button.addEventListener('click',()=>{if(!profilePhotoState.busy)file.click();}));
  file.addEventListener('change',()=>{readProfilePhoto(file.files[0]);file.value='';});
  $('#profile-name').addEventListener('input',renderProfilePhoto);
  $('#profile-remove-photo').addEventListener('click',()=>{
    if(profilePhotoState.busy)return;
    profilePhotoState.readId++;profilePhotoState.reading=false;profilePhotoState.dataUrl=null;profilePhotoState.remove=true;profilePhotoState.dirty=true;
    renderProfilePhoto();$('#profile-photo-status').textContent='Initials will replace your photo when you save your profile.';
  });
  let depth=0;
  zone.addEventListener('dragenter',event=>{event.preventDefault();depth++;if(!profilePhotoState.busy)zone.classList.add('photo-drop-active');});
  zone.addEventListener('dragover',event=>{event.preventDefault();event.dataTransfer.dropEffect=profilePhotoState.busy?'none':'copy';});
  zone.addEventListener('dragleave',()=>{if(--depth<=0){depth=0;zone.classList.remove('photo-drop-active');}});
  zone.addEventListener('drop',event=>{
    event.preventDefault();depth=0;zone.classList.remove('photo-drop-active');
    if(profilePhotoState.busy)return;
    if(event.dataTransfer.files.length!==1){$('#profile-photo-status').textContent='Drop one image file at a time.';return;}
    readProfilePhoto(event.dataTransfer.files[0]);
  });
  document.addEventListener('click',event=>{
    if(event.target.closest('.nav-button,.brand-home')&&state.view==='profile'&&(profilePhotoState.dirty||profilePhotoState.reading)&&!event.ctrlKey&&!event.metaKey){
      if(profilePhotoState.busy||!confirm('Leave without saving your profile photo change?')){event.preventDefault();event.stopImmediatePropagation();}
      else clearProfilePhoto();
    }
  },true);
});
window.addEventListener('beforeunload',event=>{if(profilePhotoState.dirty||profilePhotoState.reading){event.preventDefault();event.returnValue='';}});

;
/* quotation_import.js */
/* Check -> review matching records -> import selected. No silent replacement. */
const quoteImportState={preview:null,busy:false,request:0};
function resetQuoteReview(cancelServer=false){
  const token=quoteImportState.preview?.preview_id;
  quoteImportState.preview=null;quoteImportState.request++;
  const review=$('#light-import-review');if(review){review.classList.add('hidden');review.replaceChildren();}
  if(cancelServer&&token&&state.user)api(`/api/light-prices/previews/${token}`,{method:'DELETE'}).catch(()=>{});
}
function selectedQuoteKeys(){return $$('#light-import-review [data-quote-check]:checked').map(el=>el.value);}
function updateQuoteSelection(){
  const count=selectedQuoteKeys().length,button=$('#light-import-confirm');
  if(button){button.disabled=quoteImportState.busy||!count;button.textContent=`Import selected (${count})`;}
}
function quotePreviewTable(quote){
  return `<details class="quote-row-preview"><summary>Review ${quote.line_count} extracted price rows</summary><div class="table-scroll"><table class="mini-table"><thead><tr><th>Item</th><th>Description / supplier / catalogue</th><th>Qty</th><th>Unit ex GST</th><th>Row total ex GST</th></tr></thead><tbody>${quote.lines.map(row=>`<tr><td>${escapeHtml(row.item_no||'')}</td><td><strong>${escapeHtml(row.description||'')}</strong><small>${escapeHtml(row.supplier||'')} &middot; ${escapeHtml(row.cat_no||'')}</small></td><td>${lightQty(row.quantity)}</td><td>${lightRate(row.unit_ex)}</td><td>${lightMoney(row.total_ex)}</td></tr>`).join('')}</tbody></table></div></details>`;
}
function renderQuoteReview(data){
  const box=$('#light-import-review'),names={new:'New quotation',identical:'Already in library',revised:'Existing reference - changed data / date',matching_data:'Matching data under another reference'};
  box.innerHTML=`<div class="quote-review-heading"><div><p class="eyebrow">Check before saving</p><h3>Review quotation import</h3></div><span class="quote-review-file">${escapeHtml(data.filename)}</span></div><p class="helper-text">The file has been transferred for checking. <strong>No supplier prices have been saved yet.</strong> Exact duplicates cannot be selected. Changed quotations are saved separately, without replacing your existing prices, edits or photos.</p><div class="quote-review-summary"><span>${data.summary.new} new</span><span>${data.summary.identical} identical</span><span>${data.summary.revised+data.summary.matching_data} to review</span></div>${data.notes_excluded?`<p class="quote-review-warning">${data.notes_excluded} notes or unsupported non-price rows were excluded. Review the extracted rows below.</p>`:''}<div class="quote-review-list">${data.quotes.map(quote=>{
    const difference=quote.quoted_total_ex!==null&&Math.abs(quote.quoted_total_ex-quote.parsed_total_ex)>.009;
    return `<article class="quote-review-card is-${quote.status}"><div class="quote-review-top"><label class="quote-select"><input type="checkbox" data-quote-check value="${quote.key}" ${quote.selected?'checked':''} ${quote.can_import?'':'disabled'}><span><strong>${escapeHtml(quote.reference)}</strong><small>${escapeHtml(quote.project||'No project')} &middot; ${escapeHtml(quote.quote_date||'No quote date')}</small></span></label><span class="quote-status">${names[quote.status]}</span></div><p class="quote-selection-help">${quote.status==='identical'?'Identical quotation found. It will be skipped, keeping the existing record.':quote.status==='new'?'Selected for import. Untick this quotation to leave it out.':'Tick to import this quotation as a separate record. Existing quotations will not be changed.'}</p><p class="quote-price-summary">${quote.group_count} packages &middot; ${quote.line_count} rows &middot; Priced-row subtotal: <strong>${lightMoney(quote.parsed_total_ex)}</strong> ex GST${quote.quoted_total_ex!==null?` &middot; Supplier quote total: ${lightMoney(quote.quoted_total_ex)} ex GST`:''}</p>${difference?'<p class="quote-review-warning">The parsed subtotal differs from the supplier quote total. Review all rows and excluded notes before selecting this quotation.</p>':''}${quote.unpriced_rows?`<p class="quote-review-warning">${quote.unpriced_rows} row(s) are not priced. Blank prices remain unpriced, not zero.</p>`:''}${quote.matching_product_rows&&quote.status==='new'?`<p class="helper-text">${quote.matching_product_rows} supplier/catalogue row(s) already appear in your library. A new quote preserves its own pricing history rather than updating those rows.</p>`:''}${quote.matches.length?`<div class="quote-existing"><strong>Existing match${quote.match_count>1?'es':''}</strong>${quote.matches.map(match=>`<p>${escapeHtml(match.reference)} &middot; ${escapeHtml(match.quote_date||'No date')} &middot; ${escapeHtml(match.project||'No project')}<small>${escapeHtml(match.source||'Source not recorded')}</small></p>`).join('')}${quote.match_count>quote.matches.length?`<small>Plus ${quote.match_count-quote.matches.length} more existing matches.</small>`:''}</div>`:''}${quotePreviewTable(quote)}</article>`;
  }).join('')}</div><p class="helper-text">Review expires after 30 minutes. Selected quotations are saved together only after you confirm.</p><div class="quote-review-actions"><button id="light-import-cancel" type="button" class="button secondary">Cancel review</button><button id="light-import-confirm" type="button" class="button primary">Import selected</button></div><p id="light-import-review-status" class="helper-text" role="status"></p>`;
  box.classList.remove('hidden');updateQuoteSelection();
}
function setQuoteBusy(busy){
  quoteImportState.busy=busy;
  $('#light-price-check-button').disabled=busy;$('#light-price-file').disabled=busy;
  $$('#light-import-review button').forEach(el=>el.disabled=busy);
  $$('#light-import-review [data-quote-check]').forEach(el=>el.disabled=busy||quoteImportState.preview?.quotes.find(q=>q.key===el.value)?.status==='identical');
  updateQuoteSelection();
}
async function checkQuotation(event){
  event.preventDefault();
  const file=$('#light-price-file').files[0];if(!file||quoteImportState.busy||lightPriceState.busy||!confirmLightDiscard())return;
  if(file.size>30*1024*1024){$('#light-price-import-status').textContent='Choose a file smaller than 30 MB.';return;}
  if(lightPriceState.dirty){lightPriceState.dirty=false;closeLightPrice(false);}
  resetQuoteReview(true);const request=++quoteImportState.request;setQuoteBusy(true);
  $('#light-price-import-status').textContent='Checking quotation contents and existing library records...';
  try{
    const body=new FormData();body.append('file',file);
    const data=await api('/api/light-prices/preview',{method:'POST',body});
    if(request!==quoteImportState.request)return;
    quoteImportState.preview=data;renderQuoteReview(data);
    $('#light-price-import-status').textContent='Check complete. Review the checkboxes below, then confirm the import.';
  }catch(error){if(request===quoteImportState.request)$('#light-price-import-status').textContent=error.message;}
  finally{setQuoteBusy(false);}
}
async function confirmQuotationImport(){
  if(quoteImportState.busy||!quoteImportState.preview)return;
  const selected=selectedQuoteKeys();if(!selected.length)return;
  const token=quoteImportState.preview.preview_id;
  setQuoteBusy(true);$('#light-import-review-status').textContent='Saving selected quotations...';
  try{
    const result=await api('/api/light-prices/import',{method:'POST',body:{preview_id:token,selected}});
    const message=`Added ${result.quotes_added} quotations, ${result.groups_added} packages and ${result.lines_added} rows. ${result.quotes_skipped} identical quotation(s) skipped; ${result.quotes_not_selected} not selected. Existing quotations were not overwritten.`;
    resetQuoteReview();$('#light-price-import-form').reset();$('#light-price-import-status').textContent=message;toast('Selected supplier prices imported.');
    await loadLightPrices();
  }catch(error){const target=$('#light-import-review-status')||$('#light-price-import-status');target.textContent=error.message;}
  finally{setQuoteBusy(false);}
}
document.addEventListener('DOMContentLoaded',()=>{
  $('#light-price-import-form').addEventListener('submit',checkQuotation);
  $('#light-price-file').addEventListener('change',()=>{resetQuoteReview(true);$('#light-price-import-status').textContent='File selected. Click Check quotation before importing.';});
  $('#light-import-review').addEventListener('change',event=>{if(event.target.matches('[data-quote-check]'))updateQuoteSelection();});
  $('#light-import-review').addEventListener('click',event=>{
    if(event.target.closest('#light-import-confirm'))confirmQuotationImport();
    if(event.target.closest('#light-import-cancel')&&!quoteImportState.busy){resetQuoteReview(true);$('#light-price-import-form').reset();$('#light-price-import-status').textContent='Review cancelled. No prices were imported.';}
  });
});

;
/* import_history.js */
/* Upload history is requested only when the info dialog is opened. */
const uploadHistoryState={request:0,offset:0,limit:20,total:0,hasMore:false,timer:null};
function resetUploadHistory(){
  uploadHistoryState.request++;clearTimeout(uploadHistoryState.timer);
  Object.assign(uploadHistoryState,{offset:0,total:0,hasMore:false});
  $('#import-history-search-form')?.reset();
  if($('#import-history-results'))$('#import-history-results').replaceChildren();
  if($('#import-history-status'))$('#import-history-status').textContent='';
  if($('#import-history-page'))$('#import-history-page').textContent='';
}
function uploadHistoryDate(value){
  const d=new Date(value);
  return Number.isNaN(d.getTime())?String(value||'Date not recorded'):d.toLocaleString('en-AU',{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});
}
function renderUploadHistory(data){
  const target=$('#import-history-results');
  target.innerHTML=data.uploads.length?data.uploads.map(row=>{
    const library=row.kind==='catalog'?'Catalogue':'Light prices';
    const counts=row.kind==='catalog'?`${row.sheets} sheet${row.sheets===1?'':'s'} \u00b7 ${row.items} assemblies \u00b7 ${row.components} components`:`${row.quotes} quotation${row.quotes===1?'':'s'} \u00b7 ${row.items} packages \u00b7 ${row.components} price rows`;
    return `<article class="upload-history-entry"><div class="upload-history-heading"><span class="upload-library kind-${row.kind}">${library}</span><time>${escapeHtml(uploadHistoryDate(row.imported_at))}</time></div><h3>${escapeHtml(row.filename)}</h3><p class="upload-history-counts">${counts}${row.skipped?` \u00b7 ${row.skipped} duplicates skipped`:''}</p><p class="helper-text">Uploaded by: <strong>${escapeHtml(row.uploader_name)}</strong>${row.is_mine?' (you)':''}${row.legacy?' \u00b7 Legacy source record':''}</p>${row.references_text||row.projects_text?`<details><summary>Source details</summary>${row.references_text?`<p><strong>${row.kind==='catalog'?'Sheets':'Quotation references'}:</strong> ${escapeHtml(row.references_text)}</p>`:''}${row.projects_text?`<p><strong>Projects:</strong> ${escapeHtml(row.projects_text)}</p>`:''}</details>`:''}</article>`;
  }).join(''):'<div class="history-empty"><h3>No matching uploads</h3><p>Try another search or choose All uploads. Older records without an uploader are not included in My uploads.</p></div>';
  $('#import-history-status').textContent=`${data.total} matching file record${data.total===1?'':'s'}`;
  $('#import-history-page').textContent=data.total?`${data.offset+1}-${data.offset+data.uploads.length} of ${data.total}`:'0 results';
  $('#import-history-prev').disabled=data.offset===0;
  $('#import-history-next').disabled=!data.has_more;
}
async function refreshUploadHistory(offset=uploadHistoryState.offset){
  if(!state.user||!$('#import-history-dialog').open)return;
  const request=++uploadHistoryState.request,owner=state.user.id;
  const query=new URLSearchParams({q:$('#import-history-search').value.trim(),kind:$('#import-history-kind').value,who:$('#import-history-who').value,limit:uploadHistoryState.limit,offset});
  $('#import-history-status').textContent='Loading uploaded files...';
  $('#import-history-results').setAttribute('aria-busy','true');
  $('#import-history-prev').disabled=true;$('#import-history-next').disabled=true;
  try{
    const data=await api(`/api/import-history?${query}`);
    if(request!==uploadHistoryState.request||state.user?.id!==owner||!$('#import-history-dialog').open)return;
    Object.assign(uploadHistoryState,{offset:data.offset,total:data.total,hasMore:data.has_more});
    renderUploadHistory(data);
  }catch(error){
    if(request===uploadHistoryState.request&&state.user?.id===owner){$('#import-history-status').textContent=error.message;$('#import-history-results').replaceChildren();$('#import-history-page').textContent='';}
  }finally{if(request===uploadHistoryState.request)$('#import-history-results').removeAttribute('aria-busy');}
}
function searchUploadHistory(){clearTimeout(uploadHistoryState.timer);refreshUploadHistory(0);}
document.addEventListener('DOMContentLoaded',()=>{
  $('#import-history-button').addEventListener('click',()=>{
    $('#import-history-dialog').showModal();refreshUploadHistory(0);$('#import-history-search').focus({preventScroll:true});
  });
  $('#import-history-dialog').addEventListener('close',()=>{uploadHistoryState.request++;clearTimeout(uploadHistoryState.timer);});
  $('#import-history-search-form').addEventListener('submit',event=>{event.preventDefault();searchUploadHistory();});
  $('#import-history-search').addEventListener('input',()=>{
    clearTimeout(uploadHistoryState.timer);uploadHistoryState.request++;
    $('#import-history-prev').disabled=true;$('#import-history-next').disabled=true;
    uploadHistoryState.timer=setTimeout(searchUploadHistory,250);
  });
  [$('#import-history-kind'),$('#import-history-who')].forEach(el=>el.addEventListener('change',searchUploadHistory));
  $('#import-history-prev').addEventListener('click',()=>refreshUploadHistory(Math.max(0,uploadHistoryState.offset-uploadHistoryState.limit)));
  $('#import-history-next').addEventListener('click',()=>{if(uploadHistoryState.hasMore)refreshUploadHistory(uploadHistoryState.offset+uploadHistoryState.limit);});
});

;
/* project_transfer.js */
/* Portable projects and an account-scoped component clipboard. */
let projectJSONDraft=null,componentClipboard=null,projectJSONBusy=false;
function sydneyMonth(now=new Date()){
 const parts=new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit'}).formatToParts(now);
 return parts.find(p=>p.type==='year').value+'-'+parts.find(p=>p.type==='month').value;
}
function downloadProjectJSON(data,name){
 const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'}));
 const a=document.createElement('a');a.href=url;a.download=name.replace(/[^a-zA-Z0-9_.-]/g,'_')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
let clipboardLoad=0;
const componentChannel=typeof BroadcastChannel!=='undefined'?new BroadcastChannel('tec-component-clipboard'):null;
async function refreshComponentClipboard(){
 const owner=state.user?.id,request=++clipboardLoad;if(!owner){componentClipboard=null;syncComponentPaste();return;}
 try{const value=await api('/api/clipboard?t='+Date.now());if(state.user?.id!==owner||request!==clipboardLoad)return;componentClipboard=value.component?value:null;syncComponentPaste();return true;}catch(error){toast(error.message,true);return false;}
}
async function saveComponentClipboard(component){
 const owner=state.user?.id;if(!owner)return;const request=++clipboardLoad;
 const value=await api('/api/clipboard',{method:'POST',body:{component}});
 if(owner!==state.user?.id||request!==clipboardLoad)return;
 componentClipboard=value.component?value:null;syncComponentPaste();
 componentChannel?.postMessage({userId:owner});
 try{localStorage.setItem('tec-clipboard-update',JSON.stringify({userId:owner,at:Date.now()}));}catch(_){}
}
componentChannel?.addEventListener('message',e=>{if(e.data.userId===state.user?.id)refreshComponentClipboard();});
window.addEventListener('storage',e=>{if(e.key==='tec-clipboard-update')refreshComponentClipboard();});
window.addEventListener('focus',()=>{if(document.querySelector('#manual-dialog')?.open)refreshComponentClipboard();});
function syncComponentPaste(){
 const available=Boolean(state.user&&componentClipboard?.userId===state.user.id);
 $('#paste-component-button').disabled=!available;
 $('#paste-component-button').title=available?'Paste '+componentClipboard.component.description:'Copy a component row first';
 $('#component-clipboard-bar').classList.toggle('hidden',!available);
 $('#component-clipboard-label').textContent=available?'Copied: '+componentClipboard.component.description:'';
}

async function openProjectJSON(){
 const select=$('#project-json-select');select.innerHTML=state.projects.map(p=>`<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
 if(state.projects.some(p=>p.id===state.projectId))select.value=String(state.projectId);
 $('#project-json-export').disabled=!state.projects.length;
 $('#project-json-status').textContent='';$('#project-json-dialog').showModal();
}
async function projectJSONAction(action){
 if(projectJSONBusy)return;projectJSONBusy=true;const dialog=$('#project-json-dialog');dialog.setAttribute('aria-busy','true');
 const controls=[...dialog.querySelectorAll('button,input,select')];const disabled=controls.map(e=>e.disabled);controls.forEach(e=>e.disabled=true);
 try{await action();}catch(e){$('#project-json-status').textContent=e.message;toast(e.message,true);}
 finally{projectJSONBusy=false;dialog.removeAttribute('aria-busy');controls.forEach((e,i)=>e.disabled=disabled[i]);$('#project-json-import').disabled=!projectJSONDraft;}
}
document.addEventListener('DOMContentLoaded',()=>{
 $('#project-json-open').addEventListener('click',openProjectJSON);
 $('#project-json-dialog').addEventListener('cancel',e=>{if(projectJSONBusy)e.preventDefault();});
 $('#project-json-export').addEventListener('click',()=>projectJSONAction(async()=>{
  const data=await api('/api/projects/'+Number($('#project-json-select').value)+'/json');downloadProjectJSON(data,data.project.name);$('#project-json-status').textContent='Project JSON downloaded.';
 }));
 $('#project-json-example').addEventListener('click',()=>projectJSONAction(async()=>{const response=await fetch('/assets/example_project.json');if(!response.ok)throw new Error('Could not load example');downloadProjectJSON(await response.json(),'TEC_ConEst_example_project');}));
 $('#project-json-file').addEventListener('change',async e=>{
  projectJSONDraft=null;$('#project-json-import').disabled=true;$('#project-json-preview').textContent='';$('#project-json-status').textContent='';const file=e.target.files[0];if(!file)return;
  try{
   if(file.size>10*1024*1024)throw new Error('Choose a JSON file smaller than 10 MB.');
   const data=JSON.parse(await file.text());if(data?.format!=='tec-conest-project'||data.version!==1||!data.project?.name||!Array.isArray(data.lines))throw new Error('Choose a TEC ConEst project JSON file. Download the example for its format.');
   if(e.target.files[0]!==file)return;
   projectJSONDraft=data;$('#project-json-preview').textContent=`${data.project.name} · ${data.lines.length} estimate items. A new project will be created.`;$('#project-json-import').disabled=false;
  }catch(error){$('#project-json-status').textContent=error.message;}
 });
 $('#project-json-import').addEventListener('click',()=>projectJSONAction(async()=>{
  if(!projectJSONDraft)return;const result=await api('/api/project-json/import',{method:'POST',body:projectJSONDraft});projectJSONDraft=null;$('#project-json-file').value='';$('#project-json-preview').textContent='';await loadDashboard();$('#project-json-dialog').close();location.hash='#/estimate/'+result.id;toast('Project imported');
 }));
 $('#manual-components').addEventListener('click',async e=>{
  const button=e.target.closest('.clipboard-component');if(!button)return;
  try {
   const row=button.closest('.manual-component');
   componentClipboard=null;
   const component=readManualComponents(row)[0];
   if(!component)throw new Error('Choose a component row to copy.');
   await saveComponentClipboard(structuredClone(component));
   $$('#manual-components .clipboard-component').forEach(b=>b.classList.remove('is-copied'));
   button.classList.add('is-copied');syncComponentPaste();toast('Copied: '+component.description);
  }catch(error){componentClipboard=null;syncComponentPaste();toast(error.message,true);}

 });
 $('#clear-component-clipboard').addEventListener('click',()=>saveComponentClipboard(null).catch(e=>toast(e.message,true)));
 $('#refresh-component-clipboard').addEventListener('click',refreshComponentClipboard);
 $('#paste-component-button').addEventListener('click',async()=>{
  if(!await refreshComponentClipboard())return;
  if(componentClipboard?.userId!==state.user?.id)return;
  const c=structuredClone(componentClipboard.component);delete c.id;delete c.project_line_id;delete c.catalog_item_id;c.is_parent=0;c.is_supply_copy=0;
  $('#manual-components').insertAdjacentHTML('beforeend',componentRow(c));refreshManualPricing();toast('Component pasted. Save the item to keep it.');
 });
 new MutationObserver(()=>{if($('#manual-dialog').open)refreshComponentClipboard();else syncComponentPaste();}).observe($('#manual-dialog'),{attributes:true,attributeFilter:['open']});
});

;
/* performance.js */
/* v3.5: on-demand administrator contributions across all three workflows. */
let performanceRequest=0;
function performanceDialog(){
  let dialog=$('#performance-dialog');
  if(dialog)return dialog;
  dialog=document.createElement('dialog');dialog.id='performance-dialog';
  dialog.innerHTML=`<div class="dialog-card"><div class="dialog-heading"><div><span class="eyebrow">CONTRIBUTIONS</span><h2 id="performance-title">View Contribution</h2></div><button type="button" class="icon-button" aria-label="Close performance">×</button></div><div class="performance-toolbar"><label>Period <select id="performance-period"><option value="all">All Time</option><option value="month">Specific month</option><option value="year">Specific year</option><option value="custom">Custom dates</option></select></label><div id="contribution-dates"></div><span class="helper-text">Recorded work across Estimator, Tenders and Opportunities</span></div><div id="performance-body" aria-live="polite"></div></div>`;
  document.body.append(dialog);dialog.setAttribute('aria-labelledby','performance-title');
  dialog.querySelector('[aria-label="Close performance"]').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>performanceRequest++);
  $('#performance-period').onchange=()=>{contributionDates();loadPerformance(dialog.dataset.userId);};
  return dialog;
}
function openPerformance(id){
  const dialog=performanceDialog();dialog.dataset.userId=id;$('#performance-period').value='all';contributionDates();
  if(!dialog.open)dialog.showModal();loadPerformance(id);
}
async function loadPerformance(id){
  const request=++performanceRequest,dialog=performanceDialog(),body=$('#performance-body');
  body.innerHTML='<p class="helper-text">Loading contributions…</p>';
  const {since,until}=contributionRange();
  try{
    const result=await api(`/api/users/${Number(id)}/performance?since=${encodeURIComponent(since)}&until=${encodeURIComponent(until)}`);
    if(request!==performanceRequest||!dialog.open)return;
    $('#performance-title').textContent=result.person.name;
    const bars=rows=>rows.length?rows.map(r=>`<div class="performance-bar"><div><span>${escapeHtml(r.action)}</span><b>${r.count}</b></div><meter min="0" max="${Math.max(...rows.map(x=>x.count),1)}" value="${r.count}" aria-label="${escapeHtml(r.action)}: ${r.count}"></meter></div>`).join(''):'<p class="helper-text">No recorded activity for this period.</p>';
    const e=result.estimator,t=result.tenders,h=result.historical,u=result.uploads,o=result.opportunities||{projects:0,total:0,actions:[],rowsAdded:0,rowsUpdated:0};
    const recent=(result.recent||[]).map(row=>{
      const at=new Date(row.created_at),label=Number.isNaN(at.getTime())?row.created_at:at.toLocaleString('en-AU',{timeZone:'Australia/Sydney',dateStyle:'medium',timeStyle:'short'});
      return `<article><span class="performance-app">${escapeHtml(row.app)}</span><div><b>${escapeHtml(row.action)}</b>${row.project?`<p>${escapeHtml(row.project)}</p>`:''}</div><time datetime="${escapeHtml(row.created_at)}">${escapeHtml(label)}</time></article>`;
    }).join('');
    body.innerHTML=`<div class="performance-kpis"><article><span>Estimator projects contributed to</span><strong>${e.projects}</strong><small>${e.total} recorded actions</small></article><article><span>Tender submissions worked on</span><strong>${t.submissions}</strong><small>${t.total} website actions · ${h.periodChaseUps||0} historical chase-ups in range</small></article><article><span>Opportunities contributed to</span><strong>${o.projects}</strong><small>${o.total} recorded actions, including retained deletion history</small></article><article><span>Documents uploaded</span><strong>${u.total}</strong><small>${u.byType.map(x=>escapeHtml(x.kind)+": "+x.count).join(" · ")||"No dated upload records in this period"}</small></article></div><div class="performance-columns performance-workflows"><section><h3>Estimator activity</h3>${bars(e.actions)}</section><section><h3>Tender activity</h3>${bars(t.actions)}${t.rowsAdded||t.rowsUpdated?`<p class="helper-text">Excel imports: ${t.rowsAdded} new submissions and ${t.rowsUpdated} updates.</p>`:''}</section><section><h3>Opportunity activity</h3>${bars(o.actions)}${o.rowsAdded||o.rowsUpdated?`<p class="helper-text">Excel imports: ${o.rowsAdded} new opportunities and ${o.rowsUpdated} updates.</p>`:''}</section></div>${recent?`<section class="performance-recent"><h3>Recent activity</h3><p class="helper-text">Latest 30 recorded actions in the selected period. Times shown in Sydney time.</p>${recent}</section>`:''}`;
  }catch(error){if(request===performanceRequest&&dialog.open)body.innerHTML=`<p role="alert">${escapeHtml(error.message)}</p><button type="button" class="button secondary" id="performance-retry">Retry</button>`;const retry=$('#performance-retry');if(retry)retry.onclick=()=>loadPerformance(id);}
}

function contributionDates(){
 const kind=$('#performance-period').value,month=sydneyMonth(),year=month.slice(0,4),box=$('#contribution-dates');
 box.innerHTML=kind==='month'?`<label>Month <input id="contribution-month" type="month" value="${month}"></label>`:kind==='year'?`<label>Year <input id="contribution-year" type="number" min="1900" max="9998" value="${year}"></label>`:kind==='custom'?`<label>From <input id="contribution-from" type="date" value="${month}-01"></label><label>To <input id="contribution-to" type="date" value="${month}-${String(new Date(Number(year),Number(month.slice(5)),0).getDate()).padStart(2,'0')}"></label>`:'';
 box.querySelectorAll('input').forEach(i=>i.onchange=()=>loadPerformance($('#performance-dialog').dataset.userId));
}
function contributionRange(){
 const kind=$('#performance-period').value;
 if(kind==='month'){const m=$('#contribution-month').value;if(!m)return {since:'',until:''};const [y,n]=m.split('-').map(Number);return {since:m+'-01',until:m+'-'+new Date(y,n,0).getDate()};}
 if(kind==='year'){const y=$('#contribution-year').value;return {since:y+'-01-01',until:y+'-12-31'};}
 if(kind==='custom')return {since:$('#contribution-from').value,until:$('#contribution-to').value};
 return {since:'',until:''};
}
