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
 assert.match(ui,/onOpen:\(\)=>revealCalendarEvent\(event\.date,event\)/);
 assert.match(ui,/<MonthCalendar[^>]*onSelectDate=\{revealCalendarEvent\}/);
 assert.match(ui,/onClick=\{\(\)=>onOpen\(s\)\}/);
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

test('today is visibly marked independently of selected day; Refresh header removed',()=>{
 const ui=src('tenders_frontend/src/components/open-awarded.tsx');
 const css=src('tenders_frontend/src/components/calendar-month.css');
 const calendar=src('tenders_frontend/src/components/calendar-month.tsx');
 const app=src('tenders_frontend/src/components/tender-app.tsx');
 assert.match(ui,/sydneyCalendarDate/);
 assert.match(ui,/<MonthCalendar[^>]*today=\{today\}[^>]*selectedDay=\{selectedDay\}/);
 assert.match(calendar,/cell\.date===today\?' is-today'/);
 assert.match(calendar,/cell\.date===selectedDay\?' is-selected'/);
 assert.match(calendar,/aria-current=\{cell\.date===today\?'date'/);
 assert.match(calendar,/flow-month-today-label/);
 assert.match(ui,/setSelectedDay\(date\)/);
 assert.match(css,/\.flow-month-day\.is-today \.flow-month-date/);
 assert.match(css,/\.flow-month-day\.is-selected/);
 assert.doesNotMatch(ui,/>Refresh<|onRefresh|RefreshCw/);
 assert.doesNotMatch(app,/onRefresh=\{refresh\}/);
});


test('calendar event preview includes builder contact with direct actions and a missing-details path',()=>{
 const ui=src('tenders_frontend/src/components/open-awarded.tsx');
 const css=src('tenders_frontend/src/components/open-awarded.css');
 const footer=ui.slice(ui.indexOf('className="oa-calendar-footer"'));
 assert.match(footer,/oa-selected-event-contact/);
 assert.match(footer,/Contact people/);
 assert.match(footer,/AwardContactList submission=\{s\}/);
 const shared=src('tenders_frontend/src/components/award-contact-list.tsx');
 assert.match(shared,/person\.phones\.map/);
 assert.match(shared,/person\.emails\.map/);
 assert.match(shared,/href=\{phoneHref\(phone\)\}/);
 assert.match(shared,/href=\{outlookHref\(email\)\}/);
 assert.match(footer,/onClick=\{\(\)=>edit\(s\)\}/);
 assert.match(shared,/oa-contact-warning/);
 assert.match(footer,/View project/);
 assert.match(ui,/selectedEventsRef\.current\?\.scrollIntoView/);
 assert.match(css,/\.oa-selected-event-contact/);
 assert.match(css,/\.oa-selected-event\.is-focused/);
});
