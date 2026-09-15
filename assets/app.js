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

async function api(path, options = {}) {
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
    config.headers["Content-Type"] = "application/json";
    config.body = JSON.stringify(config.body);
  }
  const response = await fetch(path, config);
  const contentType = response.headers.get("content-type") || "";
  const result = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok || (result && result.success === false)) {
    if (response.status === 401 && path !== '/api/auth/login') showLogin();
    const error = new Error(result?.error || result?.message || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return result;
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
  const titles = { 'light-prices':'Light price check', home: 'Home', calendar: 'Deadline calendar', users: 'Manage users', profile: 'My profile', estimate: "Build estimate", catalog: "Catalog Explorer", imports: "Import workbooks", settings: "Application settings" };
  $("#view-title").textContent = titles[name] || "TEC ConEst";
  $("#export-button").classList.toggle("hidden", name !== "estimate");
  $("#floating-search-button").classList.toggle("hidden", name !== "estimate");
  syncCategoryToggle();
  $('#project-select').classList.toggle('hidden', name !== 'estimate');
  $('#delete-project-button').classList.toggle('hidden', name !== 'estimate');
  $('#new-project-button').classList.toggle('hidden', Boolean(state.user?.must_change_password));
  if (name === 'home') { renderHome(); if (load) loadDashboard().catch(error => toast(error.message,true)); }
  if (name === 'calendar') { renderCalendar(); if (load) loadDashboard().then(renderCalendar).catch(error => toast(error.message,true)); }
  if (name === 'profile') renderProfile();
  if (load && name === 'users') loadUsers().catch(error => toast(error.message,true));
  if (load && name === "catalog") loadCatalog();
  if (load && name === "light-prices") loadLightPrices().catch(error=>toast(error.message,true));
  if (load && name === "imports") loadImports();
  if (load && name === "settings") {loadSettings(); if(typeof loadBackups==='function')loadBackups().catch(error=>toast(error.message,true));}
}

async function loadDashboard(reloadEstimate = true) {
  const result = await api("/api/dashboard");
  state.dashboard = result;
  state.projects = result.projects;
  state.catalogCategories = result.catalog?.categories || [];
  $("#system-status").textContent = `${result.counts.catalog_items.toLocaleString()} unique items · ${result.counts.source_variants.toLocaleString()} source records`;
  renderCatalogCategoryFilter();
  renderProjectSelect();
  $("#category-options").innerHTML = (result.manual_options?.categories || []).map((category) => `<option value="${escapeHtml(category)}">`).join("");
  if (!state.projects.some((project) => project.id === state.projectId && project.can_view)) state.projectId = null;
  if (state.projectId) { if(reloadEstimate) await loadProject(state.projectId); }
  else { state.projectData = null; renderProject(); }
  renderProjectSelect();
  renderHome();
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
}

async function loadProject(projectId) {
  const request=state.projectLoadRequest=(state.projectLoadRequest||0)+1;
  if (!projectId) { state.projectId = null; state.projectData = null; renderProject(); if(typeof rememberPage==='function')rememberPage('estimate'); return; }
  const result = await api(`/api/projects/${projectId}`);
  if(request!==state.projectLoadRequest)return false;
  await reviewOpenedProject(result.project);
  if(request!==state.projectLoadRequest)return false;
  state.projectId = Number(projectId);
  state.projectData = result;
  renderProjectSelect();
  renderProject();
  if(state.view==='estimate' && typeof rememberPage==='function') rememberPage('estimate');
  return result;
}

function renderProject() {
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
  $("#project-client").value = project.client || "";
  $("#project-currency").value = project.currency || "AUD";
  $("#project-material-markup").value = Number(project.material_markup || 0) * 100;
  $("#project-labour-rate").value = Number(project.labor_rate || 0);
  $("#project-overhead-markup").value = Number(project.overhead_markup || 0) * 100;
  $("#empty-estimate").classList.toggle("hidden", lines.length > 0);
  $('#delete-project-button').disabled = !available || !project.can_delete;
  renderGroupedEstimate(lines);
  renderEstimateBrief(project);
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
  const categories=[...new Set([...(state.dashboard?.manual_options?.categories||[]),...(state.catalogCategories||[]).map(c=>c.name),...(state.projectData?.lines||[]).map(l=>l.category_snapshot)].filter(Boolean))];
  const matches=categories.sort((a,b)=>{const am=!showAll&&query&&a.toLowerCase().includes(query),bm=!showAll&&query&&b.toLowerCase().includes(query);return Number(bm)-Number(am)||a.localeCompare(b);});
  const box=field.parentElement.querySelector('.category-suggestions');
  box.innerHTML=matches.map(c=>`<button class="category-choice" type="button" data-category="${escapeHtml(c)}">${escapeHtml(c)}</button>`).join('');
  box.classList.toggle('hidden',!matches.length);
}

function renderScopeBreakdown(data) {
  const summary = (state.summaryMode==='work'?data.work_summary:data.scope_summary) || [];
  function summaryRow(row,child=false){return `<tr class="${child?'scope-subcategory':''}"><td>${escapeHtml(row.category)}</td><td>${child?'':row.assemblies}</td><td>${fmtMoney(row.material)}</td><td>${fmtNumber(row.hours)} hrs</td><td>${fmtMoney(row.labor)}</td><td><strong>${fmtMoney(row.quoted)}</strong></td></tr>`;}
  $('#scope-breakdown-rows').innerHTML=summary.length?summary.map(row=>summaryRow(row)+(row.subcategories||[]).map(child=>summaryRow(child,true)).join('')).join(''):'<tr><td colspan="6" class="scope-empty">Add estimate items to see the breakdown.</td></tr>';
  const totals = data.totals;
  $("#scope-breakdown-total").innerHTML = `<tr><td>TOTAL</td><td>${data.lines.length}</td><td>${fmtMoney(totals.material)}</td><td>${fmtNumber(totals.hours)} hrs</td><td>${fmtMoney(totals.labor)}</td><td>${fmtMoney(totals.quoted)}</td></tr>`;
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
    await loadDashboard();
    toast("Project deleted");
  } finally {
    $("#delete-project-button").disabled = !state.projectData;
    $("#project-select").disabled = !state.projects.length;
  }
}

