/* v3.3: on-demand administrator contribution view. */
let performanceRequest=0;
function performanceDialog(){
  let dialog=$('#performance-dialog');
  if(dialog)return dialog;
  dialog=document.createElement('dialog');dialog.id='performance-dialog';
  dialog.innerHTML=`<div class="dialog-card"><div class="dialog-heading"><div><span class="eyebrow">CONTRIBUTIONS</span><h2 id="performance-title">View Contribution</h2></div><button type="button" class="icon-button" aria-label="Close performance">×</button></div><div class="performance-toolbar"><label>Period <select id="performance-period"><option value="all">All Time</option><option value="month">Specific month</option><option value="year">Specific year</option><option value="custom">Custom dates</option></select></label><div id="contribution-dates"></div><span class="helper-text">Recorded work across Estimator and Tenders</span></div><div id="performance-body" aria-live="polite"></div></div>`;
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
    const e=result.estimator,t=result.tenders,h=result.historical,u=result.uploads;
    body.innerHTML=`<div class="performance-kpis"><article><span>Estimator projects contributed to</span><strong>${e.projects}</strong><small>${e.total} recorded actions</small></article><article><span>Tender submissions worked on</span><strong>${t.submissions}</strong><small>${t.total} website actions · ${h.periodChaseUps||0} historical chase-ups in range</small></article><article><span>Documents uploaded</span><strong>${u.total}</strong><small>${u.byType.map(x=>escapeHtml(x.kind)+": "+x.count).join(" · ")||"No dated upload records in this period"}</small></article></div><div class="performance-columns"><section><h3>Estimator activity</h3>${bars(e.actions)}</section><section><h3>Tender activity</h3>${bars(t.actions)}${t.rowsAdded||t.rowsUpdated?`<p class="helper-text">Excel imports: ${t.rowsAdded} new submissions and ${t.rowsUpdated} updates.</p>`:''}</section></div>${h.importedFiles||h.chaseUps?`<section class="performance-historical"><h3>Earlier Excel contributions — All Time</h3><p>${h.importedFiles?`${h.importedFiles} tender Excel files uploaded by ${escapeHtml(result.person.name)}.`:''}${h.chaseUps?`${h.chaseUps} chase-ups performed by ${escapeHtml(result.person.name)}.`:''}</p><small>Uploading a workbook does not count as working on its submissions. Dated chase-ups count in the selected period. The two owner-confirmed historical uploads count under All Time because their dates are unknown.</small></section>`:''}<section class="performance-recent"><h3>Recent recorded activity</h3>${result.recent.length?result.recent.map(r=>`<article><span class="performance-app">${escapeHtml(r.app)}</span><div><b>${escapeHtml(r.action)}</b><p>${escapeHtml(r.project||'Excel workbook import')}</p></div><time>${escapeHtml(new Date(r.created_at).toLocaleString('en-AU'))}</time></article>`).join(''):'<p class="helper-text">No activity recorded for this period.</p>'}</section><p class="helper-text performance-footnote">One document means one retained catalogue workbook, lighting upload/source, project JSON import, completed tender Excel import, or Help attachment. Tonmoy’s two historical tender uploads are included under All Time. Shows up to 30 recent actions. Tender website tracking starts with v3.3; older Estimator actions use existing logs. Counts describe recorded activity, not time spent or work quality. Shared projects may appear for more than one contributor.</p>`;
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
