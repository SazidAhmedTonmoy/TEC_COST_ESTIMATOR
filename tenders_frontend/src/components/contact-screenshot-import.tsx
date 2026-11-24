import {useEffect,useRef,useState} from 'react';
import {Upload,Plus,ClipboardList,Trash2,X,ClipboardPaste} from 'lucide-react';
import {apiFetch} from '../main';
import {validateDetectedContact,type DetectedContact} from '../lib/contact-screenshot';
import {pastedScreenshot,recognizeScreenshot,screenshotError} from '../lib/browser-contact-ocr';
import './contact-screenshot-import.css';

type Preview={rows:DetectedContact[];text:string;warnings:string[]};
const blank=():DetectedContact=>({builder:'',name:'',phones:[],emails:[]});

export function ContactScreenshotImport({builders,disabled,onApply}:{builders:string[];disabled:boolean;onApply:(rows:DetectedContact[])=>void}){
 const [expanded,setExpanded]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[filename,setFilename]=useState(''),[progress,setProgress]=useState(''),[dragging,setDragging]=useState(false);
 const [preview,setPreview]=useState<Preview|null>(null),[text,setText]=useState('');
 const input=useRef<HTMLInputElement>(null),pasteZone=useRef<HTMLDivElement>(null),request=useRef<AbortController|null>(null);
 useEffect(()=>{return()=>request.current?.abort()},[]);
 useEffect(()=>{if(expanded)pasteZone.current?.focus({preventScroll:true})},[expanded]);
 async function recognize(recognizedText:string,controller:AbortController){
  if(controller.signal.aborted)return;
  setProgress('Detecting builders and contacts…');
  // Only text, never screenshot bytes, is submitted to the existing parser.
  const response=await apiFetch('opportunities/contact-screenshot',{method:'POST',body:JSON.stringify({text:recognizedText,knownBuilders:builders.slice(0,2000)}),signal:controller.signal});
  const result=await response.json() as Preview&{error?:string};if(!response.ok)throw Error(result.error||'Unable to recognize contacts.');
  if(!controller.signal.aborted){setPreview(result);setText(result.text)}
 }
 async function run(task:(controller:AbortController)=>Promise<void>){
  if(disabled||request.current)return;
  const controller=new AbortController();request.current=controller;setBusy(true);setError('');setPreview(null);
  try{await task(controller)}catch(e){if(!controller.signal.aborted)setError((e as Error).message)}finally{
   if(request.current===controller){request.current=null;setBusy(false);setProgress('')}
  }
 }
 async function choose(file:File|undefined,label?:string){
  if(!file||disabled||request.current)return;
  const invalid=screenshotError(file);if(invalid){setError(invalid);return}
  setFilename(label||file.name||'Pasted screenshot');setText('');
  await run(async controller=>{
   const recognized=await recognizeScreenshot(file,controller.signal,setProgress);
   if(!controller.signal.aborted){setText(recognized);await recognize(recognized,controller)}
  });
 }
 function cancelRecognition(){const controller=request.current;request.current=null;controller?.abort();setBusy(false);setProgress('');}
 function update(index:number,patch:Partial<DetectedContact>){setPreview(p=>p?{...p,rows:p.rows.map((r,i)=>i===index?{...r,...patch}:r)}:p)}
 function close(){cancelRecognition();setExpanded(false);setDragging(false);setPreview(null);setText('');setFilename('');setError('')}
 function apply(){if(!preview?.rows.length)return;try{for(const row of preview.rows){const message=validateDetectedContact(row);if(message)throw Error(message)}onApply(preview.rows);close()}catch(e){setError((e as Error).message)}}
 return <section className="contact-screenshot-import" aria-label="Import builders from screenshot">
  <button type="button" className="secondary-btn contact-screenshot-trigger" aria-expanded={expanded} disabled={disabled||busy} onClick={()=>expanded?close():setExpanded(true)}><Upload size={16}/>Import screenshot</button>
  {expanded&&<div className="contact-screenshot-panel" onKeyDown={e=>{if(e.key==='Enter'&&(e.target as HTMLElement).tagName==='INPUT')e.preventDefault()}} onPaste={e=>{const file=pastedScreenshot(e.clipboardData);if(file){e.preventDefault();e.stopPropagation();void choose(file,'Pasted screenshot')}}}>
   <div className="contact-screenshot-heading"><strong><ClipboardList size={16}/>Detect builders and contacts</strong><button type="button" className="text-btn" aria-label="Close screenshot import" onClick={close}><X size={16}/></button></div>
   <p className="op-help">Paste or choose a cropped builder/contact screenshot. Recognition runs in your browser; only recognized text is sent to TEC Flow for matching. Nothing is saved until you save the opportunity.</p>
   <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" className="contact-screenshot-file" aria-label="Select builder contact screenshot" disabled={disabled||busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';void choose(file)}}/>
   <div ref={pasteZone} tabIndex={0} className={'contact-screenshot-paste'+(dragging?' is-dragging':'')} aria-label="Paste screenshot here using Control or Command V" onDragOver={e=>{e.preventDefault();if(!disabled&&!busy){e.dataTransfer.dropEffect='copy';setDragging(true)}}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);void choose(pastedScreenshot(e.dataTransfer)||undefined)}}>
    <ClipboardPaste size={24}/><strong>Paste screenshot here</strong><span>Ctrl+V / Cmd+V, or drag and drop an image</span>
    <button type="button" className="secondary-btn" disabled={disabled||busy} onClick={()=>input.current?.click()}><Upload size={15}/>Choose screenshot</button>
    <small>{filename||'PNG, JPEG, WebP · up to 6 MB'}</small>
   </div>
   {busy&&<div className="contact-screenshot-upload"><p role="status">{progress||'Preparing screenshot…'}</p><button type="button" className="secondary-btn" onClick={cancelRecognition}>Cancel recognition</button></div>}
   {error&&<p className="error-banner" role="alert">{error}</p>}
   <details className="contact-screenshot-text" open={!!error&&!preview?true:undefined}><summary>Paste or correct recognized text</summary><textarea value={text} maxLength={24000} rows={5} disabled={busy||disabled} onChange={e=>setText(e.target.value)} placeholder={'Builder name\nPhone number\nContact person\nEmail address'}/><button type="button" className="secondary-btn" disabled={disabled||busy||!text.trim()} onClick={()=>void run(controller=>recognize(text,controller))}>Detect from text</button></details>
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
