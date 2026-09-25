(()=>{
 let finished=false;
 function show(){
  if(finished)return;
  const host=document.getElementById('boot-status')||(document.body.classList.contains('app-loading')?document.querySelector('#startup-screen>div'):null);
  if(!host||document.getElementById('startup-recovery'))return;
  const box=document.createElement('div');box.id='startup-recovery';box.setAttribute('role','status');
  const message=document.createElement('p');message.textContent='Loading is taking longer than expected.';
  const retry=document.createElement('button');retry.type='button';retry.className='button secondary';retry.textContent='Reload page';retry.onclick=()=>location.reload();
  box.append(message,retry);host.append(box);
 }
 const timer=setTimeout(show,20000);
 window.addEventListener('error',event=>{if(event.target?.tagName==='SCRIPT')show()},true);
 window.addEventListener('conest:workspace-ready',()=>{finished=true;clearTimeout(timer);document.getElementById('startup-recovery')?.remove()},{once:true});
})();
