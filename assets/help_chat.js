/* TEC EstiDoc v3.7.27: searchable in-product guide + context-aware assistant.
 * Only explicit, server-authorized actions can change records, after confirmation.
 */
(function(){
 'use strict';
 let user=null, csrf='', busy=false, generation=0, activePanel='assistant', articles=[], guideSections=[], selectedArticle='', guideQuery='';
 const el=id=>document.getElementById(id);
 async function request(path,body){
  const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-ConEst-Request':'1','X-CSRF-Token':csrf},...(body===undefined?{}:{body:JSON.stringify(body)})});
  let data;try{data=await response.json()}catch(_){throw Error('Connection interrupted. Please check your connection and retry.');}
  if(!response.ok)throw Error(data.error||'Request failed. Verify the saved record before retrying.');return data;
 }
 function message(text,kind,sources=[]){
  const article=document.createElement('article');article.className='help-message '+kind;
  const p=document.createElement('p');p.textContent=text;article.append(p);
  for(const source of sources){if(!source||!(/^#\/(catalog|estimate|light-prices)\/\d+$/.test(source.url)||source.url==='/tenders/chase-up'))continue;
   const a=document.createElement('a');a.href=source.url.startsWith('#')?'/'+source.url:source.url;a.textContent=source.label||'Open source';a.className='help-source-link';article.append(a);}
  el('help-chat-messages').append(article);el('help-chat-messages').scrollTop=el('help-chat-messages').scrollHeight;return article;
 }
 function renderMemory(data){
  if(data.models){const select=el('help-model'),previous=select.value;select.replaceChildren(new Option('App default',''));for(const model of data.models)select.add(new Option(model,model));if([...select.options].some(opt=>opt.value===previous))select.value=previous;}
  el('help-chat-messages').textContent='';for(const m of data.messages||[])message(m.text,m.role,m.sources||[]);
  el('help-memory-note').value=data.note||'';el('help-use-ai').checked=data.useAI===true;
  el('help-documents').textContent='';for(const doc of data.documents||[]){
   const row=document.createElement('div');row.className='help-attachment-row';const title=document.createElement('span');title.textContent=doc.name+' · '+doc.characters.toLocaleString()+' characters';const remove=document.createElement('button');remove.type='button';remove.className='button secondary small';remove.textContent='Remove';remove.onclick=async()=>{try{renderMemory(await request('/api/assistant/memory',{removeDocument:doc.id}));}catch(err){message(err.message,'answer');}};row.append(title,remove);el('help-documents').append(row);
  }
 }
 function pageContext(){
  if(location.pathname.startsWith('/tenders'))return {page:'tenders'};
  if(typeof state!=='undefined')return {page:state.view,project_id:state.view==='estimate'?Number(state.projectId)||null:null,catalog_item_id:state.view==='catalog'?state.currentCatalogItem?.id:null,light_group_id:state.view==='light-prices'&&typeof lightPriceState!=='undefined'?lightPriceState.selected:null};
  return {page:'estimator'};
 }
 function setPanel(panel){
  activePanel=panel;
  const guide=panel==='guide';el('help-guide').hidden=!guide;el('help-chat-messages').hidden=guide;el('help-chat-form').hidden=guide;
  el('help-tab-guide').classList.toggle('selected',guide);el('help-tab-assistant').classList.toggle('selected',!guide);
  el('help-tab-guide').setAttribute('aria-selected',String(guide));el('help-tab-assistant').setAttribute('aria-selected',String(!guide));
  if(guide){renderGuide();el('help-guide-search').focus();}else el('help-chat-question').focus();
 }
 function renderGuide(){
  const host=el('help-guide-topics'),details=el('help-guide-content'),q=guideQuery.trim().toLocaleLowerCase();
  host.replaceChildren();details.replaceChildren();
  const matches=articles.filter(item=>!q||[item.title,item.category,...item.steps,item.note].join(' ').toLocaleLowerCase().includes(q));
  if(!matches.length){details.textContent='No matching guide topics. Try another feature name or ask the AI Assistant.';return;}
  if(!matches.some(item=>item.id===selectedArticle))selectedArticle=matches[0].id;
  let previousGroup='';for(const item of matches){
   if(previousGroup!==item.category){const heading=document.createElement('div');heading.className='help-topic-group';heading.textContent=item.category;host.append(heading);previousGroup=item.category;}
   const button=document.createElement('button');button.type='button';button.className='help-topic'+(selectedArticle===item.id?' selected':'');button.textContent=item.title;button.onclick=()=>{selectedArticle=item.id;renderGuide();};host.append(button);
  }
  const item=matches.find(a=>a.id===selectedArticle);
  const h=document.createElement('h3');h.textContent=item.title;details.append(h);
  const group=document.createElement('p');group.className='help-topic-category';group.textContent=item.category;details.append(group);
  const ol=document.createElement('ol');for(const text of item.steps){const li=document.createElement('li');li.textContent=text;ol.append(li);}details.append(ol);
  if(item.note){const tip=document.createElement('p');tip.className='help-guide-tip';tip.textContent=item.note;details.append(tip);}
  const ask=document.createElement('button');ask.type='button';ask.className='button primary';ask.textContent='Ask AI about this topic';ask.onclick=()=>{el('help-chat-question').value='Explain how to '+item.title.toLocaleLowerCase()+' in TEC EstiDoc.';setPanel('assistant');};details.append(ask);
 }
 function renderGuideData(data){guideSections=data.sections||[];articles=[];for(const group of guideSections)for(const item of group.articles||[])articles.push({...item,category:group.title});renderGuide();}
 async function open(){
  try{
   const session=await request('/api/auth/session');if(!session.user||session.user.must_change_password)throw Error('Complete sign-in before using Help.');
   user=session.user;csrf=session.csrf_token;generation++;el('help-chat-dialog').showModal();
   const [memory,guide]=await Promise.all([request('/api/assistant/memory'),request('/api/assistant/guide')]);
   renderMemory(memory);renderGuideData(guide);setPanel(activePanel);
  }catch(err){if(el('help-chat-dialog').open)message(err.message,'answer');else alert(err.message);}
 }
 function resetHelpChat(){generation++;user=null;csrf='';if(el('help-chat-dialog')){el('help-chat-dialog').close();el('help-chat-messages').textContent='';el('help-memory-note').value='';el('help-documents').textContent='';}}
 window.resetHelpChat=resetHelpChat;
 function previewAction(data){
  const entry=el('help-chat-messages'),card=document.createElement('section');card.className='help-action-preview';card.setAttribute('role','group');card.setAttribute('aria-label','Confirm proposed action');
  const title=document.createElement('strong');title.textContent='Review before applying';const p=document.createElement('p');p.textContent=data.description;
  const controls=document.createElement('div');controls.className='help-action-controls';
  const confirm=document.createElement('button');confirm.className='button primary';confirm.type='button';confirm.textContent='Confirm action';
  const cancel=document.createElement('button');cancel.className='button secondary';cancel.type='button';cancel.textContent='Cancel';
  async function act(command){confirm.disabled=true;cancel.disabled=true;
   try{const result=await request('/api/assistant/action',{command,token:data.token});card.remove();message(result.answer,'answer',result.sources||[]);}
   catch(err){message(err.message,'answer');confirm.disabled=false;cancel.disabled=false;}
  }
  confirm.onclick=()=>act('confirm');cancel.onclick=()=>act('cancel');controls.append(confirm,cancel);card.append(title,p,controls);entry.append(card);entry.scrollTop=entry.scrollHeight;
 }
 function init(){
  el('help-chat-dialog')?.remove();el('help-chat-button')?.remove();
  const host=document.createElement('div');host.innerHTML=`<button id="help-chat-button" class="help-chat-launch" type="button">? <span>Help</span></button>
<dialog id="help-chat-dialog" class="help-chat-dialog" aria-labelledby="help-chat-title">
<header class="help-chat-heading"><div><h2 id="help-chat-title">TEC EstiDoc Help</h2><p>User Guide · AI Assistant · Documents</p></div><nav class="help-header-actions" aria-label="Help options"><button id="help-settings-button" type="button" class="button secondary small" aria-expanded="false" aria-controls="help-settings">Settings</button><button id="close-help-chat" class="button secondary small" type="button">Close</button></nav></header>
<div class="help-tabs" role="tablist" aria-label="Help view"><button id="help-tab-assistant" role="tab" aria-controls="help-chat-messages" class="help-tab selected" type="button">AI Assistant</button><button id="help-tab-guide" role="tab" aria-controls="help-guide" class="help-tab" type="button">User Guide</button></div>
<section id="help-settings" class="help-memory" hidden><h3>Assistant settings</h3><label class="help-ai-choice"><input type="checkbox" id="help-use-ai">Use configured Gemini for AI-assisted answers. This sends your question and relevant records, memory and document excerpts to the configured provider.</label><label>My assistant context<textarea id="help-memory-note" maxlength="2000" rows="2" placeholder="Optional work context or preferred response style"></textarea></label><button id="help-save-memory" type="button" class="button secondary small">Save context</button><h4>Attachments</h4><div id="help-documents"></div><small>Up to three files, 10 MB each: text PDF, XLSX, DOCX, TXT, CSV, JSON, MD. Scanned PDF images need OCR.</small><div class="help-settings-actions"><button id="help-clear-memory" type="button" class="button secondary small">Clear conversation</button><button id="help-reset-memory" type="button" class="button secondary small">Reset chat, context and attachments</button></div></section>
<section id="help-guide" class="help-guide" hidden aria-label="User Guide"><label class="help-guide-search"><span>Search the user guide</span><input type="search" id="help-guide-search" placeholder="Search a function, e.g. Breakdown, quote, import…" autocomplete="off" /></label><div class="help-guide-layout"><nav id="help-guide-topics" class="help-guide-topics" aria-label="User Guide topics"></nav><article id="help-guide-content" class="help-guide-content"></article></div></section>
<main id="help-chat-messages" class="help-chat-messages" role="log" aria-live="polite"></main>
<form id="help-chat-form"><div class="help-chat-compose"><button id="help-attach-button" class="button secondary small" type="button" aria-label="Attach a file" title="Attach a file">+</button><input id="help-file" type="file" accept=".pdf,.xlsx,.docx,.txt,.csv,.json,.md" hidden><textarea id="help-chat-question" aria-label="Your question" rows="2" maxlength="1000" required placeholder="Ask about your estimates, tenders or attached files…"></textarea><button id="send-help-chat" class="button primary" type="submit" aria-label="Send message">↑</button></div><div class="help-compose-options"><div class="help-compose-selectors"><label>Mode <select id="help-chat-mode"><option value="project">Workspace</option><option value="normal">General</option></select></label><label>Model <select id="help-model"><option value="">App default</option></select></label></div><span id="help-mode-description">Uses authorized project and tender records</span></div><p class="help-composer-note">Enter to send · Shift+Enter for a new line · Project changes require confirmation</p><div class="help-starter-questions"><button type="button" data-prompt="Summarise the current estimate">Summarise this estimate</button><button type="button" data-prompt="How do I allocate items in Breakdown?">How to use Breakdown</button><button type="button" data-prompt="What actions can you perform for me?">What can you do?</button></div></form>
</dialog>`;document.body.append(host);
  el('help-chat-button').onclick=open;el('close-help-chat').onclick=()=>el('help-chat-dialog').close();
  el('help-tab-assistant').onclick=()=>setPanel('assistant');el('help-tab-guide').onclick=()=>setPanel('guide');
  el('help-guide-search').oninput=e=>{guideQuery=e.target.value;renderGuide();};
  const app=el('authenticated-app');if(app){const sync=()=>{const active=typeof state!=='undefined'&&state.user&&!state.user.must_change_password;el('help-chat-button').classList.toggle('hidden',!active);if(!active)resetHelpChat();};new MutationObserver(sync).observe(app,{attributes:true,attributeFilter:['class']});sync();}
  el('help-save-memory').onclick=async()=>{try{await request('/api/assistant/memory',{note:el('help-memory-note').value});message('Assistant context saved.','answer');}catch(err){message(err.message,'answer');}};
  el('help-use-ai').onchange=async()=>{const wanted=el('help-use-ai').checked;try{await request('/api/assistant/memory',{useAI:wanted});}catch(err){el('help-use-ai').checked=!wanted;message(err.message,'answer');}};
  el('help-clear-memory').onclick=async()=>{try{generation++;renderMemory(await request('/api/assistant/memory',{clearConversation:true}));}catch(err){message(err.message,'answer');}};
  el('help-reset-memory').onclick=async()=>{if(!confirm('Clear all assistant messages, saved context and attachments?'))return;try{generation++;renderMemory(await request('/api/assistant/memory',{clear:true}));}catch(err){message(err.message,'answer');}};
  el('help-settings-button').onclick=()=>{const panel=el('help-settings');panel.hidden=!panel.hidden;el('help-settings-button').setAttribute('aria-expanded',String(!panel.hidden));};
  el('help-chat-mode').onchange=()=>{el('help-mode-description').textContent=el('help-chat-mode').value==='project'?'Uses authorized project and tender records':'General knowledge and attached files; no workspace lookup';};
  el('help-attach-button').onclick=()=>el('help-file').click();
  el('help-chat-question').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();el('help-chat-form').requestSubmit();}});
  for(const button of el('help-chat-form').querySelectorAll('[data-prompt]'))button.onclick=()=>{el('help-chat-question').value=button.dataset.prompt;el('help-chat-question').focus();};
  el('help-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;e.target.disabled=true;try{
   if(file.size>10*1024*1024)throw Error('Choose a file up to 10 MB.');
   const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Cannot read file'));reader.readAsDataURL(file);});
   renderMemory(await request('/api/assistant/document',{name:file.name,content}));message('Attached '+file.name+'. Ask a question about it.','answer');
  }catch(error){message(error.message,'answer');}finally{e.target.disabled=false;e.target.value='';}};
  el('help-chat-form').onsubmit=async e=>{e.preventDefault();if(busy)return;const question=el('help-chat-question').value.trim();if(!question)return;
   busy=true;const token=generation;el('send-help-chat').disabled=true;message(question,'question');el('help-chat-question').value='';const pending=message('Checking available records and guide…','answer');
   try{const data=await request('/api/assistant/chat',{question,chatMode:el('help-chat-mode').value,model:el('help-model').value,scope:'auto',useAI:el('help-use-ai').checked,...pageContext()});
    if(token!==generation)return;pending.remove();message(data.answer+(data.mode?'\n\n'+data.mode:''),'answer',data.sources||[]);if(data.actionPreview)previewAction(data.actionPreview);
   }catch(error){if(token===generation)pending.textContent=error.message;}finally{busy=false;el('send-help-chat').disabled=false;}
  };
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
