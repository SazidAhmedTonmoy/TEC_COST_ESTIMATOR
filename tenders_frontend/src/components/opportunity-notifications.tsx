import './opportunities.css';
import {useEffect,useRef,useState} from 'react';
import {BellRing} from 'lucide-react';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './ui/dialog';
import {opportunityRequest} from '@/lib/opportunities';
import {toast} from 'sonner';
type Notice={id:number;opportunity_id:string;project:string;action:string;actor_name:string;created_at:string;read_at:string|null};
export function OpportunityNotifications({onOpen}:{onOpen:(id:string)=>void}){
 const [open,setOpen]=useState(false),[items,setItems]=useState<Notice[]>([]),[unread,setUnread]=useState(0),[error,setError]=useState('');
 const busy=useRef(false);
 async function refresh(){if(busy.current||document.hidden)return;busy.current=true;try{const d=await opportunityRequest('/notifications');setItems(d.items);setUnread(d.unread);setError('')}catch(e){setError((e as Error).message)}finally{busy.current=false}}
 useEffect(()=>{refresh();const t=setInterval(refresh,60000);window.addEventListener('opportunities:changed',refresh);document.addEventListener('visibilitychange',refresh);return()=>{clearInterval(t);window.removeEventListener('opportunities:changed',refresh);document.removeEventListener('visibilitychange',refresh)}},[]);
 async function read(){if(!items.length)return;try{await opportunityRequest('/notifications/read',{through:items[0].id});refresh()}catch(e){toast.error((e as Error).message)}}
 return <><button className="notification-btn" title="Opportunity notifications" aria-label={`Opportunity notifications${unread?', '+unread+' unread':''}`} onClick={()=>{setOpen(true);refresh()}}><BellRing size={20}/>{unread>0&&<span>{unread>99?'99+':unread}</span>}</button><Dialog open={open} onOpenChange={setOpen}><DialogContent className="tender-dialog opportunity-inbox"><DialogHeader><DialogTitle>Opportunity notifications</DialogTitle><DialogDescription>Assignments, decisions and deadline updates for your opportunities.</DialogDescription></DialogHeader>{error&&<p role="alert">{error} <button className="text-btn" onClick={refresh}>Retry</button></p>}<div className="opportunity-inbox-heading"><span>{unread} unread</span><button className="secondary-btn" disabled={!unread} onClick={read}>Mark all read</button></div>{items.map(n=><button key={n.id} className={'opportunity-notice '+(!n.read_at?'unread':'')} onClick={()=>{setOpen(false);onOpen(n.opportunity_id)}}><strong>{n.project}</strong><span>{n.action} · {n.actor_name}</span><small>{new Date(n.created_at).toLocaleString('en-AU')}</small></button>)}{!items.length&&!error&&<p className="muted">You’re up to date. New assignments and deadline alerts will appear here.</p>}</DialogContent></Dialog></>;
}
