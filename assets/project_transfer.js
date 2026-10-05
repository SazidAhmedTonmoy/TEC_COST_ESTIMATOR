/* Portable projects and an in-tab component clipboard. */
let projectJSONDraft=null,componentClipboard=null,projectJSONBusy=false;
function sydneyMonth(now=new Date()){
 const parts=new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit'}).formatToParts(now);
 return parts.find(p=>p.type==='year').value+'-'+parts.find(p=>p.type==='month').value;
}
function downloadProjectJSON(data,name){
 const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'}));
 const a=document.createElement('a');a.href=url;a.download=name.replace(/[^a-zA-Z0-9_.-]/g,'_')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function syncComponentPaste(){
 const available=Boolean(state.user&&componentClipboard?.userId===state.user.id);
 $('#paste-component-button').disabled=!available;
 $('#paste-component-button').title=available?'Paste '+componentClipboard.component.description:'Copy a component row first';
 $('#component-clipboard-bar').classList.toggle('hidden',!available);
 $('#component-clipboard-label').textContent=available?'Copied: '+componentClipboard.component.description:'';
}

async function openProjectJSON(){
 const select=$('#project-json-select');select.innerHTML=state.projects.map(p=>`<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
 if(state.projects.some(p=>p.id===state.projectId))select.value=String(state.projectId);
 $('#project-json-export').disabled=!state.projects.length;
 $('#project-json-status').textContent='';$('#project-json-dialog').showModal();
}
async function projectJSONAction(action){
 if(projectJSONBusy)return;projectJSONBusy=true;const dialog=$('#project-json-dialog');dialog.setAttribute('aria-busy','true');
 const controls=[...dialog.querySelectorAll('button,input,select')];const disabled=controls.map(e=>e.disabled);controls.forEach(e=>e.disabled=true);
 try{await action();}catch(e){$('#project-json-status').textContent=e.message;toast(e.message,true);}
 finally{projectJSONBusy=false;dialog.removeAttribute('aria-busy');controls.forEach((e,i)=>e.disabled=disabled[i]);$('#project-json-import').disabled=!projectJSONDraft;}
}
document.addEventListener('DOMContentLoaded',()=>{
 $('#project-json-open').addEventListener('click',openProjectJSON);
 $('#project-json-dialog').addEventListener('cancel',e=>{if(projectJSONBusy)e.preventDefault();});
 $('#project-json-export').addEventListener('click',()=>projectJSONAction(async()=>{
  const data=await api('/api/projects/'+Number($('#project-json-select').value)+'/json');downloadProjectJSON(data,data.project.name);$('#project-json-status').textContent='Project JSON downloaded.';
 }));
 $('#project-json-example').addEventListener('click',()=>projectJSONAction(async()=>{const response=await fetch('/assets/example_project.json');if(!response.ok)throw new Error('Could not load example');downloadProjectJSON(await response.json(),'TEC_ConEst_example_project');}));
 $('#project-json-file').addEventListener('change',async e=>{
  projectJSONDraft=null;$('#project-json-import').disabled=true;$('#project-json-preview').textContent='';$('#project-json-status').textContent='';const file=e.target.files[0];if(!file)return;
  try{
   if(file.size>10*1024*1024)throw new Error('Choose a JSON file smaller than 10 MB.');
   const data=JSON.parse(await file.text());if(data?.format!=='tec-conest-project'||data.version!==1||!data.project?.name||!Array.isArray(data.lines))throw new Error('Choose a TEC ConEst project JSON file. Download the example for its format.');
   if(e.target.files[0]!==file)return;
   projectJSONDraft=data;$('#project-json-preview').textContent=`${data.project.name} · ${data.lines.length} estimate items. A new project will be created.`;$('#project-json-import').disabled=false;
  }catch(error){$('#project-json-status').textContent=error.message;}
 });
 $('#project-json-import').addEventListener('click',()=>projectJSONAction(async()=>{
  if(!projectJSONDraft)return;const result=await api('/api/project-json/import',{method:'POST',body:projectJSONDraft});projectJSONDraft=null;$('#project-json-file').value='';$('#project-json-preview').textContent='';await loadDashboard();$('#project-json-dialog').close();location.hash='#/estimate/'+result.id;toast('Project imported');
 }));
 $('#manual-components').addEventListener('click',e=>{
  const button=e.target.closest('.clipboard-component');if(!button)return;
  try {
   const row=button.closest('.manual-component');
   componentClipboard=null;
   const component=readManualComponents(row)[0];
   if(!component)throw new Error('Choose a component row to copy.');
   componentClipboard={userId:state.user.id,component:structuredClone(component)};
   $$('#manual-components .clipboard-component').forEach(b=>b.classList.remove('is-copied'));
   button.classList.add('is-copied');syncComponentPaste();toast('Copied: '+component.description);
  }catch(error){componentClipboard=null;syncComponentPaste();toast(error.message,true);}

 });
 $('#clear-component-clipboard').addEventListener('click',()=>{componentClipboard=null;syncComponentPaste();$$('#manual-components .clipboard-component').forEach(b=>b.classList.remove('is-copied'));});
 $('#paste-component-button').addEventListener('click',()=>{
  if(componentClipboard?.userId!==state.user?.id)return;
  const c=structuredClone(componentClipboard.component);delete c.id;delete c.project_line_id;delete c.catalog_item_id;c.is_parent=0;c.is_supply_copy=0;
  $('#manual-components').insertAdjacentHTML('beforeend',componentRow(c));refreshManualPricing();toast('Component pasted. Save the item to keep it.');
 });
 new MutationObserver(syncComponentPaste).observe($('#manual-dialog'),{attributes:true,attributeFilter:['open']});
});
