/* Select a dropped file; the existing preview/import button confirms submission. */
function bindFileDrop(zone,input,extensions,maxBytes,status){
  let depth=0;
  function message(text){status.textContent=text;status.classList.remove('hidden');}
  zone.addEventListener('dragenter',event=>{event.preventDefault();depth++;zone.classList.add('drop-active');});
  zone.addEventListener('dragover',event=>{event.preventDefault();event.dataTransfer.dropEffect='copy';});
  zone.addEventListener('dragleave',()=>{if(--depth<=0){depth=0;zone.classList.remove('drop-active');}});
  zone.addEventListener('drop',event=>{
    event.preventDefault();depth=0;zone.classList.remove('drop-active');
    const files=event.dataTransfer.files;
    if(files.length!==1){message('Drop one file at a time.');return;}
    const file=files[0],ext=file.name.toLowerCase().split('.').pop();
    if(!extensions.includes(ext)){message('Choose a '+extensions.join(' or ').toUpperCase()+' file.');return;}
    if(file.size>maxBytes){message('This file exceeds the '+Math.round(maxBytes/1024/1024)+' MB limit.');return;}
    if(input.disabled){message('File selection is currently unavailable.');return;}
    const transfer=new DataTransfer();transfer.items.add(file);input.files=transfer.files;
    input.dispatchEvent(new Event('change',{bubbles:true}));
    message(file.name+' selected. Use the button below to continue.');
  });
}
document.addEventListener('DOMContentLoaded',()=>{
  bindFileDrop(document.querySelector('#drop-zone'),document.querySelector('#import-file'),['xlsx','xlsm'],80*1024*1024,document.querySelector('#import-progress'));
  bindFileDrop(document.querySelector('.light-upload-file'),document.querySelector('#light-price-file'),['xlsx','pdf'],30*1024*1024,document.querySelector('#light-price-import-status'));
});
