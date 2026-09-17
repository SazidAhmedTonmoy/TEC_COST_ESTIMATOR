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
