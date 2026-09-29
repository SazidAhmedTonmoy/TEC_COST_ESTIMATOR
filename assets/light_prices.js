/* Quoted lighting packages: inline details, explicit arithmetic, editable working copies. */
const lightPriceState={request:0,detailRequest:0,offset:0,total:0,selected:null,item:null,results:[],suppliers:[],editing:false,dirty:false,busy:false,photoDataUrl:null,removePhoto:false,photoLoading:false,photoReadId:0};
function renderSupplierPicker(options){
  const active=document.activeElement,preserve=$('#light-price-supplier').contains(active)&&active.matches('input'),all=active?.dataset?.allSuppliers!==undefined,activeValue=active?.value;
  lightPriceState.supplierOptions=options;
  const selected=lightPriceState.suppliers;
  $('#light-price-supplier summary').textContent=selected.length===0?'All suppliers':selected.length===1?selected[0]:`${selected.length} suppliers`;
  $('#light-price-supplier .supplier-options').innerHTML=`<label><input type="checkbox" data-all-suppliers ${selected.length?'':'checked'}>All suppliers</label>`+options.map(s=>`<label><input type="checkbox" data-supplier value="${escapeHtml(s)}" ${selected.includes(s)?'checked':''}>${escapeHtml(s)}</label>`).join('');
  if(preserve){const control=$$('#light-price-supplier input').find(el=>all?el.dataset.allSuppliers!==undefined:el.value===activeValue);control?.focus();}
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
  $('#light-price-results').innerHTML='';$('#light-price-search').value='';renderSupplierPicker([]);
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
  $('#light-price-supplier').addEventListener('change',event=>{clearTimeout(timer);if(event.target.dataset.allSuppliers!==undefined){lightPriceState.suppliers=[];}else{lightPriceState.suppliers=$$('#light-price-supplier input[data-supplier]:checked').map(el=>el.value);}renderSupplierPicker(lightPriceState.supplierOptions||[]);runSearch();});
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
