import React from 'react';
import {createRoot} from 'react-dom/client';
import TenderApp from './components/tender-app';
import './globals.css';
import {request} from './lib/request';
export const session={user:null as any,csrf:''};
export function apiFetch(path:string,options:RequestInit={}){
 return request('/api/tenders/'+path,{...options,headers:{'Content-Type':'application/json','X-ConEst-Request':'1','X-CSRF-Token':session.csrf,...options.headers}}).then(r=>{if(r.status===401){location.href='/?return=tenders';throw Error('Please sign in');}if(!r.ok&&!(r.headers.get('content-type')||'').includes('application/json'))throw Error('The server is busy or returned an unexpected response. Refresh to check the latest saved information.');return r});
}
const startupSidebar=document.querySelector('.boot-sidebar')?.outerHTML||'';
class TenderRecovery extends React.Component<{children:React.ReactNode},{failed:boolean}>{
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true};}
 componentDidCatch(){window.dispatchEvent(new Event('conest:workspace-ready'));}
 render(){return this.state.failed?<><div dangerouslySetInnerHTML={{__html:startupSidebar}}/><main className="boot-loading"><div role="alert"><p>Unable to display Tenders. Please reload the page.</p><button onClick={()=>location.reload()}>Reload page</button></div></main></>:this.props.children;}
}
async function start(){
 try{
 const boot=window as Window & {__tenderBoot?:Promise<any>;conestTenderStart?:()=>Promise<any>};
 const pending=boot.__tenderBoot;delete boot.__tenderBoot;
 if(!pending&&!boot.conestTenderStart)throw Error('Startup files did not load. Reload the page.');
 const response=await (pending||boot.conestTenderStart!());if(!response)throw Error('Unable to connect. Please retry.');if(response.status===401){location.replace('/?return=tenders');return;}
 if(!response.ok)throw Error('Could not load your session. Please retry.');
 const data=response.data;session.user=data.user;session.csrf=data.csrf_token;
 if(data.user.must_change_password){location.replace('/?workspace=tenders#/profile');return;}
 const view=location.pathname.split('/')[2]||'dashboard';
 createRoot(document.getElementById('root')!).render(<TenderRecovery><TenderApp initialView={view} initialData={data.data}/></TenderRecovery>);
 }catch(e){window.dispatchEvent(new Event('conest:workspace-ready'));const root=document.getElementById('boot-status')||document.getElementById('root')!;root.textContent=(e as Error).message;const button=document.createElement('button');button.textContent='Retry';button.onclick=start;root.append(button);}
}
start();
