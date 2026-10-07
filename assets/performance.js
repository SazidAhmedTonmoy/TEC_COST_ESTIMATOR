/* v3.3: on-demand administrator contribution view. */
let performanceRequest=0;
function performanceDialog(){
  let dialog=$('#performance-dialog');
  if(dialog)return dialog;
  dialog=document.createElement('dialog');dialog.id='performance-dialog';
  dialog.innerHTML=`<div class="dialog-card"><div class="dialog-heading"><div><span class="eyebrow">CONTRIBUTIONS</span><h2 id="performance-title">View Performance</h2></div><button type="button" class="icon-button" aria-label="Close performance">×</button></div><div class="performance-toolbar"><label>Period <select id="performance-period"><option value="month">This month</option><option value="all">All time</option></select></label><span class="helper-text">Recorded work across Estimator and Tenders</span></div><div id="performance-body" aria-live="polite"></div></div>`;
  document.body.append(dialog);dialog.setAttribute('aria-labelledby','performance-title');
  dialog.querySelector('[aria-label="Close performance"]').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>performanceRequest++);
  $('#performance-period').onchange=()=>loadPerformance(dialog.dataset.userId);
  return dialog;
}
function openPerformance(id){
  const dialog=performanceDialog();dialog.dataset.userId=id;$('#performance-period').value='month';
  if(!dialog.open)dialog.showModal();loadPerformance(id);
}
async function loadPerformance(id){
  const request=++performanceRequest,dialog=performanceDialog(),body=$('#performance-body');
  body.innerHTML='<p class="helper-text">Loading contributions…</p>';
  const since=$('#performance-period').value==='month'?sydneyMonth()+'-01':'';
  try{
    const result=await api(`/api/users/${Number(id)}/performance?since=${encodeURIComponent(since)}`);
    if(request!==performanceRequest||!dialog.open)return;
    $('#performance-title').textContent=result.person.name;
    const bars=rows=>rows.length?rows.map(r=>`<div class="performance-bar"><div><span>${escapeHtml(r.action)}</span><b>${r.count}</b></div><meter min="0" max="${Math.max(...rows.map(x=>x.count),1)}" value="${r.count}" aria-label="${escapeHtml(r.action)}: ${r.count}"></meter></div>`).join(''):'<p class="helper-text">No recorded activity for this period.</p>';
    const e=result.estimator,t=result.tenders,h=result.historical;
    body.innerHTML=`<div class="performance-kpis"><article><span>Estimator projects contributed to</span><strong>${e.projects}</strong><small>${e.total} recorded actions</small></article><article><span>Tender submissions worked on</span><strong>${t.submissions}</strong><small>${t.total} recorded actions · imports counted separately</small></article></div><div class="performance-columns"><section><h3>Estimator activity</h3>${bars(e.actions)}</section><section><h3>Tender activity</h3>${bars(t.actions)}${t.rowsAdded||t.rowsUpdated?`<p class="helper-text">Excel imports: ${t.rowsAdded} new submissions and ${t.rowsUpdated} updates.</p>`:''}</section></div>${h.importedTenders||h.chaseUps?`<section class="performance-historical"><h3>Historical Excel contributions</h3><p>${h.importedTenders?`${h.importedTenders} existing tender submissions uploaded by Tonmoy.`:''}${h.chaseUps?`${h.chaseUps} historical chase-ups performed by Yunus.`:''}</p><small>All time · owner-confirmed attribution; upload/action dates were not recorded. Excluded from website activity above.</small></section>`:''}<section class="performance-recent"><h3>Recent recorded activity</h3>${result.recent.length?result.recent.map(r=>`<article><span class="performance-app">${escapeHtml(r.app)}</span><div><b>${escapeHtml(r.action)}</b><p>${escapeHtml(r.project||'Excel workbook import')}</p></div><time>${escapeHtml(new Date(r.created_at).toLocaleString('en-AU'))}</time></article>`).join(''):'<p class="helper-text">No activity recorded for this period.</p>'}</section><p class="helper-text performance-footnote">Shows up to 30 recent actions. Tender website tracking starts with v3.3; older Estimator actions use existing logs. Counts describe recorded activity, not time spent or work quality. Shared projects may appear for more than one contributor.</p>`;
  }catch(error){if(request===performanceRequest&&dialog.open)body.innerHTML=`<p role="alert">${escapeHtml(error.message)}</p><button type="button" class="button secondary" id="performance-retry">Retry</button>`;const retry=$('#performance-retry');if(retry)retry.onclick=()=>loadPerformance(id);}
}
