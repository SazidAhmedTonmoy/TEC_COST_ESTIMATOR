const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('../tenders_frontend/node_modules/typescript');
const source=fs.readFileSync(new URL('../tenders_frontend/src/components/open-awarded.tsx',`file://${__filename}`),'utf8');
const filename='open-awarded.tsx';
const tree=ts.createSourceFile(filename,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
const wanted=new Set(['isoDate','awardCalendarEvents','awardMonthCells','sydneyCalendarDate']);
const parts=tree.statements.filter(node=>{
 if(ts.isFunctionDeclaration(node))return wanted.has(node.name?.text);
 if(ts.isVariableStatement(node))return node.declarationList.declarations.some(dec=>wanted.has(dec.name.getText(tree)));
 return false;
}).map(node=>node.getText(tree));
const compiled=ts.transpileModule(parts.join('\n'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}});
const sandbox={exports:{},Date,RegExp,String,Array,Number}; vm.runInNewContext(compiled.outputText,sandbox);const calendar=sandbox.exports;

test('calendar splits awarded and estimated start events without using submission deadlines',()=>{
 const {awardCalendarEvents}=calendar;
 const rows=[{id:'a',project:'Building A',builder:'Builder A',awardedDate:'2026-11-05',estStartDate:'2026-11-16',due:'2026-12-01'},
 {id:'b',project:'Building B',builder:'Builder B',awardedDate:'',estStartDate:'2026-11-16',due:'2026-11-10'},
 {id:'c',project:'Building C',builder:'Builder C',awardedDate:'2026-02-30',estStartDate:'',due:'2026-11-08'}];
 const events=awardCalendarEvents(rows).map(v=>({id:v.submission.id,date:v.date,kind:v.kind}));
 assert.deepEqual(JSON.parse(JSON.stringify(events)),[
  {id:'a',date:'2026-11-05',kind:'awarded'},
  {id:'a',date:'2026-11-16',kind:'start'},
  {id:'b',date:'2026-11-16',kind:'start'},
 ]);
});

test('monthly calendar starts Monday, includes month end and pads leading/trailing dates',()=>{
 const cells=calendar.awardMonthCells('2026-11');
 assert.equal(cells.length,42);
 assert.equal(cells[0],null);
 assert.equal(cells[6],'2026-11-01');
 assert.equal(cells[35],'2026-11-30');
 assert.equal(cells[36],null);
 assert.equal(calendar.awardMonthCells('2026-13').length,0);
 const leap=calendar.awardMonthCells('2028-02');
 assert.ok(leap.includes('2028-02-29'));
});

test('today date follows Sydney calendar day at UTC day boundary',()=>{
 assert.equal(calendar.sydneyCalendarDate(new Date('2026-11-17T14:00:00Z')),'2026-11-18');
 assert.equal(calendar.sydneyCalendarDate(new Date('2026-11-17T11:00:00Z')),'2026-11-17');
 assert.equal(calendar.sydneyCalendarDate(new Date('2026-07-31T14:30:00Z')),'2026-08-01');
});
