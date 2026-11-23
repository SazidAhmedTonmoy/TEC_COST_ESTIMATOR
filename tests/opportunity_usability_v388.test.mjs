import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=(name)=>readFileSync(new URL('../tenders_frontend/src/'+name,import.meta.url),'utf8');
const server=readFileSync(new URL('../conest_app/opportunities.py',import.meta.url),'utf8');

test('analytics uses explicit light/dark tokens for backgrounds, legible text and tables',()=>{
 const css=source('tender-v35.css');
 assert.match(css,/v3\.8\.8: readable Opportunity analytics/);
 for(const part of ['.op-analytics-card','.op-analytics-table-panel','.op-analytics-donut>div','.op-analytics-dates','.op-analytics-modes','tbody th','thead th'])assert.ok(css.includes(part),part);
 assert.match(css,/html\[data-theme="dark"\] \.op-analytics/);
 assert.match(css,/color:var\(--op-analytics-text\)/);
});

test('approved calendar indicates missing documents with a softer tone and a factual hover detail',()=>{
 const calendar=source('components/opportunity-calendar.tsx');
 const event=source('components/calendar-month.tsx');
 const css=source('components/calendar-month.css');
 assert.match(server,/'documentsAvailable': item\.get\('documentsAvailable'\) is True/);
 assert.match(calendar,/documentsAvailable:event\.documentsAvailable/);
 assert.match(calendar,/label:'Documents',value:event\.documentsAvailable\?'Available':'Not available'/);
 assert.match(event,/documentsMissing=event\.documentsAvailable===false/);
 assert.match(event,/is-documents-pending/);
 assert.match(css,/\.flow-calendar-event\.is-documents-pending/);
 assert.match(css,/color-mix\(in srgb,var\(--flow-event-accent/);
});

test('Opportunity save controls remain within the independently scrolling form editor',()=>{
 const opportunities=source('components/opportunities.tsx');
 const css=source('tender-v35.css');
 assert.match(opportunities,/op-dialog op-edit-dialog op-opportunity-editor/);
 assert.match(opportunities,/op-dialog-actions op-opportunity-save-bar/);
 assert.match(opportunities,/Contacts save with this opportunity/);
 assert.match(opportunities,/type="submit" className="primary-btn" disabled=\{busy\|\|duplicateChecking/);
 assert.match(css,/\.op-opportunity-editor \.op-form-grid\{[^}]*overflow-y:auto/);
 assert.match(css,/\.op-opportunity-editor \.op-dialog-actions\.op-opportunity-save-bar\{[^}]*position:static/);
});
