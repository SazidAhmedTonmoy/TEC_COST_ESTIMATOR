/* Live database answers, source links and validated follow-up record IDs. */
const helpChat={owner:null,busy:false,generation:0,followUp:null,anchor:null};
function resetHelpChat(){helpChat.generation++;helpChat.busy=false;helpChat.owner=null;helpChat.followUp=null;helpChat.anchor=null;$('#help-chat-messages').textContent='';$('#help-chat-question').value='';$('#send-help-chat').disabled=false;$('#send-help-chat').textContent='Ask';$('#help-chat-scope').value='auto';}
function helpPageContext(){
  const projectId=state.view==='estimate'?state.projectId:null;
  const catalogId=state.view==='catalog'?state.currentCatalogItem?.id:null;
  const lightId=state.view==='light-prices'&&typeof lightPriceState!=='undefined'?lightPriceState.selected:null;
  return {page:state.view,project_id:projectId||null,catalog_item_id:catalogId||null,light_group_id:lightId?Number(lightId):null};
}
function refreshHelpContext(){
  const current=helpPageContext(),anchor=JSON.stringify(current);
  if(helpChat.anchor!==anchor){helpChat.followUp=null;helpChat.anchor=anchor;}
  const name=current.project_id?state.projectData?.project.name:current.catalog_item_id?state.currentCatalogItem?.name:current.light_group_id?lightPriceState.item?.description:null;
  $('#help-chat-context').textContent=name?`Current record: ${name}. Ask about this record, or name another one.`:'Search all company projects and saved catalogue/lighting records by name, number or nickname.';
  return current;
}
function chatMessage(text,kind,sources=[]){
  const box=document.createElement('div');box.className=`help-message ${kind}`;
  const body=document.createElement('p');body.textContent=text;box.append(body);
  if(sources.length){const links=document.createElement('div');links.className='help-sources';for(const source of sources){if(!/^#\/(catalog|estimate|light-prices)\/\d+$/.test(source.url))continue;const link=document.createElement('a');link.href=source.url;link.textContent=source.label;link.addEventListener('click',e=>{if(!e.ctrlKey&&!e.metaKey&&!e.shiftKey)$('#help-chat-dialog').close();});links.append(link);}box.append(links);}
  $('#help-chat-messages').append(box);box.scrollIntoView({block:'nearest'});return box;
}
async function askHelp(){
  const question=$('#help-chat-question').value.trim();if(!question||helpChat.busy||!state.user)return;
  const current=refreshHelpContext(),owner=state.user.id,generation=helpChat.generation;
  const followUp=helpChat.followUp;helpChat.busy=true;
  chatMessage(question,'question');$('#help-chat-question').value='';
  const pending=chatMessage('Reading saved project, catalogue and lighting-price records...','answer');$('#send-help-chat').disabled=true;$('#send-help-chat').textContent='Working...';
  try{
    const data=await api('/api/assistant/help',{method:'POST',body:{question,...current,scope:$('#help-chat-scope').value,follow_up:followUp}});
    if(generation!==helpChat.generation||state.user?.id!==owner)return;
    helpChat.followUp=data.follow_up||null;
    pending.remove();chatMessage(`${data.answer}\n\n${data.mode}`,'answer',data.sources||[]);
  }catch(error){if(generation===helpChat.generation&&state.user?.id===owner)pending.firstChild.textContent=error.message;}
  finally{if(generation===helpChat.generation){helpChat.busy=false;$('#send-help-chat').disabled=false;$('#send-help-chat').textContent='Ask';$('#help-chat-question').focus();}}
}
document.addEventListener('DOMContentLoaded',()=>{
  const refresh=()=>{$('#help-chat-button').classList.toggle('hidden',!state.user||Boolean(state.user.must_change_password));if(!state.user)resetHelpChat();};
  new MutationObserver(refresh).observe($('#authenticated-app'),{attributes:true,attributeFilter:['class']});refresh();
  $('#help-chat-button').addEventListener('click',()=>{if(helpChat.owner!==state.user?.id){resetHelpChat();helpChat.owner=state.user?.id;}refreshHelpContext();$('#help-chat-dialog').showModal();$('#help-chat-question').focus();});
  $('#close-help-chat').addEventListener('click',()=>$('#help-chat-dialog').close());
  $('#help-chat-form').addEventListener('submit',event=>{event.preventDefault();askHelp();});
  $('#help-chat-scope').addEventListener('change',()=>{helpChat.followUp=null;});
  $$('.help-chat-starters button').forEach(button=>button.addEventListener('click',()=>{$('#help-chat-scope').value='auto';$('#help-chat-question').value=button.dataset.helpQuestion;$('#help-chat-question').focus();}));
});