async function updateLineCategory(lineId, value) {
  const result = await api(`/api/projects/${state.projectId}/lines/${lineId}`, { method:"PATCH", body:{ category_snapshot:value.trim() || "Other" } });
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

async function runQuickSearch() {
  clearTimeout(state.quickSearchTimer);
  const request = ++state.quickSearchRequest;
  const query = $("#quick-search-input").value.trim();
  const box = $("#quick-search-results");
  if (!query) { box.innerHTML = `<p class="helper-text">Type an item title to find it.</p>`; return; }
  box.innerHTML = `<p class="helper-text">Searching…</p>`;
  const result = await api(`/api/catalog/search?q=${encodeURIComponent(query)}&limit=20`);
  if (request !== state.quickSearchRequest) return;
  box.innerHTML = result.results.length ? result.results.map((item) => `<article class="quick-search-result"><div><strong>${catalogName(item)}</strong><small>${escapeHtml(item.category)} · ${escapeHtml(workTypeLabel(item.pricing_work_type || item.work_type))} / ${escapeHtml(item.base_uom || "EA")}</small><small>Material ${fmtMoney(item.unit_material)} · Labour ${catalogLaborLabel(item)}</small></div><div><button class="button primary small quick-add" type="button" data-id="${item.id}" data-name="${escapeHtml(item.name)}" data-unit="${escapeHtml(item.base_uom || "EA")}">Add</button><button class="text-button quick-edit-add" type="button" data-id="${item.id}">Edit & add</button></div></article>`).join("") : `<p class="helper-text">No matching item. Try another search or add a manual item.</p>`;
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
  const details = (line.components || []).map((component) => `
    <tr class="detail-row hidden-row" data-parent="${line.id}" data-component-id="${component.id}">
      <td class="assembly-cell"><span class="drag-handle" draggable="true" data-drag-kind="component" data-line-id="${line.id}" data-component-id="${component.id}" title="Drag component">⠿</span><button class="component-copy-live" data-line-id="${line.id}" data-component-id="${component.id}" title="Copy component below" aria-label="Copy component">+</button>${componentLabel(component)}</td>
      <td>${fmtNumber(component.scaled_quantity)} ${escapeHtml(component.uom || "")}</td>
      <td>${component.is_supply_allowance?fmtMoney(component.unit_material):"—"}</td><td>${component.is_supply_allowance?"—":fmtMoney(component.unit_material)}</td>
      <td>${fmtMoney(component.total_material)}</td>
      <td>${componentLaborLabel(component)}</td>
      <td>${fmtNumber(component.total_hours)}</td>
      <td>${fmtMoney(component.total_labor)}</td>
      <td>${fmtMoney(component.grand_total)}</td>
      <td>—</td><td></td>
    </tr>`).join("");
  return `
    <tr class="assembly-row" data-line-id="${line.id}">
      <td class="assembly-cell"><div class="assembly-title">
        <button class="toggle-details" data-line-id="${line.id}" aria-label="Expand component details" aria-expanded="false">+</button>
        <div class="assembly-copy">
          <div class="line-heading-grid">
            <div class="assembly-name-row"><span class="drag-handle" draggable="true" data-drag-kind="line" data-line-id="${line.id}" title="Drag item within this category">⠿</span><textarea class="line-estimate-name" data-line-id="${line.id}" rows="1" maxlength="500" aria-label="Estimate item name">${escapeHtml(line.display_name || cleanEstimateTitle(line.name_snapshot))}</textarea></div>
            <label class="line-category-label">Category<div class="category-editor" data-value="${escapeHtml(category)}"><textarea class="line-category" data-line-id="${line.id}" rows="1" maxlength="120" aria-label="Scope or category for ${escapeHtml(line.name_snapshot)}" title="Choose or type a category; saves when you leave this field">${escapeHtml(category)}</textarea><div class="category-suggestions hidden" aria-label="Suggested categories"></div></div></label>
          </div>
          <div class="line-bottom-row">
            ${line.has_supply_allowance?`<label class="compact-supply">Supply cost / unit<input class="line-supply-cost" data-line-id="${line.id}" type="number" min="0" step="any" value="${line.supply_unit_cost}" title="Supplier price for one fitting, before mark-ups. Saved only with this estimate."></label>`:''}
            <span class="line-detail-count">${line.components.length} components</span>
            <div class="assembly-actions"><button class="text-button edit-estimate-line" data-line-id="${line.id}">Edit item / components</button><button class="text-button copy-estimate-line" data-line-id="${line.id}">Copy item</button></div>
          </div>
        </div></div></td>
      <td><input class="line-quantity" data-line-id="${line.id}" type="number" min="0" step="any" value="${Number(line.quantity)}" aria-label="Estimate quantity"><small class="line-unit">${escapeHtml(line.uom || "EA")}</small></td>
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
      <span class="suggestion-meta"><em class="data-status ${escapeHtml(item.data_status)}">${(item.pricing_label || dataStatusLabel(item.data_status))}</em>${fmtMoney(item.unit_material)} · ${catalogLaborLabel(item)}</span>
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

async function loadSmartSuggestions() {
  const input = $("#smart-search-input");
  const text = input.value.trim();
  if (text.length < 2) {
    hideSmartSuggestions();
    return;
  }
  const requestId = ++suggestionRequestId;
  const query = text
    .replace(/\b(?:qty|quantity)\s*[:=]?\s*\d+(?:\.\d+)?\b/ig, " ")
    .replace(/^\s*\d+(?:\.\d+)?\s*[x×]\s*/i, "")
    .trim() || text;
  try {
    const result = await api(`/api/catalog/search?q=${encodeURIComponent(query)}&limit=8`);
    if (requestId !== suggestionRequestId || input.value.trim() !== text) return;
    renderSmartSuggestions(result.results || []);
  } catch (_) {
    if (requestId === suggestionRequestId) hideSmartSuggestions();
  }
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
    <tr><td>${componentLabel(component)}</td><td>${fmtNumber(component.quantity_per_unit, 4)} ${escapeHtml(component.uom || "")}</td><td>${fmtMoney(component.unit_material)}</td><td>${componentLaborLabel(component)}</td></tr>`).join("");
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
      <div class="result-cost"><span>Material / unit<strong>${fmtMoney(item.unit_material)}</strong></span><span>Labour / unit<strong>${catalogLaborLabel(item)}</strong></span><button class="button secondary search-delete-item" type="button" data-id="${item.id}">Delete</button><button class="button secondary edit-add-result" data-id="${item.id}">Edit & add</button><button class="button primary add-result" data-id="${item.id}" data-query="${escapeHtml(query)}">Add to estimate</button></div>
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
      <div class="result-cost"><span>Material / unit<strong>${fmtMoney(item.unit_material)}</strong></span><span>Labour / unit<strong>${catalogLaborLabel(item)}</strong></span>${Number(item.variant_count || 1) > 1 ? `<button class="button tertiary small compare-variants" data-id="${item.id}" data-query="${escapeHtml(item.name)}">Versions</button>` : ""}<button class="button secondary search-delete-item" type="button" data-id="${item.id}">Delete</button><button class="button secondary edit-add-result" data-id="${item.id}">Edit & add</button><button class="button primary add-result" data-id="${item.id}" data-query="${escapeHtml(result.original)}">Add</button></div>
    </article>`).join("");
}

async function addCatalogItem(itemId, query = "", quantity = null) {
  if (!state.projectId) throw new Error("Create a project first");
  const qty = quantity ?? Number($("#smart-quantity").value || 1);
  const result = await api(`/api/projects/${state.projectId}/lines`, {
    method: "POST",
    body: { catalog_item_id: Number(itemId), quantity: qty, query },
  });
  state.projectData = result;
  renderProject();
  $("#search-results").classList.add("hidden");
  toast("Assembly added with all component rows");
}

async function updateLineQuantity(lineId, value) {
  const quantity = Number(value);
  if (!Number.isFinite(quantity) || quantity < 0) { toast("Quantity must be zero or greater", true); renderProject(); return; }
  const result = await api(`/api/projects/${state.projectId}/lines/${lineId}`, { method: "PATCH", body: { quantity } });
  state.projectData = result;
  renderProject();
}

async function removeLine(lineId) {
  const result = await api(`/api/projects/${state.projectId}/lines/${lineId}`, { method: "DELETE", body: {} });
  state.projectData = result;
  renderProject();
  toast("Assembly removed");
}

async function saveProjectSettings(event) {
  event.preventDefault();
  const payload = {
    name: $("#project-name").value,
    client: $("#project-client").value,
    currency: $("#project-currency").value,
    material_markup: Number($("#project-material-markup").value || 0) / 100,
    labor_rate: Number($("#project-labour-rate").value || 0),
    overhead_markup: Number($("#project-overhead-markup").value || 0) / 100,
    hours_per_day: Number($("#project-hours-per-day").value || 8),
    crew_size: Number($("#project-crew-size").value || 2),
  };
  const result = await api(`/api/projects/${state.projectId}`, { method: "PATCH", body: payload });
  state.projectData = result;
  await loadDashboard();
  $("#project-settings-form").classList.remove("hidden");
  toast("Project rates updated; all totals recalculated");
}

async function createNewProject(event) {
  event.preventDefault();
  const settings = state.appSettings || await loadSettings(false);
  const payload = {
    name: $("#new-project-name").value,
    client: $("#new-project-client").value,
    scope_of_work: $('#new-project-scope').value,
    submission_deadline: $('#new-project-deadline').value,
    currency: settings.currency || "AUD",
    material_markup: Number(settings.default_material_markup || .15),
    labor_rate: Number(settings.default_labor_rate || 120),
    crew_size: Number(settings.default_crew_size || 2),
    hours_per_day: Number(settings.default_hours_per_day || 8),
    overhead_markup: Number(settings.default_overhead_markup || .10),
  };
  const result = await api("/api/projects", { method: "POST", body: payload });
  state.projectId = result.project.id;
  $("#project-dialog").close();
  $("#new-project-form").reset();
  await loadDashboard();
  setView('estimate', false);
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
    <td data-label="Description"><span class="drag-handle" draggable="true" data-drag-kind="manual" title="Drag component">⠿</span><button class="copy-manual-component" type="button" title="Copy component below" aria-label="Copy component">+</button><input class="component-description" aria-label="Detail description" required value="${escapeHtml(component.description || "")}" placeholder="Product, material or work description">
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

function readManualComponents() {
  const workType = $("#manual-work-type").value;
  return $$("#manual-components .manual-component").map((row, index) => {
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
  const markup = Number(project?.material_markup ?? state.appSettings?.default_material_markup ?? .15);
  const overhead = Number(project?.overhead_markup ?? state.appSettings?.default_overhead_markup ?? .10);
  const quotedUnit = (material * (1 + markup) + hours * rate + fixed) * (1 + overhead);
  const unit = escapeHtml($("#manual-uom").value || "unit");
  const qty = Number($("#manual-quantity").value);
  $("#manual-cost-preview").innerHTML = `<span>Base material / ${unit}<strong>${fmtMoney(material)}</strong></span><span>Labour / ${unit}<strong>${fmtNumber(hours)} hrs + ${fmtMoney(fixed)} fixed</strong></span><span>Quoted price / ${unit}<strong>${fmtMoney(quotedUnit)}</strong></span>${state.manualAddToEstimate ? `<span>Estimate total · ${fmtNumber(qty)} ${unit}<strong>${fmtMoney(quotedUnit * qty)}</strong></span>` : ""}<small>Preview uses ${fmtMoney(rate)}/hr, ${fmtNumber(markup * 100)}% material mark-up and ${fmtNumber(overhead * 100)}% final mark-up. ${state.manualAddToEstimate ? "Lighting fitting supply prices are saved only with this estimate." : "Existing estimates retain their saved prices."}</small>`;
}

function openManualDialog(addToEstimate = false, sourceItem = null, editExisting = false, lineId = null, quantityOverride = null) {
  if (!state.dashboard?.manual_options) { toast("Catalog is still loading. Please try again.", true); return; }
  state.manualAddToEstimate = addToEstimate;
  state.manualEditId = editExisting && sourceItem?.id ? sourceItem.id : null;
  state.manualLineId = lineId;
  state.manualLineRevision = state.projectData?.lines.find(l=>l.id===lineId)?.revision;
  state.manualProjectId = state.projectId;
  state.manualSource = sourceItem || {};
  state.manualSaving = false;
  $("#manual-save-error").classList.add("hidden");
  $("#manual-item-form").reset();
  const options = state.dashboard.manual_options;
  $("#manual-category").value = sourceItem?.category_override || sourceItem?.category || "Lighting";
  $("#manual-work-type").innerHTML = Object.entries(options.work_types).map(([value, label]) => `<option value="${value}">${escapeHtml(label)}</option>`).join("");
  $("#manual-work-type").value = sourceItem?.work_type || "supply_install";
  $("#manual-name").value = sourceItem?.display_name || cleanEstimateTitle(sourceItem?.name || "");
  $('#manual-assembly-size').value=sourceItem?.assembly_size || '';
  $('#manual-save-mode-label').classList.toggle('hidden',!addToEstimate||!sourceItem);
  $('#manual-save-mode').innerHTML=(sourceItem?'<option value="estimate">Save this estimate only</option>':'')+(sourceItem?.id?'<option value="update">Update existing catalog item</option>':'')+'<option value="new">Save as a new catalog item</option>';
  $('#manual-save-mode').value='new';
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
    estimate_quantity: line.quantity,
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
    assembly_size:$("#manual-assembly-size").value.trim(), code: state.manualSource.code || "", name: $("#manual-name").value.trim(),
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
      result = await api(path, { method: "POST", body: { save_mode:$("#manual-save-mode").value || "new", item: payload, quantity: Number($("#manual-quantity").value), ...(state.manualLineId ? {expected_revision:state.manualLineRevision}: {}) } });
      state.projectData = result;
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
  toast(state.manualLineId ? "Estimate saved" : state.manualAddToEstimate ? "Estimate changes saved" : "Catalog changes saved for future use");
  // A rendering/refresh failure must not turn a successful write into a retry.
  try {
    state.catalogCache.clear();hideSmartSuggestions();hideCatalogHover(0);
    if(state.manualAddToEstimate){renderProject();$("#search-results").classList.add("hidden");}
    await loadDashboard();
    if (!state.manualAddToEstimate) {
      $("#catalog-category").value = "";
      $("#catalog-search-input").value = result.item.display_name || cleanEstimateTitle(result.item.name);
      await loadCatalog();
      await showCatalogDetail(result.item.id);
    }
  } catch (_) { toast("Saved successfully. Refresh the page to reload the catalog."); }
}

let catalogSearchTimer, catalogSearchRequest=0;
async function loadCatalog(query = null) {
  const request=++catalogSearchRequest;
  const term = query ?? $("#catalog-search-input").value.trim();
  const category = $("#catalog-category")?.value || "";
  const includeIncomplete = $("#catalog-show-incomplete")?.checked ? "1" : "0";
  const result = await api(`/api/catalog/search?q=${encodeURIComponent(term)}&category=${encodeURIComponent(category)}&include_incomplete=${includeIncomplete}&limit=60`);
  if(request!==catalogSearchRequest)return;
  const box = $("#catalog-results");
  if (!result.results.length) {
    box.innerHTML = `<div class="empty-state"><p>No catalog results found.</p></div>`;
    return;
  }
  box.innerHTML = result.results.map((item) => `<a href="#/catalog/${item.id}" class="catalog-result catalog-peek" data-id="${item.id}" data-catalog-preview="${item.id}"><span><strong>${catalogName(item)}</strong><small>${escapeHtml(item.category || "Other")} · ${escapeHtml(workTypeLabel(item.pricing_work_type || item.work_type))} / ${escapeHtml(item.base_uom || "EA")}<br>${variantText(item)} · ${Number(item.component_count || 0)} detail rows</small></span><em class="data-status ${escapeHtml(item.data_status)}">${(item.pricing_label || dataStatusLabel(item.data_status))}</em></a>`).join("");
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
  const componentRows = item.components.map((component) => `<tr><td>${componentLabel(component)}</td><td>${fmtNumber(component.quantity_per_unit, 4)}</td><td>${escapeHtml(component.uom || "")}</td><td>${fmtMoney(component.unit_material)}</td><td>${componentLaborLabel(component)}</td></tr>`).join("");
  const sources = item.occurrences.length ? item.occurrences.map((source) => `<span class="source-chip">${escapeHtml(source.project_name || source.file_name)} · ${escapeHtml(source.sheet_name || "")} · row ${source.source_row || "—"}</span>`).join("") : `<span class="source-chip">Manual catalog</span>`;
  const variants = (item.variants || []).map((variant) => `<a href="#/catalog/${variant.id}" class="variant-option${Number(variant.id) === Number(item.id) ? " active" : ""}" data-variant-id="${variant.id}"><span><strong>${escapeHtml(variant.specification || variant.name || "Saved option")}</strong><small>${escapeHtml(variant.source_file || "Manual catalog")} · ${variant.component_count} rows</small></span><span><b>${fmtMoney(variant.unit_material)}</b><small>${catalogLaborLabel(variant)}</small></span><em class="data-status ${escapeHtml(variant.data_status)}">${dataStatusLabel(variant.data_status)}</em></a>`).join("");
  $("#catalog-detail").classList.remove("empty-detail");
  $("#catalog-detail").innerHTML = `
    <div class="detail-header"><div><h3>${catalogName(item)}</h3><p>${escapeHtml(item.category || "Other")} · ${escapeHtml(workTypeLabel(item.pricing_work_type || item.work_type))} / ${escapeHtml(item.base_uom || "EA")}</p><div class="result-tags"><span class="data-status ${escapeHtml(item.data_status)}">${(item.pricing_label || dataStatusLabel(item.data_status))}</span><span>${(item.components || []).length} components</span><span>${variantText(item)}</span></div></div><div><button class="button primary small detail-add" data-id="${item.id}">Add to estimate</button> <button class="button secondary small detail-edit-add">Edit & add</button> <button class="button secondary small detail-edit">Edit catalog item</button> <button class="button secondary small detail-clone">${item.is_manual ? "Save as new version" : "Create editable version"}</button></div></div>
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
    <tr><td>${componentLabel(component)}</td><td>${fmtNumber(component.quantity_per_unit, 3)} ${escapeHtml(component.uom || "")}</td><td>${fmtMoney(component.unit_material)}</td><td>${componentLaborLabel(component)}</td></tr>`).join("");
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
  const sourcesResult = await api("/api/imports");
  const sources = sourcesResult.sources;
  $("#source-count").textContent = `${sources.length} sheets`;
  $("#source-rows").innerHTML = sources.map((source) => `<tr><td class="file-cell"><strong>${escapeHtml(source.file_name)}</strong><small>${escapeHtml(source.sheet_name)}</small></td><td>${escapeHtml(source.project_name || "—")}</td><td>${escapeHtml(source.import_format)}</td><td>${source.row_count.toLocaleString()}</td><td>${source.assembly_count.toLocaleString()}</td><td>${source.component_count.toLocaleString()}</td><td>${source.warning_count || "—"}</td></tr>`).join("");
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

async function loadSettings(render = true) {
  const result = await api("/api/settings");
  state.appSettings = result.settings;
  if (render) {
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
  $("#smart-search-suggestions").addEventListener("mousedown", (event) => event.preventDefault());
  $("#smart-search-suggestions").addEventListener("click", (event) => {
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
      const rows = $$(`.detail-row[data-parent="${toggle.dataset.lineId}"]`);
      const hiding = !rows[0]?.classList.contains("hidden-row");
      rows.forEach((row) => row.classList.toggle("hidden-row", hiding));
      toggle.textContent = hiding ? "+" : "−";
      toggle.setAttribute("aria-expanded",String(!hiding));
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
    const key=field.matches('.line-estimate-size')?'size_snapshot':field.matches('.line-work-type')?'work_type_snapshot':field.matches('.line-estimate-name')?'name_snapshot':field.matches('.line-supply-quantity')?'supply_quantity_override':field.matches('.line-supply-cost')?'supply_unit_cost_override':null;
    if(key){
      const value=['name_snapshot','work_type_snapshot','size_snapshot'].includes(key)?field.value:field.value===''?null:Number(field.value);
      field.disabled=true;
      api(`/api/projects/${state.projectId}/lines/${field.dataset.lineId}`,{method:'PATCH',body:{[key]:value}}).then(result=>{state.projectData=result;renderProject();}).catch(error=>{field.disabled=false;toast(error.message,true);});
    }
    if (event.target.matches(".line-category")) updateLineCategory(event.target.dataset.lineId, event.target.value).catch((error) => { toast(error.message, true); renderProject(); });
    if (event.target.matches(".line-quantity")) updateLineQuantity(event.target.dataset.lineId, event.target.value).catch((error) => toast(error.message, true));
  });
  $("#toggle-project-settings").addEventListener("click", () => $("#project-settings-form").classList.toggle("hidden"));
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
  $("#new-project-button").addEventListener("click", () => {
    const now=new Date(),today=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
    $('#new-project-deadline').min=today;$('#project-dialog').showModal();
  });
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
  $("#catalog-show-incomplete").addEventListener("change", () => loadCatalog().catch((error) => toast(error.message, true)));
  $("#catalog-results").addEventListener("click", (event) => {
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
    if (event.target.closest(".detail-edit-add")) openManualDialog(true, state.currentCatalogItem);
  });
  $("#import-form").addEventListener("submit", importWorkbook);
  $("#import-file").addEventListener("change", (event) => { if (event.target.files[0]) $("#drop-zone strong").textContent = event.target.files[0].name; });
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
  bindEvents();
  bindWorkspaceEvents();
  if(typeof bindProductivityEvents==='function')bindProductivityEvents();
  await bootWorkspace();
});
