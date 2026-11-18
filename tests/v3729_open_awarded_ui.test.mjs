import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const src=name=>readFileSync(new URL('../'+name,import.meta.url),'utf8');

test('Open-Awarded has switchable Cards and Calendar views and separate event colours',()=>{
 const ui=src('tenders_frontend/src/components/open-awarded.tsx');
 const css=src('tenders_frontend/src/components/open-awarded.css');
 assert.match(ui,/setView\('cards'\)/);
 assert.match(ui,/setView\('calendar'\)/);
 assert.match(ui,/aria-pressed=\{view==='calendar'\}/);
 assert.match(ui,/export function awardCalendarEvents/);
 assert.match(ui,/export function awardMonthCells/);
 assert.match(ui,/oa-event-award/);
 assert.match(ui,/oa-event-start/);
 assert.match(css,/oa-legend-award/);
 assert.match(css,/oa-legend-start/);
 assert.match(ui,/onOpen\(event.submission\)/);
});

test('Awarded cards, detail and edit dialog support start dates and safe project links',()=>{
 const ui=src('tenders_frontend/src/components/open-awarded.tsx');
 const sheet=src('tenders_frontend/src/components/tender-app.tsx');
 assert.match(ui,/Est\. start date/);
 assert.match(ui,/Project link/);
 assert.match(ui,/safeOpportunityLink/);
 assert.match(ui,/awardProjectLink/);
 assert.match(ui,/opportunityLink/);
 assert.match(ui,/Use Opportunity link/);
 assert.match(sheet,/Est\. start date/);
 assert.match(sheet,/oa-sheet-project-link/);
 assert.match(sheet,/safeOpportunityLink/);
});
