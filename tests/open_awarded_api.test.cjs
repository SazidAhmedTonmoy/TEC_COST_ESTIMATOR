const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('/opt/nvm/versions/node/v22.16.0/lib/node_modules/typescript');
const root=path.resolve(__dirname,'..');
const app=fs.readFileSync(path.join(root,'tenders_frontend/src/components/tender-app.tsx'),'utf8');
const cards=fs.readFileSync(path.join(root,'tenders_frontend/src/components/open-awarded.tsx'),'utf8');
const main=fs.readFileSync(path.join(root,'tenders_frontend/src/main.tsx'),'utf8');
const html=fs.readFileSync(path.join(root,'tenders_frontend/index.html'),'utf8');
function select(rows){
 const src=ts.createSourceFile('open-awarded.tsx',cards,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 assert.deepEqual(src.parseDiagnostics,[]);
 const node=src.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text==='selectOpenAwarded');
 assert.ok(node);
 const compiled=ts.transpileModule(node.getText(src),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
 const context={exports:{}};vm.runInNewContext(compiled.outputText,context);
 return context.exports.selectOpenAwarded(rows);
}
test('only TEC Open and builder Awarded appear, newest recorded award first',()=>{
 const rows=[{id:'a',project:'Old',builder:'A',status:'Open',builderStatus:'Awarded',awardedDate:'2026-06-03'},
 {id:'b',project:'Won',builder:'B',status:'Won',builderStatus:'Awarded',awardedDate:'2026-11-15'},
 {id:'c',project:'New',builder:'C',status:'Open',builderStatus:'Awarded',awardedDate:'2026-11-12'},
 {id:'d',project:'Unknown',builder:'D',status:'Open',builderStatus:'Awarded',awardedDate:''},
 {id:'e',project:'Unsuccessful',builder:'E',status:'Open',builderStatus:'Unsuccessful',awardedDate:'2026-11-16'}];
 assert.deepEqual(Array.from(select(rows),x=>x.id),['c','a','d']);
 assert.equal(rows[0].id,'a','sort must not mutate original array');
});
test('Tender navigation, direct route and detail drawer connect new page',()=>{
 assert.match(app,/\['open-awarded','Open-Awarded',Award\]/);
 assert.match(app,/onOpen=\{s=>open\(s,'history'\)\}/);
 assert.match(app,/post\('open-awarded\/contact'/);
 assert.match(app,/AwardContactList submission=\{chosen\}/);
 assert.match(app,/\'open-awarded\'\]\.includes\(initialView\)/);
 assert.match(main,/location\.pathname\.split\('\/'\)\[2\]/);
 assert.match(html,/href="\/tenders\/open-awarded"/);
});
test('contacts are separate, cards warn for missing fields, phone and Outlook links are direct',()=>{
 assert.match(cards,/awardContacts/);
 assert.match(cards,/AwardContactList submission=\{s\}/);
 const shared=fs.readFileSync(path.join(root,'tenders_frontend/src/components/award-contact-list.tsx'),'utf8');
 assert.match(shared,/person\.phones\.map/);
 assert.match(shared,/person\.emails\.map/);
 assert.match(shared,/oa-contact-warning/);
 assert.match(cards,/oa-date-warning/);
 assert.match(shared,/phoneHref/);
 assert.match(shared,/outlookHref/);
 assert.match(cards,/window\.confirm\('Discard unsaved awarded-project/);
});
