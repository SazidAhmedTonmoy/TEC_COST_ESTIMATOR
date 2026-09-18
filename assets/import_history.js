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
