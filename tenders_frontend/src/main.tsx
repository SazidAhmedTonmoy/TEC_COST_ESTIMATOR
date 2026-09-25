import React from 'react';
import {createRoot} from 'react-dom/client';
import TenderApp from './components/tender-app';
import './globals.css';
export const session={user:null as any,csrf:''};
export function apiFetch(path:string,options:RequestInit={}){
 return fetch('/api/tenders/'+path,{...options,headers:{'Content-Type':'application/json','X-ConEst-Request':'1','X-CSRF-Token':session.csrf,...options.headers}}).then(r=>{if(r.status===401){location.href='/?return=tenders';throw Error('Please sign in');}return r});
}
async function start(){
 try{
 const response=await fetch('/api/auth/session');if(response.status===401){location.replace('/?return=tenders');return;}
 if(!response.ok)throw Error('Could not load your session. Please retry.');
 const data=await response.json();session.user=data.user;session.csrf=data.csrf_token;
 if(data.user.must_change_password){location.replace('/?workspace=tenders#/profile');return;}
 const view=location.pathname.split('/')[2]||'dashboard';
 createRoot(document.getElementById('root')!).render(<TenderApp initialView={view}/>);
 }catch(e){const root=document.getElementById('root')!;root.textContent=(e as Error).message;const button=document.createElement('button');button.textContent='Retry';button.onclick=start;root.append(button);}
}
start();
