/* Account photos are staged locally and saved with the profile, never in a catalogue. */
const profilePhotoState={dataUrl:null,remove:false,reading:false,readId:0,dirty:false,busy:false};
function profileInitials(name){
  const words=String(name||'').trim().split(/\s+/).filter(Boolean);
  if(!words.length)return '?';
  return (Array.from(words[0])[0]+(words.length>1?Array.from(words.at(-1))[0]:'')).toLocaleUpperCase();
}
function profilePhotoURL(user){return `/api/auth/profile/photo?v=${Number(user.avatar_version||0)}`;}
function fillAvatar(element,user,source){
  if(!element)return;
  const initials=profileInitials(user?.name||user?.username);
  element.replaceChildren();
  const fallback=()=>{element.replaceChildren();const span=document.createElement('span');span.className='avatar-initials';span.textContent=initials;span.setAttribute('aria-hidden','true');element.append(span);};
  if(!source){fallback();return;}
  const image=document.createElement('img');image.alt='';image.src=source;
  image.addEventListener('error',fallback,{once:true});element.append(image);
}
function renderAccountAvatar(user){fillAvatar($('#account-avatar'),user,user.has_avatar?profilePhotoURL(user):null);}
function clearProfilePhoto(){
  profilePhotoState.readId++;
  Object.assign(profilePhotoState,{dataUrl:null,remove:false,reading:false,dirty:false,busy:false});
  const input=$('#profile-photo-file');if(input)input.value='';
  if($('#profile-photo-preview'))$('#profile-photo-preview').replaceChildren();
}
function resetProfilePhoto(user){
  clearProfilePhoto();
  renderProfilePhoto();
  $('#profile-photo-status').textContent=user.has_avatar?'Your photo is saved to your account.':'Your name initials are used when no photo is set.';
}
function renderProfilePhoto(){
  const user={...state.user,name:$('#profile-name').value||state.user?.name};
  const source=profilePhotoState.dataUrl||(!profilePhotoState.remove&&user.has_avatar?profilePhotoURL(user):null);
  fillAvatar($('#profile-photo-preview'),user,source);
  $('#profile-remove-photo').disabled=profilePhotoState.busy||(!source&&!profilePhotoState.reading);
}
function readProfilePhoto(file){
  const status=$('#profile-photo-status');if(profilePhotoState.busy||!file)return;
  if(!/^image\/(png|jpeg|webp|gif|bmp)$/.test(file.type)){status.textContent='Choose a PNG, JPG, WebP, GIF or BMP image file.';return;}
  if(!file.size||file.size>8*1024*1024){status.textContent='Choose a non-empty image smaller than 8 MB.';return;}
  const request=++profilePhotoState.readId,userId=state.user?.id;
  profilePhotoState.reading=true;status.textContent='Preparing photo preview...';
  const reader=new FileReader();
  reader.onload=()=>{
    if(request!==profilePhotoState.readId||state.user?.id!==userId)return;
    const image=new Image();
    image.onload=()=>{
      if(request!==profilePhotoState.readId||state.user?.id!==userId)return;
      profilePhotoState.reading=false;
      if(image.naturalWidth*image.naturalHeight>20000000){status.textContent='Use an image with at most 20 megapixels.';return;}
      profilePhotoState.dataUrl=String(reader.result);profilePhotoState.remove=false;profilePhotoState.dirty=true;
      renderProfilePhoto();status.textContent='Photo ready. Select Save profile to apply it.';
    };
    image.onerror=()=>{if(request===profilePhotoState.readId){profilePhotoState.reading=false;status.textContent='The image could not be read. Choose another file.';}};
    image.src=String(reader.result);
  };
  reader.onerror=()=>{if(request===profilePhotoState.readId){profilePhotoState.reading=false;status.textContent='The photo could not be read. Try again.';}};
  reader.readAsDataURL(file);
}
document.addEventListener('DOMContentLoaded',()=>{
  const file=$('#profile-photo-file'),zone=$('#profile-photo-area');
  [$('#profile-photo-ring'),$('#profile-upload-photo')].forEach(button=>button.addEventListener('click',()=>{if(!profilePhotoState.busy)file.click();}));
  file.addEventListener('change',()=>{readProfilePhoto(file.files[0]);file.value='';});
  $('#profile-name').addEventListener('input',renderProfilePhoto);
  $('#profile-remove-photo').addEventListener('click',()=>{
    if(profilePhotoState.busy)return;
    profilePhotoState.readId++;profilePhotoState.reading=false;profilePhotoState.dataUrl=null;profilePhotoState.remove=true;profilePhotoState.dirty=true;
    renderProfilePhoto();$('#profile-photo-status').textContent='Initials will replace your photo when you save your profile.';
  });
  let depth=0;
  zone.addEventListener('dragenter',event=>{event.preventDefault();depth++;if(!profilePhotoState.busy)zone.classList.add('photo-drop-active');});
  zone.addEventListener('dragover',event=>{event.preventDefault();event.dataTransfer.dropEffect=profilePhotoState.busy?'none':'copy';});
  zone.addEventListener('dragleave',()=>{if(--depth<=0){depth=0;zone.classList.remove('photo-drop-active');}});
  zone.addEventListener('drop',event=>{
    event.preventDefault();depth=0;zone.classList.remove('photo-drop-active');
    if(profilePhotoState.busy)return;
    if(event.dataTransfer.files.length!==1){$('#profile-photo-status').textContent='Drop one image file at a time.';return;}
    readProfilePhoto(event.dataTransfer.files[0]);
  });
  document.addEventListener('click',event=>{
    if(event.target.closest('.nav-button,.brand-home')&&state.view==='profile'&&(profilePhotoState.dirty||profilePhotoState.reading)&&!event.ctrlKey&&!event.metaKey){
      if(profilePhotoState.busy||!confirm('Leave without saving your profile photo change?')){event.preventDefault();event.stopImmediatePropagation();}
      else clearProfilePhoto();
    }
  },true);
});
window.addEventListener('beforeunload',event=>{if(profilePhotoState.dirty||profilePhotoState.reading){event.preventDefault();event.returnValue='';}});
