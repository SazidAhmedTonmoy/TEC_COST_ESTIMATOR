import {useEffect,useRef,useState} from 'react';
import {Upload,Plus,ClipboardList,Trash2,X} from 'lucide-react';
import {apiFetch} from '../main';
import {validateDetectedContact,type DetectedContact} from '../lib/contact-screenshot';
import './contact-screenshot-import.css';

type Preview={rows:DetectedContact[];text:string;warnings:string[]};
const blank=():DetectedContact=>({builder:'',name:'',phones:[],emails:[]});
const fileContent=(file:File)=>new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(Error('Could not read the screenshot.'));reader.onload=()=>resolve(String(reader.result).split(',')[1]||'');reader.readAsDataURL(file)});

export function ContactScreenshotImport({builders,disabled,onApply}:{builders:string[];disabled:boolean;onApply:(rows:DetectedContact[])=>void}){
 const [expanded,setExpanded]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[filename,setFilename]=useState('');
 const [preview,setPreview]=useState<Preview|null>(null),[text,setText]=useState('');
 const input=useRef<HTMLInputElement>(null),request=useRef<AbortController|null>(null),mounted=useRef(true);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;request.current?.abort()}},[]);
 async function recognize(payload:{content:string}|{text:string}){
  request.current?.abort();const controller=new AbortController();request.current=controller;setBusy(true);setError('');setPreview(null);
  try{
   const response=await apiFetch('opportunities/contact-screenshot',{method:'POST',body:JSON.stringify({...payload,knownBuilders:builders.slice(0,2000)}),signal:controller.signal});
   const result=await response.json() as Preview&{error?:string};if(!response.ok)throw Error(result.error||'Unable to recognize contacts.');
   if(!controller.signal.aborted){setPreview(result);setText(result.text)}
  }catch(e){if(!controller.signal.aborted)setError((e as Error).message)}finally{if(!controller.signal.aborted)setBusy(false)}
 }
 async function choose(file:File|undefined){
  if(!file||disabled||busy)return;
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)){setError('Choose a PNG, JPEG or WebP screenshot.');return}
  if(file.size>6*1024*1024){setError('Crop the screenshot to the contact list or choose an image under 6 MB.');return}
  setFilename(file.name);setText('');setPreview(null);setBusy(true);setError('');
  try{const content=await fileContent(file);if(mounted.current)await recognize({content})}catch(e){if(mounted.current){setError((e as Error).message);setBusy(false)}}
 }
 function update(index:number,patch:Partial<DetectedContact>){setPreview(p=>p?{...p,rows:p.rows.map((r,i)=>i===index?{...r,...patch}:r)}:p)}
 function close(){request.current?.abort();setExpanded(false);setBusy(false);setPreview(null);setText('');setFilename('');setError('')}
 function apply(){if(!preview?.rows.length)return;try{for(const row of preview.rows){const message=validateDetectedContact(row);if(message)throw Error(message)}onApply(preview.rows);close()}catch(e){setError((e as Error).message)}}
 return <section className="contact-screenshot-import" aria-label="Import builders from screenshot">
  <button type="button" className="secondary-btn contact-screenshot-trigger" aria-expanded={expanded} disabled={disabled||busy} onClick={()=>expanded?close():setExpanded(true)}><Upload size={16}/>Import screenshot</button>
  {expanded&&<div className="contact-screenshot-panel" onKeyDown={e=>{if(e.key==='Enter'&&(e.target as HTMLElement).tagName==='INPUT')e.preventDefault()}} onPaste={e=>{const file=[...e.clipboardData.files].find(f=>f.type.startsWith('image/'));if(file){e.preventDefault();void choose(file)}}}>
   <div className="contact-screenshot-heading"><strong><ClipboardList size={16}/>Detect builders and contacts</strong><button type="button" className="text-btn" aria-label="Close screenshot import" disabled={busy} onClick={close}><X size={16}/></button></div>
   <p className="op-help">Choose a cropped builder/contact screenshot. Recognition is private on your server; nothing is saved until you save the opportunity.</p>
   <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" className="contact-screenshot-file" aria-label="Select builder contact screenshot" disabled={disabled||busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';void choose(file)}}/>
   <div className="contact-screenshot-upload"><button type="button" className="secondary-btn" disabled={disabled||busy} onClick={()=>input.current?.click()}><Upload size={15}/>{busy?'Recognizing…':'Choose screenshot'}</button><span>{filename||'PNG, JPEG, WebP · up to 6 MB'}</span></div>
   {busy&&<p role="status">Recognizing builder and contact details…</p>}
   {error&&<p className="error-banner" role="alert">{error}</p>}
   <details className="contact-screenshot-text" open={!!error&&!preview?true:undefined}><summary>Paste or correct recognized text</summary><textarea value={text} maxLength={24000} rows={5} disabled={busy||disabled} onChange={e=>setText(e.target.value)} placeholder={'Builder name\nPhone number\nContact person\nEmail address'}/><button type="button" className="secondary-btn" disabled={disabled||busy||!text.trim()} onClick={()=>void recognize({text})}>Detect from text</button></details>
   {preview&&<><div className="contact-screenshot-heading"><strong>Review {preview.rows.length} detected row{preview.rows.length===1?'':'s'}</strong><button className="secondary-btn" type="button" disabled={disabled||busy||preview.rows.length>=60} onClick={()=>setPreview(p=>p?{...p,rows:[...p.rows,blank()]}:p)}><Plus size={14}/>Add row</button></div>
    <p className="op-help">Check spelling and which person belongs to each builder. Remove incorrect rows. Existing saved people are reused where there is a clear match.</p>
    {preview.warnings.map(w=><p key={w} className="op-help">{w}</p>)}
    {preview.rows.map((row,index)=><div className="contact-screenshot-row" key={index}>
     <div className="contact-screenshot-heading"><b>Row {index+1}</b><button type="button" className="text-btn" disabled={disabled||busy} aria-label={'Remove detected row '+(index+1)} onClick={()=>setPreview(p=>p?{...p,rows:p.rows.filter((_,i)=>i!==index)}:p)}><Trash2 size={14}/>Remove</button></div>
     <label>Builder<input value={row.builder} maxLength={500} disabled={disabled||busy} list="op-existing-builders" onChange={e=>update(index,{builder:e.target.value})}/></label>
     <label>Contact person<input value={row.name} maxLength={200} disabled={disabled||busy} onChange={e=>update(index,{name:e.target.value})}/></label>
     <label>Phone numbers (one per line)<textarea rows={2} value={row.phones.join('\n')} disabled={disabled||busy} onChange={e=>update(index,{phones:e.target.value.split('\n')})}/></label>
     <label>Email addresses (one per line)<textarea rows={2} value={row.emails.join('\n')} disabled={disabled||busy} onChange={e=>update(index,{emails:e.target.value.split('\n')})}/></label>
     {validateDetectedContact(row)&&<small role="status">{validateDetectedContact(row)}</small>}
    </div>)}
    <button type="button" className="primary-btn" disabled={disabled||busy||!preview.rows.length||preview.rows.some(row=>!!validateDetectedContact(row))} onClick={apply}>Add reviewed builders &amp; contacts</button>
   </>}
  </div>}
 </section>;
}
