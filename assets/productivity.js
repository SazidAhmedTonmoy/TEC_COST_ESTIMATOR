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
  $('#backup-list').innerHTML=result.backups.length?result.backups.map(b=>`<article class="tool-row"><div><strong>${escapeHtml(b.reason||'Backup')}</strong><small>${escapeHtml(b.created_at||b.name)} · ${(b.bytes/1048576).toFixed(1)} MB</small></div><a class="button secondary small" href="/api/backups/${encodeURIComponent(b.name)}/download">Download</a><button class="button secondary small" data-restore-backup="${escapeHtml(b.name)}">Restore</button></article>`).join(''):'<p>No backups yet. The first daily backup is created shortly after the server starts.</p>';
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
  $('#revision-list').innerHTML=rows.length?`<label>Compare selected revision against<select id="revision-compare-target"><option value="current">Current working estimate</option>${rows.map(r=>`<option value="${r.id}">${escapeHtml(r.label)}</option>`).join('')}</select></label>`+rows.map(r=>`<article class="tool-row"><div><strong>${escapeHtml(r.label)}</strong><small>${escapeHtml(r.author||'Unknown')} · ${escapeHtml(new Date(r.created_at).toLocaleString('en-AU'))} · ${escapeHtml(r.currency)} ${fmtMoney(r.quoted,r.currency)}</small></div><div class="revision-actions"><button class="button secondary small" data-compare-revision="${r.id}">View & compare</button><a class="button secondary small" href="/api/projects/${productivityState.revisionProject}/revisions/${r.id}/export">Excel</a>${r.can_delete?`<button class="button secondary small danger-text" data-delete-revision="${r.id}" data-revision-label="${escapeHtml(r.label)}">Delete</button>`:''}</div></article>`).join(''):'<p>No saved revisions. Save Original before making your next changes.</p>';
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
