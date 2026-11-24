/** Browser-only OCR: the input image never leaves the device. The application
 * posts the resulting text to its existing authenticated contact parser. */
const assetRoot='/tenders/assets/ocr-v6.0.1';
const MAX_PIXELS=12_000_000;
const MAX_TEXT=24_000;
export const MAX_SCREENSHOT_BYTES=6*1024*1024;
const supportedTypes=new Set(['image/png','image/jpeg','image/webp']);
export function screenshotError(file:Pick<File,'type'|'size'>):string{
 if(!supportedTypes.has(file.type))return 'Choose a PNG, JPEG or WebP screenshot.';
 if(file.size<=0||file.size>MAX_SCREENSHOT_BYTES)return 'Crop the screenshot to the contact list or choose an image under 6 MB.';
 return '';
}
export function pastedScreenshot(data:Pick<DataTransfer,'files'|'items'>):File|null{
 // Some browsers expose a pasted screenshot only via ClipboardItem.getAsFile.
 for(const item of Array.from(data.items||[])){
  if(item.kind==='file'&&item.type.startsWith('image/')){const file=item.getAsFile();if(file)return file;}
 }
 return Array.from(data.files||[]).find(file=>file.type.startsWith('image/'))||null;
}
type OCRWorker={setParameters:(parameters:Record<string,string>)=>Promise<unknown>;recognize:(image:HTMLCanvasElement)=>Promise<{data:{text:string}}>;terminate:()=>Promise<unknown>};
type Engine={createWorker:(lang:string,oem:number,options:Record<string,unknown>)=>Promise<OCRWorker>};
type OCRWindow=Window&{Tesseract?:Engine};
let enginePromise:Promise<Engine>|null=null;
function loadEngine():Promise<Engine>{
 if(enginePromise)return enginePromise;
 const engine=(window as OCRWindow).Tesseract;
 if(engine?.createWorker)return Promise.resolve(engine);
 enginePromise=new Promise<Engine>((resolve,reject)=>{
  const script=document.createElement('script');script.src=`${assetRoot}/tesseract.min.js`;script.async=true;
  const fail=()=>{script.remove();reject(Error('Browser recognition could not load. Please retry, or use Detect from text.'));};
  script.onload=()=>{const loaded=(window as OCRWindow).Tesseract;if(loaded?.createWorker)resolve(loaded);else fail();};
  script.onerror=fail;document.head.append(script);
 }).catch(error=>{enginePromise=null;throw error;});
 return enginePromise;
}
async function prepareImage(file:File):Promise<HTMLCanvasElement>{
 const bitmap=await createImageBitmap(file);
 try{
  if(!bitmap.width||!bitmap.height||bitmap.width*bitmap.height>MAX_PIXELS)throw Error('Screenshot is too large. Crop it to the builder/contact list.');
  const scale=Math.min(3,2400/Math.max(bitmap.width,bitmap.height));
  const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));
  const context=canvas.getContext('2d',{willReadFrequently:true});if(!context)throw Error('Image processing is unavailable in this browser.');
  context.fillStyle='#ffffff';context.fillRect(0,0,canvas.width,canvas.height);context.imageSmoothingQuality='high';context.drawImage(bitmap,0,0,canvas.width,canvas.height);
  // Grayscale and stretch contrast, matching the small-screenshot server OCR.
  const pixels=context.getImageData(0,0,canvas.width,canvas.height),data=pixels.data;let low=255,high=0;
  for(let i=0;i<data.length;i+=4){const value=Math.round(.299*data[i]+.587*data[i+1]+.114*data[i+2]);data[i]=data[i+1]=data[i+2]=value;low=Math.min(low,value);high=Math.max(high,value);}
  if(high>low)for(let i=0;i<data.length;i+=4){const value=Math.round((data[i]-low)*255/(high-low));data[i]=data[i+1]=data[i+2]=value;}
  context.putImageData(pixels,0,0);return canvas;
 }finally{bitmap.close();}
}
export async function recognizeScreenshot(file:File,signal:AbortSignal,onProgress:(message:string)=>void):Promise<string>{
 const invalid=screenshotError(file);if(invalid)throw Error(invalid);
 if(typeof Worker==='undefined'||typeof WebAssembly==='undefined'||typeof createImageBitmap==='undefined')throw Error('This browser does not support image recognition. Use an up-to-date browser or Detect from text.');
 let worker:OCRWorker|undefined,canvas:HTMLCanvasElement|undefined,stopped=false;
 let timer:ReturnType<typeof setTimeout>|undefined,abort:()=>void=()=>{};
 let rejectWorker:(error:Error)=>void=()=>{};
 const cancelled=new Promise<never>((_,reject)=>{
  rejectWorker=reject;
  abort=()=>reject(new DOMException('Recognition cancelled.','AbortError'));
  if(signal.aborted)abort();else signal.addEventListener('abort',abort,{once:true});
  timer=setTimeout(()=>reject(Error('Image recognition timed out. Try a smaller cropped screenshot or Detect from text.')),90000);
 });
 const check=()=>{if(stopped||signal.aborted)throw new DOMException('Recognition cancelled.','AbortError');};
 const progress=(message:string)=>{if(!stopped&&!signal.aborted)onProgress(message);};
 const work=async()=>{
  check();progress('Preparing screenshot…');const image=await prepareImage(file);
  if(stopped||signal.aborted){image.width=image.height=0;check();}canvas=image;
  progress('Loading private recognition engine…');const engine=await loadEngine();check();
  const base=new URL(assetRoot+'/',window.location.origin).href;
  const instance=await engine.createWorker('eng',1,{
   workerPath:base+'worker.min.js',corePath:base.slice(0,-1),langPath:base.slice(0,-1),
   workerBlobURL:false,legacyCore:false,legacyLang:false,gzip:true,cacheMethod:'none',
   logger:(event:{status?:string;progress?:number})=>{if(event.status==='recognizing text')progress(`Recognizing text… ${Math.round((event.progress||0)*100)}%`);},
   errorHandler:()=>rejectWorker(Error('Browser recognition could not finish. Retry or use Detect from text.')),
  });
  if(stopped||signal.aborted){await instance.terminate();check();}worker=instance;
  await worker.setParameters({tessedit_pageseg_mode:'6'});check();
  progress('Recognizing text…');const result=await worker.recognize(image);check();
  const text=result.data.text.trim();if(!text)throw Error('No text was recognized. Try a clearer cropped screenshot or Detect from text.');
  return text.slice(0,MAX_TEXT);
 };
 try{return await Promise.race([cancelled,work()]);}
 finally{stopped=true;clearTimeout(timer);signal.removeEventListener('abort',abort);if(worker)await worker.terminate().catch(()=>{});if(canvas)canvas.width=canvas.height=0;}
}
