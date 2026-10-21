import type {AppData} from './types';

export type StartupResponse={
  status:number;ok:boolean;data:unknown;
  format?:'json'|'invalid-json'|'other';failure?:'network'|'timeout';
};
export type StartupProblem={
  title:string;message:string;status?:number;reference?:string;code?:string;action:'retry'|'reload';
};
type SessionUser={id:number;name:string;role:string;must_change_password?:boolean|number;[key:string]:unknown};
export type BootstrapSession={user:SessionUser;csrf_token:string;data?:unknown};
const record=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value);
const identifier=(value:unknown)=>typeof value==='string'&&/^[A-Za-z0-9_-]{1,80}$/.test(value)?value:undefined;

function safeMessage(value:unknown){
  if(typeof value!=='string')return undefined;
  const message=value.trim();
  // Older deployments/proxies may return exception text. Keep diagnostic
  // references, but do not display markup, tracebacks or filesystem paths.
  if(!message||message.length>600||/[<>\r\n]/.test(message)||/Traceback|File\s+["']|[A-Za-z]:[\\/]|(?:^|[\s"'(])\/(?:[\w.-]+\/)+|(?:sqlite3|ModuleNotFoundError|ImportError)\./i.test(message))return undefined;
  return message;
}

export function startupProblem(response:StartupResponse|null|undefined):StartupProblem{
  if(!response||response.failure==='network')return {title:'Could not connect to Tenders',message:'Check your connection and retry. If this continues, ask your administrator to check the server.',action:'retry'};
  if(response.failure==='timeout')return {title:'Tenders took too long to respond',message:'Please retry. If this continues, ask your administrator to check the server.',action:'retry'};
  const data=record(response.data)?response.data:{};
  const reference=identifier(data.error_reference),code=identifier(data.error_code);
  const status=response.status||undefined;
  let title='Tenders could not load',message='Please retry. If this continues, ask your administrator to check the server.',action:StartupProblem['action']='retry';
  if(code==='SESSION_STARTUP_FAILED'){title='Your sign-in could not be checked';message='Please retry. If this continues, ask your administrator to check the sign-in service.'}
  else if(response.status===403){title='Tenders access was denied';message='Ask your administrator to check your access, then retry.'}
  else if(response.status===404){title='The Tenders startup service was not found';message='Reload the page. If this continues, ask your administrator to check the deployment.';action='reload'}
  else if(response.status===429){title='Tenders is receiving too many requests';message='Wait a moment, then retry.'}
  else if([502,503,504].includes(response.status)){title='The Tenders server is temporarily unavailable';message='Please retry shortly. If this continues, ask your administrator to check the server.'}
  else if(response.ok){title='Tenders returned an unexpected response';message='Reload the page to get the current version. If this continues, ask your administrator to check the deployment.';action='reload'}
  return {title,message:(!response.ok&&safeMessage(data.error))||message,status,reference,code,action};
}

export function validBootstrapSession(value:unknown):value is BootstrapSession{
  return record(value)&&record(value.user)&&Number.isInteger(value.user.id)&&Number(value.user.id)>0&&
    typeof value.user.name==='string'&&typeof value.user.role==='string'&&
    typeof value.csrf_token==='string'&&value.csrf_token.length>0;
}

export function validTenderData(value:unknown):value is AppData{
  return record(value)&&Array.isArray(value.submissions)&&Array.isArray(value.chases)&&Array.isArray(value.reminders)&&
    record(value.settings)&&typeof value.settings.author==='string'&&typeof value.settings.defaultDays==='number'&&
    Number.isFinite(value.settings.defaultDays)&&(!('teams' in value)||Array.isArray(value.teams));
}
