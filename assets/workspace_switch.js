/* Tender assets are loaded only when entering the tender workspace. */
document.addEventListener('DOMContentLoaded',()=>{
 const inTenders=new URLSearchParams(location.search).get('workspace')==='tenders';
 const brand=document.querySelector('.sidebar .brand');
 // Visible workspace tabs replace the ambiguous circular-arrow control.
 // Keep the workspace-swap class on the *inactive* link so the existing
 // cross-workspace loading transition continues to work without interception.
 if(!brand||brand.closest('.workspace-brand'))return;
 const tabs=document.createElement('nav');
 tabs.className='workspace-tabs';
 tabs.setAttribute('aria-label','Switch workspace');
 for(const [name,url,active] of [
   ['Estimator','/',!inTenders],['Tenders','/tenders/',inTenders]
 ]){
   const tab=document.createElement('a');
   tab.className='workspace-tab'+(active?' is-active':' workspace-swap');
   tab.href=active?(inTenders?'/tenders/':'#/home'):url;
   tab.textContent=name;
   if(active)tab.setAttribute('aria-current','page');
   else tab.setAttribute('aria-label','Switch to '+name);
   tabs.append(tab);
 }
 const wrap=document.createElement('div');
 wrap.className='workspace-brand';
 brand.before(wrap);
 wrap.append(brand,tabs);
 if(inTenders){document.documentElement.dataset.workspace='tenders';brand.querySelector('div:last-child span').textContent='TENDERS';brand.href='/tenders/';brand.removeAttribute('data-view');
 const nav=document.querySelector('#main-navigation');nav.querySelectorAll('.nav-button').forEach(a=>a.remove());
 const pages=[['dashboard','Home','⌂'],['chase-up','Project Chase-up','☷'],['projects','Projects','▦'],['builders','Builders','♙'],['calendar','Calendar','▤'],['reminders','Reminders','◷']];
 for(const [path,label,icon] of pages.reverse()){const a=document.createElement('a');a.className='nav-button';a.href='/tenders/'+path;a.innerHTML=`<span>${icon}</span> ${label}`;nav.prepend(a);}
 }
});
