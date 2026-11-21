/* Productivity tools keep draft fields intact during background refreshes. */
const productivityState={tab:Array.from(crypto.getRandomValues(new Uint32Array(4))).join('-'),presence:null,presenceProject:null,busy:false,revisionProject:null,revisionVersion:null,priceItem:null,preview:null,reminderRequest:0};
async function loadReminders(force=false){
  const uid=state.user?.id;if(!uid)return;
  if(!force && productivityState.reminderUser===uid && Date.now()-(productivityState.reminderFetched||0)<45000)return;
  if(productivityState.reminderPending && productivityState.reminderUser===uid)return productivityState.reminderPending;
  const request=++productivityState.reminderRequest;
  productivityState.reminderUser=uid;
  const task=(async()=>{
    const result=await api('/api/reminders');
    if(uid!==state.user?.id||request!==productivityState.reminderRequest)return;
    workspaceState.reminderRows=result.reminders;
    productivityState.reminderFetched=Date.now();
    renderSchedule();
  })();
  productivityState.reminderPending=task;
  try{return await task;}finally{if(productivityState.reminderPending===task)productivityState.reminderPending=null;}
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
  $('#backup-list').innerHTML=result.backups.length?result.backups.map(b=>{
    const encrypted=b.encrypted===true||String(b.name).endsWith('.db.enc');
    const protection=encrypted?'Encrypted':'Legacy unencrypted';
    return `<article class="tool-row"><div><strong>${b.database==='tenders'?'Tenders':'Catalog / Estimator'} · ${escapeHtml(b.reason||'Backup')}</strong><small>${escapeHtml(b.created_at||b.name)} · ${(b.bytes/1048576).toFixed(1)} MB · ${protection}</small></div><a class="button secondary small" href="/api/backups/${encodeURIComponent(b.name)}/download" title="${encrypted?'Download encrypted backup (.db.enc)':'Download legacy unencrypted backup (.db)'}">Download</a>${b.database==='tenders'?'':`<button class="button secondary small" data-restore-backup="${escapeHtml(b.name)}">Restore</button>`}</article>`;
  }).join(''):'<p>No backups yet. New backups are encrypted. Daily backups are scheduled for 12:10 am server time.</p>';
}
async function openRevisions(pid){
  productivityState.revisionProject=Number(pid);
  productivityState.revisionVersion=state.projectData?.project.id===Number(pid)?state.projectData.project.revision:null;
  productivityState.revisionRows=[];productivityState.revisionSelectedId=null;productivityState.revisionRequest=(productivityState.revisionRequest||0)+1;
  $('#revision-label').value='';$('#revision-comparison').innerHTML='<div class="revision-empty"><h3>Choose a saved revision</h3><p>Select <strong>View</strong> to inspect a saved estimate, or <strong>Compare</strong> to see what changed. Viewing and comparing do not modify your current estimate.</p></div>';
  $('#revision-form').classList.toggle('hidden',!state.projectData?.project.can_edit);
  $('#revision-list').textContent='Loading…';$('#revision-dialog').showModal();
  const result=await api(`/api/projects/${pid}/revisions`);
  if(productivityState.revisionProject===Number(pid))renderRevisions(result.revisions);
}
function revisionRow(id){return (productivityState.revisionRows||[]).find(row=>Number(row.id)===Number(id));}
function markSelectedRevision(id,mode){
 productivityState.revisionSelectedId=Number(id);
 $$('#revision-list .revision-entry').forEach(entry=>{
  const selected=Number(entry.dataset.revisionId)===Number(id);
  entry.classList.toggle('selected',selected);
  entry.querySelectorAll('[data-view-revision],[data-compare-revision]').forEach(button=>button.setAttribute('aria-pressed',String(selected && (mode==='view'?button.hasAttribute('data-view-revision'):button.hasAttribute('data-compare-revision')))));
 });
}
function renderRevisions(rows){
 rows=rows||[];
 productivityState.revisionRows=rows;
 const selected=productivityState.revisionSelectedId;
 if(selected&&!revisionRow(selected)){
  productivityState.revisionSelectedId=null;
  $('#revision-comparison').innerHTML='<div class="revision-empty"><h3>Choose a saved revision</h3><p>Select View to inspect the estimate, or Compare to review changes.</p></div>';
 }
 $('#revision-list').innerHTML=rows.length?`<div class="revision-list-heading"><h3>Saved revisions</h3><span class="pill">${rows.length}</span></div>`+rows.map(r=>`<article class="revision-entry${Number(r.id)===Number(productivityState.revisionSelectedId)?' selected':''}" data-revision-id="${Number(r.id)}"><div class="revision-entry-heading"><strong>${escapeHtml(r.label)}</strong><small>${escapeHtml(r.author||'Unknown')} · ${escapeHtml(new Date(r.created_at).toLocaleString('en-AU'))}</small><b>${escapeHtml(r.currency)} ${fmtMoney(r.quoted,r.currency)}</b></div><div class="revision-entry-actions"><button type="button" class="button secondary small" data-view-revision="${Number(r.id)}">View</button><button type="button" class="button secondary small" data-compare-revision="${Number(r.id)}">Compare</button><a class="button secondary small" href="/api/projects/${productivityState.revisionProject}/revisions/${Number(r.id)}/export">Excel</a></div>${r.can_redeploy||r.can_delete?`<details class="revision-more"><summary>More actions</summary><div class="revision-actions">${r.can_redeploy?`<button type="button" class="button secondary small" data-redeploy-revision="${Number(r.id)}" data-revision-label="${escapeHtml(r.label)}">Restore to working estimate</button>`:''}${r.can_delete?`<button type="button" class="button secondary small danger-text" data-delete-revision="${Number(r.id)}" data-revision-label="${escapeHtml(r.label)}">Delete revision</button>`:''}</div></details>`:''}</article>`).join(''):'<p class="helper-text">No saved revisions yet. Save an Original estimate to start your revision history.</p>';
}
function focusRevisionPanelOnNarrowScreens(){
 // The preview appears below the revision list on phones and tablets.
 if(typeof window!=='undefined'&&window.matchMedia?.('(max-width:900px)').matches){
  $('#revision-comparison')?.scrollIntoView?.({behavior:'smooth',block:'start'});
 }
}
function revisionTotals(totals,currency){
 const metrics=[['material','Materials',false],['hours','Labour hours',true],['labor','Labour cost',false],['quoted','Quoted total',false]];
 return `<div class="revision-metric-grid">${metrics.map(([key,label,hours])=>`<div><small>${label}</small><strong>${hours?fmtNumber(totals?.[key]||0)+' hrs':fmtMoney(totals?.[key]||0,currency)}</strong></div>`).join('')}</div>`;
}
async function viewRevision(rid){
 const pid=productivityState.revisionProject,row=revisionRow(rid);
 if(!row)return;
 const request=++productivityState.revisionRequest;
 markSelectedRevision(rid,'view');
 $('#revision-comparison').innerHTML='<p class="helper-text">Loading saved revision…</p>';
 focusRevisionPanelOnNarrowScreens();
 const result=await api(`/api/projects/${pid}/revisions/${rid}?view=1`);
 if(productivityState.revisionProject!==pid||request!==productivityState.revisionRequest)return;
 const snapshot=result.snapshot||{},saved=snapshot.project||{},lines=snapshot.lines||[];
 const currency=saved.currency||row.currency||'AUD';
 $('#revision-comparison').innerHTML=`<div class="revision-detail-heading"><div><p class="eyebrow">Read-only saved snapshot</p><h3>${escapeHtml(row.label)}</h3><p class="helper-text">Saved by ${escapeHtml(row.author||'Unknown')} · ${escapeHtml(new Date(row.created_at).toLocaleString('en-AU'))}</p></div><span class="revision-readonly">View only</span></div>${revisionTotals(snapshot.totals||{},currency)}<div class="revision-snapshot-heading"><h4>Saved estimate items</h4><span class="pill">${lines.length} items</span></div><div class="table-scroll"><table class="mini-table revision-snapshot-table"><thead><tr><th>Item / reference</th><th>Category</th><th>Quantity</th><th>Quoted</th></tr></thead><tbody>${lines.map(line=>`<tr><td><strong>${escapeHtml(line.name_snapshot||'Item')}</strong>${line.reference_name?`<small>Ref: ${escapeHtml(line.reference_name)}</small>`:''}${line.notes?`<small class="revision-line-notes">Remarks: ${escapeHtml(line.notes)}</small>`:''}</td><td>${escapeHtml(line.category_snapshot||'Other')}</td><td>${fmtNumber(line.quantity||0)} ${escapeHtml(line.uom||'')}</td><td>${fmtMoney(line.quoted_total||0,currency)}</td></tr>`).join('')}</tbody></table></div><p class="revision-readonly-note">This is an archived version. Viewing it does not change your current estimate. Use Compare to check differences or More actions to restore it.</p>`;
}
function showRevisionComparePicker(rid){
 const row=revisionRow(rid);if(!row)return;
 productivityState.revisionRequest=(productivityState.revisionRequest||0)+1;
 markSelectedRevision(rid,'compare');
 const other=(productivityState.revisionRows||[]).filter(r=>Number(r.id)!==Number(rid));
 $('#revision-comparison').innerHTML=`<div class="revision-detail-heading"><div><p class="eyebrow">Revision comparison</p><h3>${escapeHtml(row.label)}</h3><p class="helper-text">Compare this saved revision against another version. No estimate data is changed.</p></div></div><div class="revision-compare-setup"><label>Compare with<select id="revision-compare-target"><option value="current">Current working estimate</option>${other.map(r=>`<option value="${Number(r.id)}">${escapeHtml(r.label)} · ${escapeHtml(new Date(r.created_at).toLocaleDateString('en-AU'))}</option>`).join('')}</select></label><button type="button" class="button primary" data-run-revision-compare="${Number(rid)}">Show differences</button></div><div id="revision-diff-results" class="revision-diff-results"><p class="helper-text">Choose a version and select Show differences. Only changed items and settings will be listed.</p></div>`;
 focusRevisionPanelOnNarrowScreens();
}
async function compareRevision(rid){
 const pid=productivityState.revisionProject,base=revisionRow(rid),select=$('#revision-compare-target');
 if(!base||!select)return;
 const target=select.value,other=target==='current'?null:revisionRow(target);
 if(target!=='current'&&!other)return;
 const request=++productivityState.revisionRequest;
 const slot=$('#revision-diff-results');slot.innerHTML='<p class="helper-text">Comparing saved estimates…</p>';
 const result=await api(`/api/projects/${pid}/revisions/${rid}?compare=${encodeURIComponent(target)}`);
 if(pid!==productivityState.revisionProject||request!==productivityState.revisionRequest)return;
 const c=result.comparison;const sameCurrency=c.before_currency===c.after_currency;
 const money=(n,currency)=>fmtMoney(Number(n||0),currency);
 const cellValue=(row,key,side)=>{
  const field=row.fields?.[key];if(!field)return '—';
  const value=field[side];
  if(value===null||value===undefined)return 'Not present';
  return key==='quantity'?fmtNumber(Number(value)) : key==='quoted_total'?money(value,side==='before'?c.before_currency:c.after_currency):escapeHtml(String(value));
 };
 const prettyField=key=>({reference_name:'Reference',name_snapshot:'Name',category_snapshot:'Category',quantity:'Quantity',quoted_total:'Quoted total',components:'Material / labour components',notes:'Remarks',area_allocations:'Area allocations',supply_unit_cost_override:'Supply allowance',supply_quantity_override:'Supply quantity'}[key]||key.replaceAll('_',' '));
 const val=v=>{
  if(v===null||v===undefined)return '—';
  if(Array.isArray(v))return v.length&&v.every(x=>x&&typeof x==='object'&&!Array.isArray(x))?`<div class="table-scroll"><table class="mini-table revision-component-table"><thead><tr><th>Component</th><th>Qty / item</th><th>Material / unit</th><th>Labour / unit</th></tr></thead><tbody>${v.map(x=>`<tr><td>${escapeHtml(x.description||'Component')}</td><td>${fmtNumber(x.quantity_per_unit||0)} ${escapeHtml(x.uom||'')}</td><td>${fmtMoney(x.unit_material||0)}</td><td>${x.labor_pricing==='fixed'?fmtMoney(x.unit_labor_price||0):fmtNumber(x.unit_hours||0)+' hrs'}</td></tr>`).join('')}</tbody></table></div>`:v.map(x=>escapeHtml(String(x))).join('; ')||'None';
  if(typeof v==='object')return escapeHtml(JSON.stringify(v));
  return escapeHtml(String(v));
 };
 const metricNames=[['material','Material cost'],['hours','Labour hours'],['labor','Labour cost'],['quoted','Quoted total']];
 const metrics=`<div class="table-scroll"><table class="mini-table revision-comparison-table"><thead><tr><th>Metric</th><th>Saved: ${escapeHtml(base.label)}</th><th>${target==='current'?'Current estimate':escapeHtml(other.label)}</th><th>Change</th></tr></thead><tbody>${metricNames.map(([key,label])=>{
   const left=Number(c.before_totals?.[key]||0),right=Number(c.after_totals?.[key]||0),delta=right-left;
   return `<tr><th scope="row">${label}</th><td>${key==='hours'?fmtNumber(left)+' hrs':money(left,c.before_currency)}</td><td>${key==='hours'?fmtNumber(right)+' hrs':money(right,c.after_currency)}</td><td class="revision-delta">${key==='hours'?(delta>0?'+':'')+fmtNumber(delta)+' hrs':sameCurrency?(delta>0?'+':'')+money(delta,c.after_currency):'Different currencies'}</td></tr>`;
  }).join('')}</tbody></table></div>`;
 const changes=c.changes||[],settings=Object.entries(c.settings||{});
 const changeList=changes.length?changes.map(row=>`<details class="revision-diff-item"><summary><span><strong>${escapeHtml(row.name||'Item')}</strong><small>${escapeHtml(row.kind)} · ${Object.keys(row.fields||{}).map(prettyField).join(', ')}</small></span><span class="revision-change-quick">${row.fields?.quantity?`${cellValue(row,'quantity','before')} → ${cellValue(row,'quantity','after')}`:''}</span></summary><div class="table-scroll"><table class="mini-table revision-fields-table"><thead><tr><th>Changed field</th><th>Saved revision</th><th>Compared version</th></tr></thead><tbody>${Object.entries(row.fields||{}).map(([field,v])=>`<tr><th scope="row">${escapeHtml(prettyField(field))}</th><td>${field==='quoted_total'?cellValue(row,field,'before'):val(v.before)}</td><td>${field==='quoted_total'?cellValue(row,field,'after'):val(v.after)}</td></tr>`).join('')}</tbody></table></div></details>`).join(''):'<p class="revision-no-changes">No item changes between these versions.</p>';
 const settingsList=settings.length?`<details class="revision-settings"><summary>${settings.length} project setting${settings.length===1?'':'s'} changed</summary><div class="table-scroll"><table class="mini-table"><thead><tr><th>Setting</th><th>Saved revision</th><th>Compared version</th></tr></thead><tbody>${settings.map(([key,v])=>`<tr><th scope="row">${escapeHtml(prettyField(key))}</th><td>${val(v.before)}</td><td>${val(v.after)}</td></tr>`).join('')}</tbody></table></div></details>`:'';
 slot.innerHTML=`<div class="revision-compare-result-title"><h4>Differences</h4><span class="pill">${changes.length} item${changes.length===1?'':'s'} changed</span></div>${!sameCurrency?'<p class="helper-text">These versions use different currencies. Monetary changes are not converted.</p>':''}${metrics}<div class="revision-changes-heading"><h4>Changed estimate items</h4><small>Select an item to see its before-and-after values</small></div>${changeList}${settingsList}`;
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
  $('#revision-dialog').addEventListener('change',event=>{
    if(event.target.id==='revision-compare-target')$('#revision-diff-results').innerHTML='<p class="helper-text">Comparison target changed. Select Show differences to update the report.</p>';
  });
  $('#revision-form').addEventListener('submit',event=>submitWithButton(event,async()=>{const pid=productivityState.revisionProject;const result=await api(`/api/projects/${pid}/revisions`,{method:'POST',body:{label:$('#revision-label').value,expected_revision:productivityState.revisionVersion}});renderRevisions(result.revisions);$('#revision-label').value='';toast('Tender revision saved');}));
  $('#price-source-form').addEventListener('submit',event=>submitWithButton(event,async()=>{const result=await api(`/api/catalog/${productivityState.priceItem}/price-history`,{method:'POST',body:{supplier:$('#price-supplier').value,quote_date:$('#price-date').value,source:$('#price-source').value}});renderPriceHistory(result);toast('Price source recorded');}));
  document.addEventListener('click',async event=>{
    const target=event.target.closest('button');if(!target)return;
    try{
      if(target.dataset.close)$('#'+target.dataset.close).close();
      if(target.dataset.revisions)await openRevisions(target.dataset.revisions);
      if(target.dataset.viewRevision)await viewRevision(target.dataset.viewRevision);
      if(target.dataset.compareRevision)showRevisionComparePicker(target.dataset.compareRevision);
      if(target.dataset.runRevisionCompare)await compareRevision(target.dataset.runRevisionCompare);
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
        if(pid===productivityState.revisionProject)renderRevisions(result.revisions);
        toast('Revision deleted');
      }
      if(target.dataset.priceHistory)await openPriceHistory(target.dataset.priceHistory);
      if(target.dataset.readReminder){await api('/api/reminders/read',{method:'POST',body:{key:target.dataset.readReminder}});await loadReminders(true);}
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
