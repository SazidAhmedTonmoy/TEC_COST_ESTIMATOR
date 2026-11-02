/* v3.7.12: Project Breakdown is the only allocation editor; catalogue and prices are never duplicated. */
(() => {
 const COMMON='Common to All Areas', UNALLOCATED='Unallocated';
 const fmt=(n)=>Number(n||0).toLocaleString('en-AU',{maximumFractionDigits:3});
 const money=(n,c='AUD')=>`${c} ${Number(n||0).toLocaleString('en-AU',{minimumFractionDigits:2,maximumFractionDigits:2})}`;
 const qnum=v=>Number.isFinite(Number(v))?Math.max(0,Number(v)):0;
 const safe=v=>escapeHtml(String(v??''));
 document.addEventListener('click',ev=>{
  if(!ev.target.closest('[data-breakdown]'))return;
  const project=state.projectData;
  if(!project||!project.lines)return;
  if(typeof hasUncommittedProjectSettings==='function'&&hasUncommittedProjectSettings()){
   if(typeof toast==='function')toast('Finish saving the project details before editing the breakdown.',true);
   return;
  }
  const pid=state.projectId,lines=project.lines,currency=project.project.currency||'AUD';
  let names=[...(project.area_names||[])];
  for(const line of lines)for(const a of JSON.parse(line.area_allocations||'[]')){
   if(![COMMON,UNALLOCATED,'Shared / Unallocated'].includes(a.area)&&!names.some(n=>n.toLowerCase()===a.area.toLowerCase()))names.push(a.area);
  }
  if(!names.length)names=['Area 1'];
  const entries=lines.map(line=>{
   const allocations=JSON.parse(line.area_allocations||'[]');
   const common=allocations.find(a=>a.area===COMMON);
   const legacyUnallocated=allocations.some(a=>a.area==='Shared / Unallocated');
   const areaAllocations=allocations.filter(a=>a.area!==COMMON);
   const positive=areaAllocations.filter(a=>Number(a.quantity)>0);
   return {line,quantity:Number(line.quantity),mode:common?'common':legacyUnallocated||!areaAllocations.length?'unallocated':allocations.some(a=>a.shared)||positive.length>1?'multiple':'single',
    target:positive[0]?.area||names[0],values:Object.fromEntries(areaAllocations.map(a=>[a.area,Number(a.quantity)])),
    original:allocations,edited:false};
  });
  const d=document.createElement('dialog');d.className='area-dialog breakdown-matrix breakdown-v3712';d.setAttribute('aria-label','Project breakdown');document.body.append(d);
  let tab='allocate',query='',treeState='collapsed',busy=false,unallocatedOnly=false;
  const preferenceKey=`conest.breakdown.expanded.${state.user?.id||'guest'}.${pid}`;
  let openNodes=new Set();
  try{const saved=JSON.parse(localStorage.getItem(preferenceKey)||'[]');if(Array.isArray(saved))openNodes=new Set(saved.filter(x=>typeof x==='string').slice(0,1500));}catch(_){}
  const saveExpanded=()=>{try{localStorage.setItem(preferenceKey,JSON.stringify([...openNodes].slice(0,1500)));}catch(_){}};
  const nodeKey=(kind,...parts)=>[kind,...parts.map(p=>encodeURIComponent(String(p)))].join('|');
  const unallocatedEntry=e=>e.quantity>0&&(e.mode==='unallocated'||remainder(e)>0.000001);
  const unallocatedCount=()=>entries.filter(unallocatedEntry).length;
  const undoStack=[],redoStack=[];
  const snapshot=()=>JSON.stringify({names,entries:entries.map(e=>({quantity:e.quantity,mode:e.mode,target:e.target,values:{...e.values},edited:e.edited}))});
  const openedSnapshot=snapshot();let typedUnsaved=false,savedSuccessfully=false;
  const dirtyBreakdown=()=>typedUnsaved||snapshot()!==openedSnapshot;
  const requestClose=()=>{
   if(busy){invalid('Saving in progress. Check the result before closing.');return;}
   if(dirtyBreakdown()&&!confirm('Discard unsaved Breakdown changes?'))return;
   d.close();
  };
  const beforeLeave=event=>{if(dirtyBreakdown()&&!savedSuccessfully){event.preventDefault();event.returnValue='';}};
  window.addEventListener('beforeunload',beforeLeave);
  d.addEventListener('cancel',event=>{event.preventDefault();requestClose();});
  d.addEventListener('input',event=>{if(event.target.matches('[data-name],[data-total],[data-item]'))typedUnsaved=true;});
  const pushHistory=(previous=snapshot())=>{if(undoStack.at(-1)!==previous){undoStack.push(previous);if(undoStack.length>50)undoStack.shift();}redoStack.length=0;};
  const restoreSnapshot=data=>{const saved=JSON.parse(data);names=[...saved.names];saved.entries.forEach((row,i)=>{if(entries[i])Object.assign(entries[i],row)});render();};
  const historyAction=direction=>{const from=direction==='undo'?undoStack:redoStack,to=direction==='undo'?redoStack:undoStack;if(!from.length)return;const current=snapshot();to.push(current);restoreSnapshot(from.pop());};
  const invalid=(msg)=>{const el=d.querySelector('.area-error');if(el)el.textContent=msg;};
  const allocFor=e=>{
   if(e.mode==='unallocated')return !e.edited&&e.original.some(a=>a.area==='Shared / Unallocated')?e.original:[];
   if(e.quantity<=0)return [];
   if(e.mode==='common')return [{area:COMMON,quantity:e.quantity,common:true}];
   if(e.mode==='single')return [{area:e.target||names[0],quantity:e.quantity}];
   const base=names.filter(n=>qnum(e.values[n])>0).map(n=>({area:n,quantity:qnum(e.values[n])}));
   if(!e.edited&&e.original.some(a=>a.shared))base.forEach(a=>{if(e.original.some(old=>old.area===a.area&&old.shared))a.shared=true});
   return base;
  };
  const remainder=e=>e.mode==='unallocated'?0:e.quantity-allocFor(e).reduce((s,a)=>s+a.quantity,0);
  const valueParts=(e,qty)=>{
   const weight=e.quantity>0?qty/e.quantity:1;
   const l=e.line;
   return {material:Number(l.total_material||0)*weight,hours:Number(l.total_hours||0)*weight,
    labor:Number(l.total_labor||0)*weight,quoted:Number(l.quoted_total||0)*weight,
    optional:l.included_in_total===false};
  };
  const rowsByArea=()=>{
   const map=new Map([...names,COMMON,UNALLOCATED].map(name=>[name,{name,categories:new Map(),material:0,hours:0,labor:0,quoted:0,optional:0,quantity:0,units:new Map(),count:0}]));
   entries.forEach(e=>{
    const splits=allocFor(e),placements=splits.slice();
    const remaining=e.quantity-splits.reduce((sum,part)=>sum+Number(part.quantity||0),0);
    if(remaining>0.000001)placements.push({area:UNALLOCATED,quantity:remaining});
    if(!placements.length)placements.push({area:UNALLOCATED,quantity:e.quantity});
    placements.forEach(p=>{
     if(!p.quantity && e.quantity)return;
     const node=map.get(p.area)||map.get(UNALLOCATED);const cost=valueParts(e,p.quantity);
     const cat=e.line.category_key||e.line.category_snapshot||'Other';
     if(!node.categories.has(cat))node.categories.set(cat,{name:cat,items:[],quoted:0,optional:0,material:0,hours:0,labor:0});
     const group=node.categories.get(cat);const item={e,qty:p.quantity,...cost};group.items.push(item);
     for(const key of ['material','hours','labor']){if(!cost.optional){node[key]+=cost[key];group[key]+=cost[key]}}
     const costKey=cost.optional?'optional':'quoted';node[costKey]+=cost.quoted;group[costKey]+=cost.quoted;
     node.quantity+=p.quantity;node.units.set(e.line.uom,(node.units.get(e.line.uom)||0)+p.quantity);node.count++;
    });
   });
   return [...map.values()].filter(node=>node.count || names.includes(node.name));
  };
  const renderTree=()=>{
   const allGroups=rowsByArea();
   const groups=allGroups.filter(area=>!unallocatedOnly||area.name===UNALLOCATED);
   const filter=query.trim().toLowerCase();
   const total=allGroups.reduce((sum,area)=>sum+area.quoted,0);
   const optional=allGroups.reduce((sum,area)=>sum+area.optional,0);
   let body='';
   const totals=node=>`<span class="breakdown-summary-metrics"><span><small>Total Material</small><b>${money(node.material,currency)}</b></span><span><small>Total Hours</small><b>${fmt(node.hours)} hrs</b></span><span><small>Total Labour</small><b>${money(node.labor,currency)}</b></span><span><small>Quoted Total</small><b>${money(node.quoted,currency)}</b></span></span>`;
   for(const area of groups){
    const categories=[...area.categories.values()].map(g=>({...g,items:g.items.filter(x=>!filter||[area.name,g.name,x.e.line.name_snapshot].some(v=>String(v||'').toLowerCase().includes(filter)))})).filter(g=>g.items.length);
    if(filter&&!categories.length&&!area.name.toLowerCase().includes(filter))continue;
    const areaKey=nodeKey('area',area.name);
    body+=`<details class="breakdown-area" data-tree-node="${safe(areaKey)}" ${filter||openNodes.has(areaKey)?'open':''}><summary><span class="breakdown-tree-title"><span class="breakdown-folder">▤</span>${safe(area.name)} <small>${area.count} items · ${[...area.units.entries()].map(([unit,qty])=>fmt(qty)+' '+safe(unit)).slice(0,3).join(' · ')}</small></span>${totals(area)}</summary>`;
    for(const category of categories){
     const categoryKey=nodeKey('category',area.name,category.name);
     body+=`<details class="breakdown-category" data-tree-node="${safe(categoryKey)}" ${filter||openNodes.has(categoryKey)?'open':''}><summary><span>${safe(category.name)} <small>${category.items.length} item${category.items.length===1?'':'s'}</small></span>${totals(category)}</summary>`;
     for(const item of category.items){
      const l=item.e.line;
      const itemKey=nodeKey('item',area.name,category.name,l.id);
      body+=`<details class="breakdown-tree-item" data-tree-node="${safe(itemKey)}" ${filter||openNodes.has(itemKey)?'open':''}><summary><span>${safe(l.name_snapshot)} <small>${fmt(item.qty)} ${safe(l.uom)}</small></span><strong>${item.optional?'<span class="area-optional">Optional</span> ':''}${money(item.quoted,currency)}</strong></summary><div class="breakdown-item-metrics"><span>Material: ${money(item.material,currency)}</span><span>Hours: ${fmt(item.hours)}</span><span>Labour: ${money(item.labor,currency)}</span><span>Quoted: ${money(item.quoted,currency)}</span></div></details>`;
     }
     body+='</details>';
    }
    body+='</details>';
   }
   if(!body)body='<p class="helper-text">No matching areas, categories or items.</p>';
   return `<div class="breakdown-tree-toolbar"><label>Search breakdown<input type="search" data-tree-search placeholder="Find area, category or item" value="${safe(query)}"></label><button type="button" class="button secondary small" data-expand-all>Expand all</button><button type="button" class="button secondary small" data-collapse-all>Collapse all</button></div><div class="breakdown-tree">${body}</div><div class="breakdown-tree-totals"><b>Included quoted total: ${money(total,currency)} (all areas)</b><span>Optional costs excluded: ${money(optional,currency)}</span></div><p class="helper-text">Common items appear only once in totals. Filtering never changes costs; unallocated items remain separate.</p>`;
  };
  const areaControls=()=>names.map((name,i)=>`<div class="breakdown-name-row"><label>Area / floor / space ${i+1}<input data-name="${i}" maxlength="120" value="${safe(name)}" aria-label="Area ${i+1} name" required></label><div class="breakdown-area-actions"><button type="button" class="button secondary small" data-up="${i}" ${i===0?'disabled':''} title="Move area up" aria-label="Move ${safe(name)} up">↑</button><button type="button" class="button secondary small" data-down="${i}" ${i===names.length-1?'disabled':''} title="Move area down" aria-label="Move ${safe(name)} down">↓</button><button type="button" class="button secondary small" data-remove="${i}" title="Remove empty area" aria-label="Remove ${safe(name)}">×</button></div></div>`).join('');
  const editor=()=>{
   const groups=new Map();entries.forEach((e,i)=>{if(unallocatedOnly&&!unallocatedEntry(e))return;let cat=e.line.category_key||e.line.category_snapshot||'Other';if(!groups.has(cat))groups.set(cat,[]);groups.get(cat).push([e,i])});
   let trs='';
   for(const [cat,rows] of groups){
    trs+=`<tr class="breakdown-category-row"><th colspan="${5+names.length}">${safe(cat)} · ${rows.length} items</th></tr>`;
    for(const [e,i] of rows){
     const remain=remainder(e);
     trs+=`<tr><th scope="row"><strong>${safe(e.line.name_snapshot)}</strong><small>${safe(e.line.uom)} · ${safe(e.line.category_key)}</small></th><td><input data-total="${i}" type="number" min="0" max="1000000000" step="any" value="${e.quantity}" aria-label="Main quantity for ${safe(e.line.name_snapshot)}"></td><td><select data-mode="${i}" aria-label="Allocation mode for ${safe(e.line.name_snapshot)}">${[['unallocated','Unallocated'],['single','Single area'],['multiple','Multiple areas'],['common','Common to all areas']].map(([value,label])=>`<option value="${value}" ${e.mode===value?'selected':''}>${label}</option>`).join('')}</select>${e.mode==='single'?`<select data-target="${i}" aria-label="Select area for ${safe(e.line.name_snapshot)}">${names.map(n=>`<option value="${safe(n)}" ${n===e.target?'selected':''}>${safe(n)}</option>`).join('')}</select>`:''}${e.mode==='multiple'?`<button type="button" class="text-button" data-equal="${i}">Distribute equally</button>`:''}</td>${names.map((n,j)=>`<td><input type="number" min="0" step="any" data-item="${i}" data-area="${j}" value="${e.mode==='single'?(e.target===n?e.quantity:0):e.mode==='multiple'?qnum(e.values[n]):0}" ${e.mode==='multiple'?'':'disabled'} aria-label="${safe(e.line.name_snapshot+' / '+n)}"></td>`).join('')}<td><span data-remaining="${i}" class="${Math.abs(remain)>1e-6?'area-unreconciled':'area-reconciled'}">${e.mode==='unallocated'?'Unallocated':fmt(remain)}</span></td></tr>`;
    }
   }
   if(!trs)trs='<tr><td colspan="5">No unallocated items. All quantities are assigned.</td></tr>';
   return `<p class="helper-text">Assign each quantity to one area, several areas, or a single common allowance for all areas. Unallocated items are shown separately, without changing the project total.</p><div class="breakdown-names">${areaControls()}<button type="button" class="button secondary" data-add-breakdown>+ Add area / floor / space</button></div><div class="breakdown-scroll" role="region" aria-label="Allocation matrix" tabindex="0"><table><thead><tr><th>Estimate item</th><th>Main quantity</th><th>Allocation type</th>${names.map(n=>`<th>${safe(n)}</th>`).join('')}<th>Remaining</th></tr></thead><tbody>${trs}</tbody></table></div><p class="helper-text">All manually assigned quantities must reconcile to the main quantity before saving. Use Unallocated for items not yet assigned.</p>`;
  };
  function render(){
   d.innerHTML=`<form class="dialog-card" novalidate><div class="breakdown-heading"><div><h2>Breakdown — ${safe(project.project.name)}</h2><p class="helper-text">Area / Floor / Space → Category → Catalog Item</p></div><button type="button" class="button secondary" data-cancel aria-label="Close breakdown">×</button></div><div class="breakdown-tabs" role="tablist" aria-label="Breakdown view"><button type="button" role="tab" aria-selected="${tab==='allocate'}" class="${tab==='allocate'?'active':''}" data-tab="allocate">Allocation</button><button type="button" role="tab" aria-selected="${tab==='tree'}" class="${tab==='tree'?'active':''}" data-tab="tree">Structured View</button></div><div class="breakdown-utility-row"><label class="breakdown-unallocated-filter"><input type="checkbox" data-only-unallocated ${unallocatedOnly?'checked':''}> Show unallocated only <span class="breakdown-unallocated-count">${unallocatedCount()}</span></label><span class="breakdown-utility-actions"><button type="button" class="button secondary small" data-undo ${undoStack.length?'':'disabled'} title="Undo unsaved allocation change">Undo</button><button type="button" class="button secondary small" data-redo ${redoStack.length?'':'disabled'} title="Redo unsaved allocation change">Redo</button></span></div><section class="breakdown-pane" role="tabpanel">${tab==='allocate'?editor():renderTree()}</section><p role="alert" class="area-error"></p><div class="area-actions"><span class="breakdown-save-note">${entries.length} estimate items · ${names.length} areas</span><button type="button" class="button secondary" data-cancel>Cancel</button><button type="submit" class="button primary" ${busy?'disabled':''}>${busy?'Saving…':'Save breakdown'}</button></div></form>`;
   d.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=requestClose);
   d.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;render()});
   d.querySelector('[data-only-unallocated]').onchange=e=>{unallocatedOnly=e.target.checked;render()};
   d.querySelector('[data-undo]').onclick=()=>historyAction('undo');
   d.querySelector('[data-redo]').onclick=()=>historyAction('redo');
   if(tab==='allocate')bindEditor();else bindTree();
   d.querySelector('form').onsubmit=save;
  }
  function bindEditor(){
   d.querySelector('[data-add-breakdown]').onclick=()=>{if(names.length>=200){invalid('Use no more than 200 areas');return}pushHistory();names.push(`Area ${names.length+1}`);render()};
   d.querySelectorAll('[data-name]').forEach(el=>el.onchange=()=>{
    const i=Number(el.dataset.name),old=names[i],name=el.value.trim().replace(/\s+/g,' ');
    if(!name||name.length>120||[COMMON,UNALLOCATED,'Shared / Unallocated'].some(s=>s.toLowerCase()===name.toLowerCase())||names.some((n,j)=>i!==j&&n.toLowerCase()===name.toLowerCase())){invalid('Use a unique area name of 1–120 characters');el.value=old;return}
    if(name===old)return;pushHistory();names[i]=name;entries.forEach(e=>{if(Object.prototype.hasOwnProperty.call(e.values,old)){e.values[name]=e.values[old];delete e.values[old];e.edited=true}if(e.target===old)e.target=name});render();
   });
   d.querySelectorAll('[data-up],[data-down]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.up??b.dataset.down),j=i+(b.hasAttribute('data-up')?-1:1);pushHistory();[names[i],names[j]]=[names[j],names[i]];render()});
   d.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.remove),name=names[i];if(entries.some(e=>qnum(e.values[name])>0&&e.mode==='multiple'||e.mode==='single'&&e.target===name&&e.quantity>0)){invalid('Reassign quantities from '+name+' before deleting that area.');return}if(names.length===1){invalid('Keep at least one area.');return}pushHistory();names.splice(i,1);entries.forEach(e=>{delete e.values[name];if(e.target===name)e.target=names[0]});render()});
   d.querySelectorAll('[data-mode]').forEach(el=>el.onchange=()=>{const e=entries[Number(el.dataset.mode)];if(e.mode!==el.value)pushHistory();e.mode=el.value;e.edited=true;if(e.mode==='single'&&!names.includes(e.target))e.target=names[0];render()});
   d.querySelectorAll('[data-target]').forEach(el=>el.onchange=()=>{if(entries[Number(el.dataset.target)].target!==el.value)pushHistory();entries[Number(el.dataset.target)].target=el.value;entries[Number(el.dataset.target)].edited=true;render()});
   d.querySelectorAll('[data-total]').forEach(el=>el.onchange=()=>{const q=Number(el.value),e=entries[Number(el.dataset.total)];if(!Number.isFinite(q)||q<0||q>1e9){invalid('Quantity must be a finite non-negative number.');el.value=e.quantity;return}if(e.quantity!==q)pushHistory();e.quantity=q;e.edited=true;render()});
   d.querySelectorAll('[data-item]').forEach(el=>{
    el.onfocus=()=>{el.dataset.before=snapshot()};
    el.oninput=()=>{const e=entries[Number(el.dataset.item)];e.values[names[Number(el.dataset.area)]]=Number(el.value);e.edited=true;const label=d.querySelector(`[data-remaining="${el.dataset.item}"]`);const remaining=remainder(e);label.textContent=fmt(remaining);label.className=Math.abs(remaining)>1e-6?'area-unreconciled':'area-reconciled'};
    el.onchange=()=>{if(el.dataset.before&&el.dataset.before!==snapshot())pushHistory(el.dataset.before);render()};
   });
   d.querySelectorAll('[data-equal]').forEach(b=>b.onclick=()=>{const e=entries[Number(b.dataset.equal)];pushHistory();let remaining=e.quantity;names.forEach((n,i)=>{const q=i===names.length-1?remaining:e.quantity/names.length;e.values[n]=q;remaining-=q});e.edited=true;render()});
  }
  function bindTree(){
   const search=d.querySelector('[data-tree-search]');search.oninput=()=>{query=search.value;const caret=search.selectionStart;render();const next=d.querySelector('[data-tree-search]');next.focus();next.setSelectionRange(caret,caret)};
   d.querySelectorAll('[data-tree-node]').forEach(node=>node.addEventListener('toggle',()=>{
    if(query||node.dataset.treeNode===undefined)return;
    if(node.open)openNodes.add(node.dataset.treeNode);else openNodes.delete(node.dataset.treeNode);
    saveExpanded();
   }));
   d.querySelector('[data-expand-all]').onclick=()=>{openNodes=new Set([...d.querySelectorAll('[data-tree-node]')].map(node=>node.dataset.treeNode));saveExpanded();render()};
   d.querySelector('[data-collapse-all]').onclick=()=>{openNodes.clear();saveExpanded();render()};
  }
  async function save(event){
   event.preventDefault();if(busy)return;
   const error=d.querySelector('.area-error');error.textContent='';
   for(const e of entries){const assigned=allocFor(e),diff=remainder(e);
    if(e.mode!=='unallocated'&&Math.abs(diff)>1e-6){error.textContent=`Allocate ${fmt(e.quantity)} ${e.line.uom} for ${e.line.name_snapshot} (remaining ${fmt(diff)}).`;return}
    if(assigned.some(a=>!Number.isFinite(a.quantity)||a.quantity<0)){error.textContent='Allocation quantities must be non-negative numbers.';return}
   }
   busy=true;d.querySelectorAll('button,input,select').forEach(x=>x.disabled=true);
   try{
    const response=await api(`/api/projects/${pid}/breakdown`,{method:'POST',body:{expected_revision:project.project.revision,areas:names,
     rows:entries.map(e=>({id:e.line.id,expected_revision:e.line.revision,quantity:e.quantity,allocations:allocFor(e)}))}});
    if(state.projectId===pid){state.projectData=response;renderProject()}
    savedSuccessfully=true;d.close();if(typeof toast==='function')toast('Breakdown saved');
   }catch(ex){busy=false;d.querySelectorAll('button,input,select').forEach(x=>x.disabled=false);d.querySelector('.area-error').textContent=ex.message+' No changes were saved.'}
  }
  d.addEventListener('keydown',event=>{
   if(!(event.ctrlKey||event.metaKey)||event.altKey)return;
   if(event.target.closest('input,textarea,select,[contenteditable]'))return;
   if(event.key.toLowerCase()==='z'){event.preventDefault();historyAction(event.shiftKey?'redo':'undo');}
   if(event.key.toLowerCase()==='y'){event.preventDefault();historyAction('redo');}
  });
  render();d.onclose=()=>{window.removeEventListener('beforeunload',beforeLeave);d.remove();};d.showModal();
 });
})();
