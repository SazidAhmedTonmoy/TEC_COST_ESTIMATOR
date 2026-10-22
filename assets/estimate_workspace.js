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
