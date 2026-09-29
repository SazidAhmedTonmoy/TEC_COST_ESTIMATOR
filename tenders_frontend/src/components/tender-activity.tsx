import {useMemo,useState,useRef} from 'react';
import {ArrowUpRight} from 'lucide-react';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './ui/dialog';
import type {Submission} from '@/lib/types';
import {activityMonths} from '@/lib/activity';

export function TenderActivity({submissions,onSelect}:{submissions:Submission[];onSelect:(month:string)=>void}){
 const [expanded,setExpanded]=useState(false);
 const trigger=useRef<HTMLButtonElement>(null);
 const months=useMemo(()=>activityMonths(submissions),[submissions]);
 const years=[...new Set(months.map(m=>m.month.slice(0,4)))];
 const [year,setYear]=useState('all');
 const allVisible=year==='all'?months:months.filter(m=>m.month.startsWith(year+'-'));
 const chart=(rows:typeof months,full=false)=>{
  const max=Math.max(1,...rows.map(m=>m.count));
  return rows.length?<div className={full?'activity-history-scroll':''} tabIndex={full?0:undefined} aria-label={full?'Monthly activity chart; scroll horizontally for more months':undefined}><div className={'bar-chart'+(full?' activity-history-chart':'')} style={full?{minWidth:Math.max(500,rows.length*46)}:undefined}>{rows.map(({month,count})=><button className="bar-column" key={month} disabled={!count} onClick={()=>{setExpanded(false);onSelect(month)}} aria-label={`${new Date(month+'-01T12:00:00').toLocaleDateString('en-AU',{month:'long',year:'numeric'})}: ${count} submissions`}><b>{count}</b><div className="bar-track"><div style={{height:count/max*100+'%'}}/></div><span>{new Date(month+'-01T12:00:00').toLocaleDateString('en-AU',{month:'short'})}</span><small>{month.slice(0,4)}</small></button>)}</div></div>:<p className="activity-empty">No dated submissions yet.</p>;
 };
 return <><section className="panel activity-panel"><div className="panel-heading"><div><h2>Tender activity</h2><p>Submissions by due month</p></div><span className="subtle-tag">Latest 6 months</span></div>{chart(months.slice(-6))}<div className="panel-foot"><button ref={trigger} className="text-btn activity-expand" onClick={()=>{setYear('all');setExpanded(true)}}>View all months <ArrowUpRight size={15}/></button></div></section><Dialog open={expanded} onOpenChange={setExpanded}><DialogContent className="activity-history-dialog" onCloseAutoFocus={event=>{event.preventDefault();trigger.current?.focus()}}><DialogHeader><DialogTitle>Tender activity</DialogTitle><DialogDescription>All submission months. Select a bar to view the related tenders.</DialogDescription></DialogHeader><div className="activity-history-toolbar"><span>{allVisible.reduce((sum,m)=>sum+m.count,0)} submissions · {allVisible.length} months</span><label>Period<select aria-label="Activity period" value={year} onChange={e=>setYear(e.target.value)}><option value="all">All months</option>{years.map(y=><option key={y} value={y}>{y}</option>)}</select></label></div>{chart(allVisible,true)}<p className="form-hint">Scroll horizontally on smaller screens. Months without submissions show zero; undated submissions are excluded.</p></DialogContent></Dialog></>;
}
