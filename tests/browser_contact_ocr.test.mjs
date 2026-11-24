import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pastedScreenshot,screenshotError,recognizeScreenshot,MAX_SCREENSHOT_BYTES} from '../tenders_frontend/src/lib/browser-contact-ocr.ts';

const file={type:'image/png',size:100,name:'clipboard.png'};
test('clipboard items and files both support pasted screenshots, ordinary text is ignored',()=>{
 assert.equal(pastedScreenshot({items:[{kind:'file',type:'image/png',getAsFile:()=>file}],files:[]}),file);
 assert.equal(pastedScreenshot({items:[],files:[file]}),file);
 assert.equal(pastedScreenshot({items:[{kind:'string',type:'text/plain'}],files:[]}),null);
 assert.equal(screenshotError(file),'');
 assert.ok(screenshotError({...file,size:MAX_SCREENSHOT_BYTES+1}));
 assert.ok(screenshotError({...file,type:'image/svg+xml'}));
});

function browser(worker,createWorker){
 const old={window:globalThis.window,document:globalThis.document,Worker:globalThis.Worker,createImageBitmap:globalThis.createImageBitmap};
 const canvas={width:0,height:0,getContext:()=>({fillRect(){},drawImage(){},getImageData:()=>({data:new Uint8ClampedArray([255,255,255,255,0,0,0,255])}),putImageData(){}})};
 let closed=false;
 globalThis.Worker=function Worker(){};
 globalThis.createImageBitmap=async()=>({width:20,height:10,close(){closed=true;}});
 globalThis.document={createElement:()=>canvas};
 globalThis.window={location:{origin:'https://tec-flow.example.test'},Tesseract:{createWorker}};
 return {canvas,closed:()=>closed,restore(){for(const [key,value] of Object.entries(old)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}};
}

test('OCR uses local assets, English, bounded image and clears the worker',async()=>{
 let options,parameters,terminated=0;
 const worker={async setParameters(p){parameters=p;},async recognize(image){assert.equal(image.width,60);return {data:{text:'Example Builder\nAlex Example'}};},async terminate(){terminated++;}};
 const env=browser(worker,async(lang,oem,opts)=>{assert.equal(lang,'eng');assert.equal(oem,1);options=opts;return worker;});
 try{
  const result=await recognizeScreenshot(file,new AbortController().signal,()=>{});
  assert.equal(result,'Example Builder\nAlex Example');
  assert.equal(parameters.tessedit_pageseg_mode,'6');
  assert.equal(options.workerPath,'https://tec-flow.example.test/tenders/assets/ocr-v6.0.1/worker.min.js');
  assert.equal(options.corePath,'https://tec-flow.example.test/tenders/assets/ocr-v6.0.1');
  assert.equal(options.langPath,options.corePath);assert.equal(options.workerBlobURL,false);
  assert.equal(terminated,1);assert.equal(env.canvas.width,0);assert.equal(env.closed(),true);
 }finally{env.restore()}
});

test('cancelled recognition terminates an active OCR worker and clears the canvas',async()=>{
 const controller=new AbortController();let terminate=0;
 const worker={async setParameters(){},recognize(){controller.abort();return new Promise(()=>{});},async terminate(){terminate++;}};
 const env=browser(worker,async()=>worker);
 try{await assert.rejects(recognizeScreenshot(file,controller.signal,()=>{}),{name:'AbortError'});assert.equal(terminate,1);assert.equal(env.canvas.width,0);}
 finally{env.restore()}
});

test('closing during engine initialization terminates the worker when it becomes ready',async()=>{
 const controller=new AbortController();let resolveWorker,started,terminate=0;
 const worker={async terminate(){terminate++;}};
 const entered=new Promise(resolve=>{started=resolve;});
 const env=browser(worker,()=>new Promise(resolve=>{resolveWorker=resolve;started();}));
 try{
  const work=recognizeScreenshot(file,controller.signal,()=>{});await entered;controller.abort();await assert.rejects(work,{name:'AbortError'});
  resolveWorker(worker);await new Promise(resolve=>setImmediate(resolve));assert.equal(terminate,1);
 }finally{env.restore()}
});

test('import has a focusable paste/drop area and submits text only',()=>{
 const source=readFileSync(new URL('../tenders_frontend/src/components/contact-screenshot-import.tsx',import.meta.url),'utf8');
 assert.match(source,/Paste screenshot here/);assert.match(source,/onPaste=\{/);assert.match(source,/onDrop=\{/);assert.match(source,/tabIndex=\{0\}/);
 assert.match(source,/recognizeScreenshot\(file,controller.signal/);assert.match(source,/JSON.stringify\(\{text:recognizedText,knownBuilders:/);
 assert.doesNotMatch(source,/readAsDataURL|JSON.stringify\(\{content:/);
});
