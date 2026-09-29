/* Tender assets are loaded only when entering the tender workspace. */
document.addEventListener('DOMContentLoaded',()=>{
 const inTenders=new URLSearchParams(location.search).get('workspace')==='tenders';
 const brand=document.querySelector('.sidebar .brand');
 const swap=document.createElement('a');swap.className='workspace-swap';swap.href=inTenders?'/':'/tenders/';swap.title=inTenders?'Switch to Estimator':'Switch to Tenders';swap.setAttribute('aria-label',swap.title);
 swap.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 10a9 9 0 0 1 15-6l3 3M21 2v5h-5M21 14a9 9 0 0 1-15 6l-3-3M3 22v-5h5"/></svg>';
 const wrap=document.createElement('div');wrap.className='workspace-brand';brand.before(wrap);wrap.append(brand,swap);
 if(inTenders){document.documentElement.dataset.workspace='tenders';brand.querySelector('div:last-child span').textContent='TENDERS';brand.href='/tenders/';brand.removeAttribute('data-view');
 const nav=document.querySelector('#main-navigation');nav.querySelectorAll('.nav-button').forEach(a=>a.remove());
 const pages=[['dashboard','Home','⌂'],['chase-up','Project Chase-up','☷'],['projects','Projects','▦'],['builders','Builders','♙'],['calendar','Calendar','▤'],['reminders','Reminders','◷']];
 for(const [path,label,icon] of pages.reverse()){const a=document.createElement('a');a.className='nav-button';a.href='/tenders/'+path;a.innerHTML=`<span>${icon}</span> ${label}`;nav.prepend(a);}
 }
});
