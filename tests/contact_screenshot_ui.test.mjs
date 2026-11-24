import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {runInNewContext} from 'node:vm';
import * as contacts from '../tenders_frontend/src/lib/builder-contacts.ts';
const source=name=>readFileSync(new URL('../'+name,import.meta.url),'utf8');
const require=createRequire(new URL('../tenders_frontend/package.json',import.meta.url));
const ts=require('typescript'),exports={};
runInNewContext(ts.transpileModule(source('tenders_frontend/src/lib/contact-screenshot.ts'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports,require:name=>{assert.equal(name,'./builder-contacts');return contacts}});
const {mergeDetectedContacts,validateDetectedContact}=exports;
const blank={builders:[],builderContacts:[]};
const contact={builder:'Example Construction',name:'Alex Example',phones:['0450 111 222'],emails:['alex@example.com']};
const saved={id:'person-1',revision:3,name:contact.name,phones:[],emails:contact.emails};
const directory=[{builder:contact.builder,contacts:[saved]}];
test('recognition reuses shared builder/contact, adds another builder and does not mutate input',()=>{
 const merged=mergeDetectedContacts(blank,[contact,{builder:'Second Construction',name:'Sam Sample',phones:[],emails:[]}],['Example Construction'],directory);
 assert.deepEqual(JSON.parse(JSON.stringify(merged.builders)),['Example Construction','Second Construction']);
 const person=merged.builderContacts[0].contacts[0];assert.equal(person.id,'person-1');assert.equal(person.revision,3);assert.equal(person.phones[0],contact.phones[0]);assert.equal(saved.phones.length,0);assert.equal(blank.builders.length,0);
});
test('re-import keeps a selected contact once and enriches compatible missing details',()=>{
 const first={builders:[contact.builder],builderContacts:directory};
 const merged=mergeDetectedContacts(first,[contact,contact],[],directory);
 assert.equal(merged.builderContacts[0].contacts.length,1);
 assert.equal(merged.builderContacts[0].contacts[0].phones[0],contact.phones[0]);
 assert.equal(first.builderContacts[0].contacts[0].phones.length,0);
});
test('same-name contacts with conflicting phone and email remain separate',()=>{
 const other={...contact,phones:['0400 999 888'],emails:['other@example.com']};
 const merged=mergeDetectedContacts(blank,[contact,other],[],[]);
 assert.equal(merged.builderContacts[0].contacts.length,2);
});
test('invalid data cannot be inserted into draft',()=>{
 assert.ok(validateDetectedContact({...contact,builder:''}));assert.ok(validateDetectedContact({...contact,emails:['bad']}));assert.throws(()=>mergeDetectedContacts(blank,[{...contact,phones:['not a number']}],[],[]));
});
test('screenshot import is accessible from New/Edit Opportunity and saves only into draft',()=>{
 const component=source('tenders_frontend/src/components/contact-screenshot-import.tsx');const form=source('tenders_frontend/src/components/opportunities.tsx');
 assert.match(component,/opportunities\/contact-screenshot/);assert.match(component,/Add reviewed builders/);assert.match(component,/Detect from text/);assert.match(component,/type="file"/);assert.match(form,/<ContactScreenshotImport/);assert.match(form,/setForm\(\{\.\.\.form,builders:result\.builders,builderContacts:result\.builderContacts\}\)/);
});
test('same preview renderer handles calendar events and agenda entries in all views',()=>{
 const calendar=source('tenders_frontend/src/components/calendar-month.tsx');assert.match(calendar,/flow-agenda-preview-anchor/);assert.match(calendar,/onPointerEnter/);assert.match(calendar,/createPortal/);
 assert.match(source('tenders_frontend/src/components/opportunity-calendar.tsx'),/<CalendarEventButton[^>]*event=\{previewEvent\(item\)\}[^>]*className="agenda-row"/);
 assert.match(source('tenders_frontend/src/components/tender-app.tsx'),/<CalendarEventButton[^>]*className="agenda-row"[^>]*event=\{chasePreviewEvent\(e\)\}/);
 assert.match(source('tenders_frontend/src/components/open-awarded.tsx'),/<CalendarEventButton[^>]*event=\{awardPreviewEvent\(event\)\}/);
 assert.match(source('assets/v23.js'),/<tr data-calendar-preview=/);
});
