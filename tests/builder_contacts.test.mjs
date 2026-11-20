import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {runInNewContext} from 'node:vm';
import * as contactHelpers from '../tenders_frontend/src/lib/builder-contacts.ts';
const {builderKey,cloneBuilderContacts,contactPhoneKey,contactsForBuilder,matchSavedContact,replaceBuilderContacts,selectSavedContact,builderContactSearchText,matchesBuilderContactQuery}=contactHelpers;

function submissionHelpers(){
  const require=createRequire(new URL('../tenders_frontend/package.json',import.meta.url));
  const ts=require('typescript'),exports={};
  const code=ts.transpileModule(readFileSync(new URL('../tenders_frontend/src/lib/submission-contacts.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  runInNewContext(code,{exports,require:name=>{assert.equal(name,'./builder-contacts');return contactHelpers}});
  return exports;
}

const blank=()=>({name:'',emails:[],phones:[]});
const matthew={id:'person-1',revision:4,name:'Matthew Wilson',emails:['matthew@example.com','m.wilson@example.com'],phones:['0426 267 296','02 9000 1234']};

test('builder selections retain identity and revision without changing source contact arrays',()=>{
  const groups=[{builder:'Builder Pty Ltd',contacts:[matthew]},{builder:'Other Builder',contacts:[{...matthew,id:'person-other'}]}];
  assert.equal(builderKey('  Builder Pty. Ltd  '),builderKey('Builder Pty Ltd'));
  assert.equal(contactsForBuilder(groups,'Builder Pty. Ltd')[0].id,'person-1');
  const copied=cloneBuilderContacts(contactsForBuilder(groups,'Builder Pty Ltd'));
  assert.equal(copied[0].revision,4);copied[0].emails.push('new@example.com');
  assert.equal(matthew.emails.length,2);
  const removed=replaceBuilderContacts(groups,'Builder Pty Ltd',[]);
  assert.equal(contactsForBuilder(removed,'Builder Pty Ltd').length,0);
  assert.equal(contactsForBuilder(removed,'Other Builder').length,1);
  assert.equal(groups[0].contacts.length,1,'removal from a project must not mutate the shared directory');
});

test('unique exact name, email and equivalent phone autofill every saved detail',()=>{
  const byName=matchSavedContact({...blank(),name:'matthew wilson'},[matthew],'name','matthew wilson');
  assert.equal(byName.id,'person-1');assert.equal(byName.revision,4);assert.deepEqual(byName.phones,matthew.phones);assert.deepEqual(byName.emails,matthew.emails);
  const byEmail=matchSavedContact({...blank(),emails:['MATTHEW@example.com']},[matthew],'email','MATTHEW@example.com');
  assert.equal(byEmail.name,'Matthew Wilson');assert.equal(byEmail.emails.length,2);assert.equal(byEmail.emails[0],'MATTHEW@example.com');
  const byPhone=matchSavedContact({...blank(),phones:['+61 426 267 296']},[matthew],'phone','+61 426 267 296');
  assert.equal(byPhone.id,'person-1');assert.equal(byPhone.phones.length,2);assert.equal(byPhone.phones[0],'+61 426 267 296');
  assert.equal(contactPhoneKey('0061 426 267 296'),contactPhoneKey('0426 267 296'));
  assert.equal(contactPhoneKey('0061 123'),'0061123','short legacy values are not rewritten as Australian international numbers');
});

test('partial names, shared numbers and same-name people do not guess a person',()=>{
  const another={id:'person-2',revision:1,name:'Matthew Wilson',emails:['other@example.com'],phones:['02 9000 1234']};
  assert.equal(matchSavedContact({...blank(),name:'Matt'},[matthew],'name','Matt'),null);
  assert.equal(matchSavedContact({...blank(),name:'Matthew Wilson'},[matthew,another],'name','Matthew Wilson'),null);
  assert.equal(matchSavedContact({...blank(),phones:['02 9000 1234']},[matthew,another],'phone','02 9000 1234'),null);
  assert.equal(matchSavedContact({...blank(),emails:['other@example.com']},[matthew,another],'email','other@example.com').id,'person-2');
});

test('autofill never replaces conflicting typed details or reverts edits to a saved person',()=>{
  assert.equal(matchSavedContact({...blank(),name:'Jane Smith',emails:['matthew@example.com']},[matthew],'email','matthew@example.com'),null);
  assert.equal(matchSavedContact({...blank(),name:'Matthew Wilson',emails:['someone-else@example.com']},[matthew],'name','Matthew Wilson'),null);
  assert.equal(matchSavedContact({...blank(),name:'Matthew Wilson',phones:['0400 123 456']},[matthew],'name','Matthew Wilson'),null);
  assert.equal(matchSavedContact({...matthew,name:'Matthew New Name'},[matthew],'email','matthew@example.com'),null);
  assert.equal(matchSavedContact(blank(),[matthew],'name',''),null);
});

test('lookup receives only the chosen builder contacts',()=>{
  const other={...matthew,id:'other-person',emails:['other@example.com']};
  const directory=[{builder:'Builder A',contacts:[matthew]},{builder:'Builder B',contacts:[other]}];
  const scoped=contactsForBuilder(directory,'Builder B');
  assert.equal(matchSavedContact({...blank(),name:'Matthew Wilson'},scoped,'name','Matthew Wilson').id,'other-person');
  assert.equal(matchSavedContact({...blank(),emails:['matthew@example.com']},scoped,'email','matthew@example.com'),null);
});

test('explicit selection resolves an ambiguous draft without adding a duplicate person',()=>{
  const one={id:'alex-1',revision:1,name:'Alex Smith',emails:['one@example.com'],phones:['0400 111 111']};
  const two={id:'alex-2',revision:2,name:'Alex Smith',emails:['two@example.com'],phones:['0400 222 222']};
  const draft={name:'Alex Smith',emails:[],phones:[]};
  assert.equal(matchSavedContact(draft,[one,two],'name',draft.name),null);
  const selected=selectSavedContact([matthew,draft],two);
  assert.equal(selected.length,2);assert.equal(selected[1].id,'alex-2');assert.equal(selected[1].revision,2);
  assert.deepEqual(selected[1].emails,['two@example.com']);assert.equal(draft.id,undefined);
  assert.equal(selectSavedContact(selected,two).length,2,'already selected person cannot be duplicated');
});

test('selecting a saved contact fills an empty row and respects one-person directory editing',()=>{
  const selected=selectSavedContact([blank()],matthew,1);
  assert.equal(selected.length,1);assert.equal(selected[0].id,'person-1');
  assert.equal(selectSavedContact([{name:'Another person',emails:[],phones:[]}],matthew,1),null,'a conflicting typed person must not be overwritten');
  assert.equal(selectSavedContact([],matthew,1).length,1);
});

test('shared directory search finds names, builder names and email words case-insensitively',()=>{
  for(const query of ['','  ','MATTHEW','Wilson builder','m.wilson@example.com','Builder Pty Ltd Matthew'])assert.equal(matchesBuilderContactQuery('Builder Pty Ltd',[matthew],query),true,query);
  for(const query of ['Unrelated Builder','Jane','wilson nonexistent@example.com'])assert.equal(matchesBuilderContactQuery('Builder Pty Ltd',[matthew],query),false,query);
});

test('contact phone searches match domestic, international and formatting variants',()=>{
  for(const query of ['0426267296','0426 267 296','(0426) 267-296','+61426267296','+61 426 267 296','0061426267296','0061 426 267 296','Matthew +61 (426) 267-296','(02)9000-1234','02 9000 1234'])assert.equal(matchesBuilderContactQuery('Builder Pty Ltd',[matthew],query),true,query);
  for(const query of ['0426267297','+61 426 267 297','02 9000 1235'])assert.equal(matchesBuilderContactQuery('Builder Pty Ltd',[matthew],query),false,query);
  const overseasFormat={...matthew,phones:['+61 426 267 296']};
  assert.equal(matchesBuilderContactQuery('Builder',[overseasFormat],'0426267296'),true);
  const index=builderContactSearchText('Builder',[matthew]);
  assert.ok(index.includes('0426267296'));assert.ok(index.includes('61426267296'));
});

test('phone queries do not combine pieces from different people and preserve numeric company names',()=>{
  const contacts=[{name:'Person One',emails:[],phones:['0426 111 222']},{name:'Person Two',emails:[],phones:['0410 267 296']}];
  assert.equal(matchesBuilderContactQuery('Builder',contacts,'0426 267 296'),false);
  assert.equal(matchesBuilderContactQuery('Builder',contacts,'Person 0426 111'),true);
  assert.equal(matchesBuilderContactQuery('24 7 Electrical',contacts,'24 7 Electrical'),true);
});

test('restoring the original builder after typing a temporary typo keeps contact identity and revisions',()=>{
  const {contactsForSubmissionBuilder}=submissionHelpers();
  const edited={...matthew,phones:['0426 267 296'],emails:[...matthew.emails]};
  const source=JSON.stringify(edited);
  // The draft retains IDs during typing; only this final builder value is submitted.
  const result=contactsForSubmissionBuilder([edited],'Builder Pty. Ltd',[],'Builder Pty Ltd',[matthew]);
  assert.equal(result[0].id,'person-1');assert.equal(result[0].revision,4);assert.equal(result[0].phones.length,1);
  result[0].emails.push('another@example.com');assert.equal(JSON.stringify(edited),source);
});

test('moving to another builder detaches only the old company people and retains target selections',()=>{
  const {contactsForSubmissionBuilder}=submissionHelpers();
  const targetPerson={id:'target-person',revision:6,name:'Target Contact',emails:['target@example.com'],phones:['0400 987 654']};
  const added={name:'New Person',emails:[],phones:[]};
  const contacts=[matthew,targetPerson,added],snapshot=JSON.stringify(contacts);
  const directory=[{builder:'Original Builder',contacts:[matthew]},{builder:'Target Builder',contacts:[targetPerson]}];
  const result=contactsForSubmissionBuilder(contacts,'Target Builder',directory,'Original Builder',[matthew]);
  assert.equal(result[0].id,undefined);assert.equal(result[0].revision,undefined);assert.equal(result[0].name,'Matthew Wilson');
  assert.equal(result[1].id,'target-person');assert.equal(result[1].revision,6);assert.equal(result[2].id,undefined);
  assert.equal(JSON.stringify(contacts),snapshot,'save preparation never mutates source people');
});

test('name autofill preserves migrated nonnumeric phone labels without using them as phone identities',()=>{
  const legacy={id:'legacy',revision:2,name:'Legacy Person',phones:['Switchboard','02 9000 0000'],emails:['old format at company']};
  const original=JSON.stringify(legacy);
  const filled=matchSavedContact({...blank(),name:'Legacy Person'},[legacy],'name','Legacy Person');
  assert.deepEqual(filled.phones,['Switchboard','02 9000 0000']);assert.deepEqual(filled.emails,['old format at company']);
  assert.equal(filled.id,'legacy');assert.equal(filled.revision,2);
  filled.phones.push('0400 123 456');assert.equal(JSON.stringify(legacy),original);
  assert.equal(matchSavedContact({...blank(),phones:['Switchboard']},[legacy],'phone','Switchboard'),null);
});
