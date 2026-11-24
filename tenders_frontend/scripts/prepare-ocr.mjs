// Fetch only the pinned browser distribution, matching WASM core and English
// language assets at build time. No package lifecycle scripts are executed.
// Production never downloads code from a third-party CDN.
import {execFileSync} from 'node:child_process';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,renameSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const frontend=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const output=join(frontend,'public','assets','ocr-v6.0.1');
const packages=[
 {name:'tesseract.js',version:'6.0.1',files:{'dist/tesseract.min.js':'tesseract.min.js','dist/worker.min.js':'worker.min.js','LICENSE.md':'tesseract-LICENSE.txt','dist/tesseract.min.js.LICENSE.txt':'tesseract.min.js.LICENSE.txt','dist/worker.min.js.LICENSE.txt':'worker.min.js.LICENSE.txt'}},
 {name:'tesseract.js-core',version:'6.0.0',files:{'tesseract-core-lstm.wasm.js':'tesseract-core-lstm.wasm.js','tesseract-core-simd-lstm.wasm.js':'tesseract-core-simd-lstm.wasm.js','tesseract-core-lstm.wasm':'tesseract-core-lstm.wasm','tesseract-core-simd-lstm.wasm':'tesseract-core-simd-lstm.wasm','LICENSE':'core-LICENSE.txt'}},
 {name:'@tesseract.js-data/eng',version:'1.0.0',files:{'4.0.0_best_int/eng.traineddata.gz':'eng.traineddata.gz'}},
];
const temp=mkdtempSync(join(tmpdir(),'tec-flow-ocr-'));
const stage=join(output,'..','.ocr-v6.0.1-stage');
try{
 rmSync(stage,{recursive:true,force:true});mkdirSync(stage,{recursive:true});
 // npm verifies each tarball against the registry's integrity metadata. Only
 // named files are extracted, so package archive paths cannot escape staging.
 for(const pkg of packages){
  const spec=`${pkg.name}@${pkg.version}`;
  const npm=process.env.npm_execpath;
  const args=['pack',spec,'--ignore-scripts','--json','--registry=https://registry.npmjs.org','--pack-destination',temp,'--fetch-retries=1','--fetch-timeout=60000'];
  const packed=JSON.parse(execFileSync(npm?process.execPath:'npm',npm?[npm,...args]:args,{cwd:temp,encoding:'utf8',timeout:120000}))[0];
  if(packed.name!==pkg.name||packed.version!==pkg.version||!packed.integrity||!/^[-a-zA-Z0-9_.]+\.tgz$/.test(packed.filename))throw Error(`Unexpected npm package: ${spec}`);
  for(const [source,dest] of Object.entries(pkg.files)){
   const data=execFileSync('tar',['-xOf',join(temp,packed.filename),`package/${source}`],{maxBuffer:20*1024*1024,timeout:30000});
   if(!data.length)throw Error(`Missing OCR asset: ${source}`);
   writeFileSync(join(stage,dest),data);
  }
 }
 const language=readFileSync(join(stage,'eng.traineddata.gz'));
 if(language[0]!==0x1f||language[1]!==0x8b)throw Error('Invalid English OCR model.');
 for(const name of ['tesseract-core-lstm.wasm','tesseract-core-simd-lstm.wasm']){
  const magic=readFileSync(join(stage,name)).subarray(0,4);
  if(!magic.equals(Buffer.from([0,97,115,109])))throw Error(`Invalid WebAssembly asset: ${name}`);
 }
 // English model upstream uses the Apache-2.0 license (same text as the core).
 writeFileSync(join(stage,'NOTICE.txt'),'Tesseract.js 6.0.1, Tesseract.js-core 6.0.0, and @tesseract.js-data/eng 1.0.0 (4.0.0_best_int). Apache-2.0. See included licenses.\n');
 rmSync(output,{recursive:true,force:true});renameSync(stage,output);
 console.log('Prepared same-origin browser OCR assets.');
}finally{rmSync(temp,{recursive:true,force:true});rmSync(stage,{recursive:true,force:true});}
