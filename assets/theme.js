/* Apply before paint; keep this browser's preference across sign-in and refresh. */
(()=>{
  if(new URLSearchParams(location.search).get('workspace')==='tenders')document.documentElement.dataset.workspace='tenders';
  let choice;try{choice=localStorage.getItem('tec-theme');}catch{}
  const prefersDark=()=>window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches;
  function apply(theme){document.documentElement.dataset.theme=theme;const button=document.getElementById('theme-toggle');if(button){button.setAttribute('title',theme==='dark'?'Switch to light mode':'Switch to dark mode');button.setAttribute('aria-pressed',String(theme==='dark'));button.setAttribute('aria-label',theme==='dark'?'Switch to light mode':'Switch to dark mode');}}
  apply(choice==='dark'||choice==='light'?choice:prefersDark()?'dark':'light');
  document.addEventListener('DOMContentLoaded',()=>{apply(document.documentElement.dataset.theme);document.getElementById('theme-toggle').addEventListener('click',()=>{choice=document.documentElement.dataset.theme==='dark'?'light':'dark';try{localStorage.setItem('tec-theme',choice);}catch{}apply(choice);});});
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change',()=>{if(!choice)apply(prefersDark()?'dark':'light');});
})();
