/* v3.7.19 — user-scoped action centre on the Estimator Home page. */
const myWorkState = {scope:'mine',data:null,loading:false,error:'',lastLoad:0,request:0,userId:null};

function renderMyWork(){
  const root=document.getElementById('my-work-home');
  if(!root||!state.user)return;
  const result=myWorkState.data;
  const heading=`<div class="my-work-home-heading"><div><p class="my-work-home-eyebrow">PERSONAL ACTION CENTRE</p><h2>My Work</h2><p>What needs attention next · based on your saved responsibilities</p></div><div class="my-work-home-switch" role="group" aria-label="Work scope"><button type="button" data-work-scope="mine" aria-pressed="${myWorkState.scope==='mine'}" class="${myWorkState.scope==='mine'?'active':''}">My work</button><button type="button" data-work-scope="team" aria-pressed="${myWorkState.scope==='team'}" class="${myWorkState.scope==='team'?'active':''}" ${result&&!result.teamAvailable?'disabled title="Your account has no assigned team"':''}>${escapeHtml(myWorkState.scope==='team'&&result?.scopeLabel==='All teams'?'All teams':'My team')}</button><button class="my-work-home-refresh" type="button" data-work-refresh aria-label="Refresh My Work">↻</button></div></div>`;
  const metrics=[['needsApproval','Needs my approval'],['needsQuote','Approved, not quoted'],['dueSoon','Deadlines within 3 days'],['followUpsDue','Follow-ups due']];
  const metricHtml=`<div class="my-work-home-metrics">${metrics.map(([key,label])=>`<div class="my-work-home-metric"><span>${myWorkState.scope==='team'&&key==='needsApproval'?'Needs team approval':label}</span><strong>${result?Number(result.counts[key]||0):'—'}</strong></div>`).join('')}</div>`;
  const errorHtml=myWorkState.error?`<div class="my-work-home-error" role="alert">${escapeHtml(myWorkState.error)} <button data-work-refresh type="button">Retry</button></div>`:'';
  const actions=result?.actions||[];
  const list=`<div class="my-work-home-actions-title"><h3>Next actions</h3><small>${result?Number(result.actionCount):0} tasks · ${escapeHtml(myWorkState.scope==='team'?result?.scopeLabel||'Team view':'Assigned to you')}</small></div>${actions.length?`<div class="my-work-home-actions">${actions.map(item=>`<article class="my-work-home-action"><div><span class="my-work-home-action-tag ${item.kind==='chase'||(item.daysLeft!=null&&item.daysLeft<=3)?'urgent':''}">${escapeHtml(item.title)}</span><strong>${escapeHtml(item.project)}</strong><small>${escapeHtml(item.kind==='chase'?item.detail||'Scheduled follow-up':item.status==='approved'?'Approved · quote required':item.status==='review'?'In Review · decision pending':'Awaiting approval')}${item.due?' · '+escapeHtml(item.due.slice(0,10)):''}</small></div><button type="button" data-work-${item.kind==='chase'?'chase':'opportunity'}="${escapeHtml(item.id)}">${item.kind==='chase'?'Open Chase-up':'View opportunity'} ↗</button></article>`).join('')}</div>`:`<p class="my-work-home-empty">${myWorkState.loading?'Loading your work…':'You’re up to date. No actionable items in this view.'}</p>`}`;
  root.innerHTML=heading+errorHtml+metricHtml+list;
}

async function loadMyWork(force=false){
  if(!state.user||state.view!=='home')return;
  if(myWorkState.userId!==state.user.id){myWorkState.userId=state.user.id;myWorkState.scope='mine';myWorkState.data=null;myWorkState.lastLoad=0;myWorkState.request++;}
  if(!force&&(myWorkState.loading||Date.now()-myWorkState.lastLoad<90000)){renderMyWork();return;}
  const request=++myWorkState.request,userId=state.user.id;
  myWorkState.loading=true;myWorkState.error='';renderMyWork();
  try{
    const result=await api('/api/tenders/opportunities/my-work?scope='+encodeURIComponent(myWorkState.scope));
    if(request!==myWorkState.request||state.user?.id!==userId)return;
    myWorkState.data=result;myWorkState.lastLoad=Date.now();
  }catch(error){if(request===myWorkState.request)myWorkState.error=error?.message||'Unable to load My Work';}
  finally{if(request===myWorkState.request){myWorkState.loading=false;renderMyWork();}}
}

document.addEventListener('click',event=>{
  const target=event.target.closest('[data-work-scope],[data-work-refresh],[data-work-opportunity],[data-work-chase]');
  if(!target||!document.getElementById('my-work-home')?.contains(target))return;
  if(target.dataset.workScope){
    if(target.dataset.workScope===myWorkState.scope||target.disabled)return;
    myWorkState.scope=target.dataset.workScope;myWorkState.data=null;myWorkState.lastLoad=0;myWorkState.request++;
    void loadMyWork(true);
  }else if(target.hasAttribute('data-work-refresh')){myWorkState.lastLoad=0;void loadMyWork(true)}
  else if(target.dataset.workOpportunity){location.href='/tenders/opportunities?open='+encodeURIComponent(target.dataset.workOpportunity)}
  else if(target.dataset.workChase){location.href='/tenders/chase-up?submission='+encodeURIComponent(target.dataset.workChase)}
});
window.addEventListener('focus',()=>{if(state.view==='home'&&state.user)void loadMyWork()});
