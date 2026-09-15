document.addEventListener('DOMContentLoaded',()=>{
 const sidebar=document.querySelector('.sidebar'),button=document.getElementById('mobile-menu-button');
 function close(){sidebar.classList.remove('menu-open');button.setAttribute('aria-expanded','false');}
 button.addEventListener('click',()=>{const open=button.getAttribute('aria-expanded')!=='true';sidebar.classList.toggle('menu-open',open);button.setAttribute('aria-expanded',String(open));});
 sidebar.addEventListener('click',event=>{if(event.target.closest('a[href^="#/"]'))close();});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&button.getAttribute('aria-expanded')==='true'){close();button.focus();}});
 window.addEventListener('hashchange',close);
 window.matchMedia('(min-width: 821px)').addEventListener('change',close);
});
