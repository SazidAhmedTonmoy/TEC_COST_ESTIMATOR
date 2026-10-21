import {useRef,useState} from 'react';
import {CheckCircle2,Download,FileSpreadsheet,Upload} from 'lucide-react';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './ui/dialog';
import {apiFetch} from '../main';
import type {OpportunityRegion} from '@/lib/opportunity-types';

type ImportPreview={
  token:string;applied?:boolean;counts:{new:number;updated:number;unchanged:number;duplicates?:number;skippedChanged?:number;errors:number};
  rows:{project:string;region:string;action:string;builders:string[];sourceRow:number;sheet:string;due:string;message?:string}[];
  issues:{sheet:string;row:number;message:string}[];warnings?:Array<string|{sheet:string;row:number;message:string}>;
  previewTruncated?:boolean;totalRows?:number;
};
export async function downloadOpportunities(query='') {
  const response=await apiFetch(query.includes('template=1')?'opportunities/template.xlsx':'opportunities/export.xlsx'+query);
  if(!response.ok)throw Error((await response.json()).error||'Unable to export opportunities.');
  const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');
  link.href=url;link.download=query.includes('template=1')?'TEC-Opportunities-Template.xlsx':'TEC-Opportunities.xlsx';
  link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export function OpportunityImport({regions,onImported}:{regions:OpportunityRegion[];onImported:()=>Promise<unknown>}) {
  const [open,setOpen]=useState(false),[file,setFile]=useState<File|null>(null),[content,setContent]=useState('');
  const [preview,setPreview]=useState<ImportPreview|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [dragging,setDragging]=useState(false),[region,setRegion]=useState(''),[done,setDone]=useState(false);
  const input=useRef<HTMLInputElement>(null),pending=useRef(false),dragDepth=useRef(0);
  async function request(mode:'preview'|'apply',encoded=content,name=file?.name,hint=region) {
    const response=await apiFetch('opportunities/import',{method:'POST',body:JSON.stringify({filename:name,content:encoded,mode,token:preview?.token,region:hint})});
    const result=await response.json();if(!response.ok){if(response.status===409)setPreview(null);throw Error(result.error||'Import failed. Please try again.')}return result as ImportPreview;
  }
  async function inspect(selected:File,hint=region) {
    if(pending.current)return;pending.current=true;setBusy(true);setFile(selected);setPreview(null);setError('');setDone(false);
    try {
      if(!/\.xlsx$/i.test(selected.name))throw Error('Choose an Excel .xlsx workbook.');
      if(selected.size>15*1024*1024)throw Error('Choose a workbook smaller than 15 MB.');
      const encoded=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('This file could not be read.'));reader.readAsDataURL(selected)});
      setContent(encoded);setPreview(await request('preview',encoded,selected.name,hint));
    }catch(e){setError((e as Error).message)}finally{pending.current=false;setBusy(false)}
  }
  async function apply(){if(pending.current)return;pending.current=true;setBusy(true);setError('');try{setPreview(await request('apply'));setDone(true);await onImported();window.dispatchEvent(new Event('tenders:notifications-changed'))}catch(e){setError((e as Error).message)}finally{pending.current=false;setBusy(false)}}
  return <><button className="secondary-btn" onClick={()=>{setOpen(true);setFile(null);setContent('');setPreview(null);setError('');setDone(false);setRegion('')}}><Upload size={16}/>Import Excel</button>
    <Dialog open={open} onOpenChange={value=>{if(!busy)setOpen(value)}}><DialogContent className="op-dialog op-import-dialog" showCloseButton={!busy}><DialogHeader><DialogTitle>{done?'Import complete':'Import opportunities'}</DialogTitle><DialogDescription>Import an NSW or VIC opportunities workbook, or a TEC Opportunities export. Preview the records before adding them.</DialogDescription></DialogHeader>
      {!done&&<><div className="op-import-tools"><label className="op-field">Default region<select value={region} disabled={busy} onChange={e=>{setRegion(e.target.value);setPreview(null);if(file)void inspect(file,e.target.value)}}><option value="">Detect from workbook</option>{regions.map(r=><option key={r.code} value={r.code}>{r.code}</option>)}</select></label><button type="button" className="text-btn" disabled={busy} onClick={async()=>{try{await downloadOpportunities('?template=1')}catch(e){setError((e as Error).message)}}}><Download size={15}/>Download template</button></div>
      <input ref={input} className="sr-only" type="file" accept=".xlsx" aria-label="Opportunities Excel workbook" disabled={busy} onChange={e=>{const selected=e.target.files?.[0];if(selected)void inspect(selected);e.target.value=''}}/>
      <button type="button" className={'op-dropzone '+(dragging?'is-dragging':'')} disabled={busy} onClick={()=>input.current?.click()} onDragEnter={e=>{e.preventDefault();dragDepth.current++;setDragging(true)}} onDragOver={e=>{e.preventDefault();e.dataTransfer.dropEffect='copy'}} onDragLeave={e=>{e.preventDefault();if(--dragDepth.current<=0)setDragging(false)}} onDrop={e=>{e.preventDefault();dragDepth.current=0;setDragging(false);if(e.dataTransfer.files.length>1){setError('Import one workbook at a time.');return}const selected=e.dataTransfer.files[0];if(selected&&!busy)void inspect(selected)}}><FileSpreadsheet size={32}/><b>{file?.name||'Drop your Excel workbook here'}</b><span>{busy?'Reading workbook…':'or choose a file · XLSX up to 15 MB'}</span></button></>}
      {error&&<div className="error-banner" role="alert">{error}</div>}
      {preview&&<><div className="op-import-counts" aria-live="polite">{[['new','New'],['unchanged','Already added'],['errors','Needs review']].map(([key,label])=><div key={key}><strong>{preview.counts[key as keyof typeof preview.counts]||0}</strong><span>{label}</span></div>)}</div>
      {(preview.counts.skippedChanged||0)>0&&<p className="op-info"><b>{preview.counts.skippedChanged} existing opportunit{preview.counts.skippedChanged===1?'y differs':'ies differ'}.</b> Current app values will be kept. Edit these opportunities in the app to update them.</p>}
      {Boolean(preview.issues?.length||preview.warnings?.length)&&<div className="op-import-issues"><h3>Review these rows</h3>{preview.issues?.map((issue,i)=><p key={i}>{issue.sheet}{issue.row?` · Row ${issue.row}`:''}: {issue.message}</p>)}{preview.warnings?.map((warning,i)=><p key={'warning'+i}>{typeof warning==='string'?warning:`${warning.sheet} · Row ${warning.row}: ${warning.message}`}</p>)}</div>}
      {!done&&preview.rows?.length>0&&<div className="op-import-preview">{preview.rows.map((row,i)=><div key={i}><span className={'op-import-action '+row.action}>{row.action==='new'?'New':row.action==='duplicate'?'Already added':row.action==='skipped'?'Kept app values':'Review'}</span><div><b>{row.project||'Unnamed project'}</b><small>{row.region||'No region'}{row.builders?.length?' · '+row.builders.join(', '):''}</small>{row.message&&<small>{row.message}</small>}</div></div>)}</div>}{!done&&preview.previewTruncated&&<p className="op-help">Showing the first {preview.rows.length} of {preview.totalRows} workbook rows.</p>}
      {done?<p className="op-success" role="status"><CheckCircle2 size={19}/>Opportunities have been added.</p>:<p className="op-help">Existing opportunities keep their decisions, assignments and edits. Duplicate rows are skipped. New imports enter the approval workflow; past deadlines appear as Expired.</p>}</>}
      <div className="op-dialog-actions"><button className="secondary-btn" disabled={busy} onClick={()=>setOpen(false)}>{done?'Done':'Cancel'}</button>{!done&&preview&&<button className="primary-btn" disabled={busy||!preview.counts.new||preview.counts.errors>0} onClick={apply}>{busy?'Importing…':`Import ${preview.counts.new} opportunit${preview.counts.new===1?'y':'ies'}`}</button>}{!done&&file&&!preview&&!busy&&<button className="primary-btn" onClick={()=>inspect(file)}>Preview again</button>}</div>
    </DialogContent></Dialog></>;
}
