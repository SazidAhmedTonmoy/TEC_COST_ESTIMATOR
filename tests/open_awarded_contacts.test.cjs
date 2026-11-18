const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('/opt/nvm/versions/node/v22.16.0/lib/node_modules/typescript');
const root=path.resolve(__dirname,'..');
function src(p){return fs.readFileSync(path.join(root,p),'utf8')}
function parse(p){const source=src(p);const ast=ts.createSourceFile(p,source,ts.ScriptTarget.Latest,true,p.endsWith('.tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);assert.deepEqual(ast.parseDiagnostics,[],`${p} should parse`);return source}
function loadHelpers(){const code=ts.transpileModule(src('tenders_frontend/src/lib/award-contacts.ts'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;const context={exports:{}};vm.runInNewContext(code,context);return context.exports}
test('new contact list round-trips, searches by all people and phones',()=>{
 const m=loadHelpers();const s={awardContacts:[{name:'Josh Giles',emails:['josh@example.com','j.giles@example.com'],phones:['02 9616 2990','0427 420 103']},{name:'Jane Smith',emails:['jane@example.com'],phones:['0421 222 333']}]};
 assert.equal(JSON.stringify(m.awardedContacts(s)),JSON.stringify(s.awardContacts));
 assert.match(m.searchAwardContacts(s),/Jane Smith/);assert.match(m.searchAwardContacts(s),/0427 420 103/);
 assert.equal(m.missingAwardContact(s),false);
 assert.equal(m.phoneHref('02 9616 2990'),'tel:0296162990');
 assert.equal(m.outlookHref('josh@example.com'),'https://outlook.office.com/mail/deeplink/compose?to=josh%40example.com');
});
test('old one-contact records support combined office/mobile number and email without migration',()=>{
 const m=loadHelpers();const s={awardContactName:'Josh Giles',awardContactPhone:'02 9616 2990  0427 420 103',awardContactEmail:'josh@example.com'};
 assert.equal(JSON.stringify(m.awardedContacts(s)[0].phones),JSON.stringify(['02 9616 2990','0427 420 103']));
 assert.equal(m.missingAwardContact(s),false);
 assert.equal(m.missingAwardContact({awardContacts:[]}),true);
});
test('all three views share multi-contact rendering and the editor has repeatable inputs',()=>{
 const card=parse('tenders_frontend/src/components/open-awarded.tsx');
 const shared=parse('tenders_frontend/src/components/award-contact-list.tsx');
 const drawer=parse('tenders_frontend/src/components/tender-app.tsx');
 const css=src('tenders_frontend/src/components/open-awarded.css');
 assert.equal((card.match(/<AwardContactList submission=\{s\}/g)||[]).length,2,'card and calendar');
 assert.match(drawer,/<AwardContactList submission=\{chosen\}/);
 for(const label of ['Add contact person','Add phone','Add email','Remove person','Save details'])assert.ok(card.includes(label));
 assert.match(card,/onClick=\{\(\)=>removeContactField/);
 assert.match(shared,/person\.phones\.map/);assert.match(shared,/person\.emails\.map/);
 assert.match(css,/oa-contact-editor/);assert.match(css,/oa-contact-entry/);
});
