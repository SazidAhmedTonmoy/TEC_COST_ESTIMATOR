import React from 'react';
import {createRoot,type Root} from 'react-dom/client';
import TenderApp from './components/tender-app';
import './globals.css';
import './mobile-v3511.css';
import './mobile-v3512.css';
import {request} from './lib/request';
import {startupProblem,validBootstrapSession,validTenderData,type StartupProblem,type StartupResponse} from './lib/startup';
export const session={user:null as any,csrf:''};
export function apiFetch(path:string,options:RequestInit={}){
 return request('/api/tenders/'+path,{...options,headers:{'Content-Type':'application/json','X-ConEst-Request':'1','X-CSRF-Token':session.csrf,...options.headers}}).then(r=>{if(r.status===401){location.href='/?return=tenders';throw Error('Please sign in');}if(!r.ok&&!(r.headers.get('content-type')||'').includes('application/json'))throw Error('The server is busy or returned an unexpected response. Refresh to check the latest saved information.');return r});
}
const startupSidebar=document.querySelector('.boot-sidebar')?.outerHTML||'';
class TenderRecovery extends React.Component<{children:React.ReactNode},{failed:boolean}>{
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true};}
 componentDidCatch(){window.dispatchEvent(new Event('conest:workspace-ready'));}
 render(){return this.state.failed?<><div dangerouslySetInnerHTML={{__html:startupSidebar}}/><main className="boot-loading"><div className="boot-message" role="alert"><h1>Tenders could not display this page</h1><p>Reload the page. If this continues, ask your administrator to check the current deployment.</p><div className="boot-actions"><button onClick={()=>location.reload()}>Reload page</button><a href="/">Open Estimator</a></div></div></main></>:this.props.children;}
}
let starting=false,hasStarted=false,reactRoot:Root|null=null;
function statusHost(){return document.getElementById('boot-status')||document.getElementById('root')!}
function loading(retrying:boolean){
 const host=statusHost();host.className='boot-message';host.setAttribute('role','status');host.setAttribute('aria-label','Loading tenders');host.setAttribute('aria-busy','true');host.replaceChildren();
 const spinner=document.createElement('div');spinner.className='boot-spinner';spinner.setAttribute('aria-hidden','true');
 const title=document.createElement('h1');title.textContent=retrying?'Retrying Tenders…':'Loading Tenders…';
 host.append(spinner,title);
 if(retrying){const button=document.createElement('button');button.type='button';button.textContent='Retrying…';button.disabled=true;host.append(button)}
}
function failed(problem:StartupProblem){
 const host=statusHost();host.className='boot-message boot-error';host.setAttribute('role','alert');host.setAttribute('aria-label','Tenders startup error');host.setAttribute('aria-busy','false');host.replaceChildren();
 const title=document.createElement('h1');title.textContent=problem.title;
 const message=document.createElement('p');message.textContent=problem.message;host.append(title,message);
 if(problem.status||problem.reference||problem.code){
  const details=document.createElement('dl');details.className='boot-error-details';
  for(const [label,value] of [['Status',problem.status?`HTTP ${problem.status}`:undefined],['Error reference',problem.reference],['Error code',problem.code]]){
   if(!value)continue;const row=document.createElement('div'),name=document.createElement('dt'),text=document.createElement('dd');name.textContent=label!;text.textContent=value;row.append(name,text);details.append(row);
  }
  host.append(details);
 }
 const actions=document.createElement('div');actions.className='boot-actions';
 const button=document.createElement('button');button.type='button';button.textContent=problem.action==='reload'?'Reload page':'Retry';button.onclick=problem.action==='reload'?()=>location.reload():()=>{void start()};
 const estimator=document.createElement('a');estimator.href='/';estimator.textContent='Open Estimator';actions.append(button,estimator);host.append(actions);
 window.dispatchEvent(new Event('conest:workspace-ready'));
}
async function start(){
 if(starting)return;starting=true;loading(hasStarted);hasStarted=true;
 try{
 const boot=window as Window & {__tenderBoot?:Promise<StartupResponse|null>;conestTenderStart?:()=>Promise<StartupResponse|null>};
 const pending=boot.__tenderBoot;delete boot.__tenderBoot;
 if(!pending&&!boot.conestTenderStart){failed({title:'Tenders startup files did not load',message:'Reload the page. If this continues, ask your administrator to check the current deployment.',action:'reload'});return}
 const response=await (pending||boot.conestTenderStart!());
 if(response?.status===401){location.replace('/?return=tenders');return}
 if(!response||!response.ok||response.failure){failed(startupProblem(response));return}
 const data=response.data;
 if(!validBootstrapSession(data)){failed(startupProblem(response));return}
 if(data.user.must_change_password){location.replace('/?workspace=tenders#/profile');return;}
 if(!validTenderData(data.data)){failed(startupProblem(response));return}
 session.user=data.user;session.csrf=data.csrf_token;
 const view=location.pathname.split('/')[2]||'dashboard';
 reactRoot??=createRoot(document.getElementById('root')!);
 reactRoot.render(<TenderRecovery><TenderApp initialView={view} initialData={data.data}/></TenderRecovery>);
 }catch{failed(startupProblem(null))}finally{starting=false}
}
void start();
