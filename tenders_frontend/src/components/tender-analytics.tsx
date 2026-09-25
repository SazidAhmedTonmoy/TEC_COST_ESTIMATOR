import {useMemo} from 'react';
import type {Submission} from '@/lib/types';
export const chartColors=['#d9aa00','#16834a','#db3f4b','#4d73d8','#a055cc','#e67622','#0896a6','#697780'];
export const feedbackLabel=(value:string)=>value==='Nil'||!value?'No feedback':value;
export const feedbackColors:Record<string,string>={'No feedback':'#8d9ba8',Competitive:'#21a56c',High:'#ef5263','Mid-Range':'#5291ef',Lower:'#b776ed','Not recorded':'#e78e35',Mix:'#20b4bf'};
export const builderColors:Record<string,string>={Unsuccessful:'#ef5263',Awarded:'#21a56c','In Progress':'#5291ef',Hold:'#b776ed','Builder Withdrawn':'#e78e35',Suspended:'#8d9ba8'};
export function AnalyticsCard({title,field,rows,onSelect}:{title:string;field:'builderStatus'|'pricing';rows:Submission[];onSelect:(value:string)=>void}){
 const color=(label:string)=>(field==='pricing'?feedbackColors[feedbackLabel(label)]:builderColors[label])||'#20b4bf';
 const counts=useMemo(()=>{const result=new Map<string,number>();for(const s of rows){const k=s[field]||'Not recorded';result.set(k,(result.get(k)||0)+1)}return [...result].sort((a,b)=>b[1]-a[1])},[rows,field]);
 let sum=0;const gradient=counts.map(([label,n])=>{const from=sum;sum+=n/Math.max(rows.length,1)*100;return `${color(label)} ${from}% ${sum}%`}).join(',');
 return <section className="panel analytics-panel"><div className="panel-heading"><h2>{title}</h2></div><div className="pipeline-body"><div className="donut" style={{background:counts.length?`conic-gradient(${gradient})`:'var(--muted)'}}><div><strong>{rows.length}</strong><span>submissions</span></div></div><div className="pipeline-legend">{counts.map(([label,count])=><button key={label} onClick={()=>onSelect(label)}><span className="legend-dot" style={{background:color(label)}}/><span>{label==='Nil'?'No feedback':label}</span><b>{count}</b></button>)}</div></div></section>
}
