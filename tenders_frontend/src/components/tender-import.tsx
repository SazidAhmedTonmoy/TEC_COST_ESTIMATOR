import {useRef,useState} from 'react';
import {Upload,FileSpreadsheet,Check} from 'lucide-react';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './ui/dialog';
import {apiFetch} from '../main';

type Preview={token:string;counts:Record<string,number>;changes:{action:string;project:string;builder:string;fields:string[]}[];totalChanges:number};
export function TenderImport({onImported}:{onImported:()=>Promise<unknown>}){
 const [open,setOpen]=useState(false),[file,setFile]=useState<File|null>(null),[content,setContent]=useState(''),[preview,setPreview]=useState<Preview|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[done,setDone]=useState(false);
 const input=useRef<HTMLInputElement>(null);
 async function request(mode:string,encoded=content,name=file?.name,token=preview?.token){
  const response=await apiFetch('import',{method:'POST',body:JSON.stringify({mode,filename:name,content:encoded,token})});
  const result=await response.json();if(!response.ok){if(response.status===409)setPreview(null);throw Error(result.error||'Import failed. Please retry.')}return result;
 }
 async function inspect(selected:File){
  setFile(selected);setError('');setPreview(null);setDone(false);setBusy(true);
  try{
   if(selected.size>15*1024*1024)throw Error('Choose a workbook smaller than 15 MB.');
   const encoded=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Cannot read this file.'));reader.readAsDataURL(selected)});
   setContent(encoded);setPreview(await request('preview',encoded,selected.name));
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 async function apply(){setBusy(true);setError('');try{const result=await request('apply');setPreview(result);setDone(true);await onImported()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 const changes=preview?preview.counts.added+preview.counts.updated+preview.counts.followupsAdded+preview.counts.followupsUpdated+preview.counts.remindersAdded+preview.counts.remindersUpdated:0;
 return <><button className="secondary-btn" onClick={()=>{setOpen(true);setError('');setPreview(null);setFile(null);setDone(false)}}><Upload size={17}/>Import Excel</button>
 <Dialog open={open} onOpenChange={v=>{if(!busy)setOpen(v)}}><DialogContent className="tender-import-dialog"><DialogHeader><DialogTitle>{done?'Import complete':'Import tender data'}</DialogTitle><DialogDescription>Upload the original workbook with its Raw Data sheet, or a TEC Tenders export. New records are added; changed records are updated.</DialogDescription></DialogHeader>
 <input ref={input} type="file" accept=".xlsx,.xlsm" aria-label="Tender Excel workbook" className="sr-only" disabled={busy} onChange={e=>{const chosen=e.target.files?.[0];if(chosen)inspect(chosen);e.target.value=''}}/>
 {!done&&<button className="import-file-picker" disabled={busy} onClick={()=>input.current?.click()}><FileSpreadsheet size={26}/><span><b>{file?.name||'Choose Excel workbook'}</b><small>{busy?'Processing workbook…':'XLSX or XLSM · up to 15 MB'}</small></span></button>}
 {error&&<p className="error-banner" role="alert">{error}</p>}
 {preview&&<><div className="import-counts" aria-live="polite">{[['added','New'],['updated','Updated'],['unchanged','Unchanged']].map(([key,label])=><div key={key}><strong>{preview.counts[key]}</strong><span>{label}</span></div>)}</div>
 <p className="import-note">Follow-ups: {preview.counts.followupsAdded} new, {preview.counts.followupsUpdated} updated. Scheduled reminders: {preview.counts.remindersAdded} new, {preview.counts.remindersUpdated} updated.{preview.counts.duplicates>0?` ${preview.counts.duplicates} duplicate rows skipped.`:''}</p>
 {!done&&preview.changes.length>0&&<div className="import-changes">{preview.changes.map((c,i)=><div key={i}><span className="subtle-tag">{c.action==='added'?'New':'Update'}</span><div><b>{c.project}</b><small>{c.builder}</small></div></div>)}{preview.totalChanges>100&&<p>Showing the first 100 of {preview.totalChanges} changes.</p>}</div>}
 {done?<p className="import-success" role="status"><Check size={18}/>Your tender data is up to date.</p>:<p className="import-note">Records missing from the workbook stay in the app. Reimporting the same file skips unchanged data. Changed Excel values replace the corresponding app values.</p>}</>}
 <div className="import-actions"><button className="secondary-btn" disabled={busy} onClick={()=>setOpen(false)}>{done?'Done':'Cancel'}</button>{!done&&(preview?<button className="primary-btn" disabled={busy} onClick={apply}>{busy?'Importing…':changes?'Import changes':'Finish check'}</button>:file&&!busy?<button className="primary-btn" onClick={()=>inspect(file)}>Preview again</button>:null)}</div>
 </DialogContent></Dialog></>;
}
