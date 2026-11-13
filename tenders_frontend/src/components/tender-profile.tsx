'use client';
import {useEffect,useRef,useState,type FormEvent} from 'react';
import {Camera,CheckCircle2,Eye,EyeOff,Save} from 'lucide-react';
import {request} from '../lib/request';
import {session} from '../main';
import '../tender-profile.css';

type ProfileUser={
 id:number;name:string;username:string;job_title:string;email?:string;contact_number?:string;
 role:string;has_avatar?:boolean;avatar_version?:number;preferred_homepage?:string;
 homepage?:string;must_change_password?:boolean;
};
type Fields={name:string;username:string;job_title:string;email:string;contact_number:string;homepage:string};
const fields=(user:ProfileUser):Fields=>({
 name:user.name||'',username:user.username||'',job_title:user.job_title||'',
 email:user.email||'',contact_number:user.contact_number||'',homepage:user.preferred_homepage||'auto'
});
const initials=(name:string)=>name.trim().split(/\s+/).filter(Boolean).filter((_,index,all)=>index===0||index===all.length-1).map(part=>part[0]).join('').toUpperCase()||'?';

export default function TenderProfile({user,onUpdated,onDirtyChange}:{
 user:ProfileUser;onUpdated:(user:ProfileUser)=>void;onDirtyChange:(dirty:boolean)=>void;
}){
 const baseline=useRef(JSON.stringify(fields(user)));
 const [form,setForm]=useState<Fields>(()=>fields(user));
 const [currentPassword,setCurrentPassword]=useState('');
 const [newPassword,setNewPassword]=useState('');
 const [confirmPassword,setConfirmPassword]=useState('');
 const [showPasswords,setShowPasswords]=useState(false);
 const [photoData,setPhotoData]=useState<string|null>(null);
 const [removePhoto,setRemovePhoto]=useState(false);
 const [reading,setReading]=useState(false);
 const [saving,setSaving]=useState(false);
 const [error,setError]=useState('');
 const [success,setSuccess]=useState('');
 const photoInput=useRef<HTMLInputElement>(null);
 const dirty=JSON.stringify(form)!==baseline.current||!!(currentPassword||newPassword||confirmPassword||photoData||removePhoto);
 useEffect(()=>{onDirtyChange(dirty||reading||saving);},[dirty,reading,saving,onDirtyChange]);
 const dirtyChangeRef=useRef(onDirtyChange);dirtyChangeRef.current=onDirtyChange;
 useEffect(()=>()=>dirtyChangeRef.current(false),[]);
 useEffect(()=>{
  const guard=(event:BeforeUnloadEvent)=>{
   if(dirty||reading||saving){event.preventDefault();event.returnValue='';}
  };
  window.addEventListener('beforeunload',guard);
  return()=>{window.removeEventListener('beforeunload',guard);};
 },[dirty,reading,saving]);
 const change=(key:keyof Fields,value:string)=>{setForm(previous=>({...previous,[key]:value}));setSuccess('');};
 function choosePhoto(file?:File){
  if(!file)return;
  setSuccess('');setError('');
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)){
   setError('Choose a JPG, PNG or WebP profile photo.');return;
  }
  if(file.size>8*1024*1024){setError('Choose a photo smaller than 8 MB.');return;}
  const reader=new FileReader();setReading(true);
  reader.onload=()=>{setPhotoData(String(reader.result||''));setRemovePhoto(false);setReading(false);};
  reader.onerror=()=>{setReading(false);setError('Could not read that image. Choose another photo.');};
  reader.readAsDataURL(file);
 }
 async function save(event:FormEvent<HTMLFormElement>){
  event.preventDefault();if(saving||reading)return;
  setError('');setSuccess('');
  if(newPassword!==confirmPassword){setError('The new passwords do not match.');return;}
  setSaving(true);
  try{
   const payload:Record<string,unknown>={...form,current_password:currentPassword,password:newPassword};
   if(photoData)payload.photo_data_url=photoData;
   else if(removePhoto)payload.remove_photo=true;
   const response=await request('/api/auth/profile',{
    method:'PATCH',headers:{'Content-Type':'application/json','X-ConEst-Request':'1','X-CSRF-Token':session.csrf},
    body:JSON.stringify(payload)
   });
   if(response.status===401){location.replace('/?return=tenders');return;}
   const result=await response.json();
   if(!response.ok||!result.success)throw Error(result.error||'Could not save profile.');
   // Profile updates rotate the session on the server. Keep CSRF in sync so
   // Opportunity and Tender actions continue to work without a reload.
   session.user=result.user;session.csrf=result.csrf_token;
   const updated=fields(result.user);baseline.current=JSON.stringify(updated);setForm(updated);
   setCurrentPassword('');setNewPassword('');setConfirmPassword('');
   setPhotoData(null);setRemovePhoto(false);
   if(photoInput.current)photoInput.current.value='';
   onUpdated(result.user);onDirtyChange(false);
   setSuccess('Profile saved. Your Tender workspace stays open.');
  }catch(e){setError((e as Error).message||'Unable to confirm the save. Check your profile before trying again.');}
  finally{setSaving(false);}
 }
 const photo=photoData||(!removePhoto&&user.has_avatar?`/api/auth/profile/photo?v=${Number(user.avatar_version||0)}`:'');
 return <section className="tender-profile" aria-label="My Profile">
  <div className="panel tender-profile-panel">
   <div className="tender-profile-heading"><span className="tender-profile-eyebrow">YOUR ACCOUNT</span><h2>My Profile</h2><p>Update your details and choose your preferred starting workspace.</p></div>
   <form onSubmit={save}>
    <div className="tender-profile-photo-area">
     <div className="tender-profile-photo" aria-label="Profile photo">
      {photo?<img src={photo} alt="Your profile"/>:<span>{initials(form.name||form.username)}</span>}
      <button type="button" title="Change profile photo" aria-label="Change profile photo" disabled={saving||reading} onClick={()=>photoInput.current?.click()}><Camera size={16}/></button>
     </div>
     <strong>Profile photo</strong>
     <div className="tender-profile-photo-actions">
      <button type="button" className="secondary-btn" disabled={saving||reading} onClick={()=>photoInput.current?.click()}>Upload / change photo</button>
      <button type="button" className="secondary-btn" disabled={saving||reading||!photo} onClick={()=>{setPhotoData(null);setRemovePhoto(true);setSuccess('');}}>Use initials</button>
     </div>
     <input ref={photoInput} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Choose profile photo" className="tender-profile-file" onChange={e=>choosePhoto(e.target.files?.[0])}/>
     {reading&&<span className="tender-profile-hint" role="status">Reading photo…</span>}
    </div>
    <div className="tender-profile-grid">
     <label>Name<input required maxLength={120} autoComplete="name" value={form.name} onChange={e=>change('name',e.target.value)}/></label>
     <label>Username<input required minLength={3} maxLength={64} autoComplete="username" value={form.username} onChange={e=>change('username',e.target.value)}/></label>
     <label>Job title<input maxLength={120} value={form.job_title} onChange={e=>change('job_title',e.target.value)}/></label>
     <label>Email <span>(optional)</span><input type="email" maxLength={254} autoComplete="email" value={form.email} onChange={e=>change('email',e.target.value)}/></label>
     <label>Contact no. <span>(optional)</span><input type="tel" maxLength={50} autoComplete="tel" value={form.contact_number} onChange={e=>change('contact_number',e.target.value)}/></label>
     <label>Role<input readOnly disabled value={user.role==='admin'?'Admin':'User'}/></label>
     <label>My homepage<select value={form.homepage} onChange={e=>change('homepage',e.target.value)}><option value="auto">Use role / team default</option><option value="estimator">Estimator</option><option value="tenders">Tenders</option></select><span className="tender-profile-hint">Auto currently opens {user.homepage==='tenders'?'Tenders':'Estimator'}. Your selection applies the next time you open TEC ConEst.</span></label>
    </div>
    <fieldset className="tender-profile-password"><legend>Password &amp; Security</legend>
     <div className="tender-profile-grid">
      <label>Current password<div className="tender-profile-password-input"><input type={showPasswords?'text':'password'} autoComplete="current-password" value={currentPassword} onChange={e=>{setCurrentPassword(e.target.value);setSuccess('');}}/><button type="button" aria-label={showPasswords?'Hide passwords':'Show passwords'} onClick={()=>setShowPasswords(!showPasswords)}>{showPasswords?<EyeOff size={16}/>:<Eye size={16}/>}</button></div></label>
      <label>New password<input type={showPasswords?'text':'password'} autoComplete="new-password" minLength={newPassword?8:undefined} value={newPassword} onChange={e=>{setNewPassword(e.target.value);setSuccess('');}}/></label>
      <label>Confirm new password<input type={showPasswords?'text':'password'} autoComplete="new-password" value={confirmPassword} onChange={e=>{setConfirmPassword(e.target.value);setSuccess('');}}/></label>
     </div>
     <p className="tender-profile-hint">Enter your current password when changing your username or password. Password changes sign out your other sessions.</p>
    </fieldset>
    {error&&<div className="tender-profile-error" role="alert">{error}</div>}
    {success&&<div className="tender-profile-success" role="status"><CheckCircle2 size={17}/>{success}</div>}
    <div className="tender-profile-actions"><button className="primary-btn" type="submit" disabled={saving||reading}><Save size={16}/>{saving?'Saving…':'Save profile'}</button></div>
   </form>
  </div>
 </section>;
}
