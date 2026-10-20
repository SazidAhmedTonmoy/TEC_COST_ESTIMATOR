function bindProjectSharing(){
 let project=null,busy=false;
 const dialog=$('#project-share-dialog'),url=$('#project-share-url'),status=$('#project-share-status');
 $('#share-project-button').addEventListener('click',()=>{if(!state.projectData?.project.can_manage)return;project=state.projectId;url.value='';status.textContent='';$('#copy-project-share').disabled=true;dialog.showModal();});
 for(const [selector,action]of [['#create-project-share','create'],['#revoke-project-share','revoke']])$(selector).addEventListener('click',async()=>{
  if(busy)return;
  if(!confirm(action==='create'?'Create a public read-only link with all prices and component details? Any previous link will stop working.':'Revoke this project’s public link?'))return;
  busy=true;dialog.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{const result=await api(`/api/projects/${project}/share`,{method:'POST',body:{action}});url.value=result.path?new URL(result.path,location.origin).href:'';status.textContent=result.path?'Link ready. Anyone with this link can view this project.':'Public access revoked.';}
  catch(error){status.textContent=error.message;}
  finally{busy=false;dialog.querySelectorAll('button').forEach(b=>b.disabled=false);$('#copy-project-share').disabled=!url.value;}
 });
 dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault()});
 $('#copy-project-share').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(url.value);status.textContent='Link copied.';}catch{url.focus();url.select();status.textContent='Select and copy the link above.';}});
}
function bindFrozenEstimateHeader(){
 const table=document.querySelector('.estimate-table'),wrapper=table.parentElement;
 const floating=document.createElement('div');floating.className='frozen-estimate-heading';floating.setAttribute('aria-hidden','true');floating.hidden=true;document.body.append(floating);
 let scheduled=false,signature='',copy=null;
 function update(){
  scheduled=false;
  const rect=table.getBoundingClientRect(),frame=wrapper.getBoundingClientRect(),head=table.tHead;
  const top=0,height=head.getBoundingClientRect().height;
  const visible=innerWidth>820&&state.view==='estimate'&&rect.top<top&&rect.bottom>top+height;
  document.body.style.setProperty('--estimate-heading-bottom',`${top+height+10}px`);
  floating.hidden=!visible;document.body.classList.toggle('estimate-heading-frozen',visible);if(!visible)return;
  floating.style.cssText=`top:${top}px;left:${Math.max(0,frame.left)}px;width:${Math.min(frame.right,innerWidth)-Math.max(0,frame.left)}px`;
  const widths=[...head.rows[0].cells].map(c=>c.getBoundingClientRect().width),next=widths.join(',');
  if(next!==signature||!copy){
   signature=next;copy=document.createElement('table');copy.className='estimate-table';copy.style.width=rect.width+'px';copy.style.minWidth=rect.width+'px';copy.style.tableLayout='fixed';
   const group=document.createElement('colgroup');for(const width of widths){const col=document.createElement('col');col.style.width=width+'px';group.append(col);}copy.append(group,head.cloneNode(true));floating.replaceChildren(copy);
  }
  copy.style.transform=`translateX(${-wrapper.scrollLeft}px)`;
 }
 function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(update)}}
 document.addEventListener('scroll',schedule,{passive:true,capture:true});window.addEventListener('resize',schedule,{passive:true});new ResizeObserver(schedule).observe(table);window.addEventListener('hashchange',schedule);
}
