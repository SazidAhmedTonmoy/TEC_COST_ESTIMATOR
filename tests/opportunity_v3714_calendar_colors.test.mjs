import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {calendarTeamPalette,calendarTeamAppearance,teamCalendarColor} from '../tenders_frontend/src/lib/calendar-team-colors.ts';

const teams=[{id:12,name:'TEC AU'},{id:4,name:'TEC BD'},{id:31,name:'Another team'}];
test('team colour is stable across team list and calendar month ordering',()=>{
 const palette=calendarTeamPalette(teams);
 const reordered=calendarTeamPalette([...teams].reverse());
 for(const team of teams) assert.deepEqual(palette.get(team.id),reordered.get(team.id));
 assert.notEqual(palette.get(4).accent,palette.get(12).accent);
});
test('multiple teams show all names and are assigned one stable primary colour',()=>{
 const palette=calendarTeamPalette(teams);
 const result=calendarTeamAppearance([12,4,12],teams,palette);
 assert.equal(result.key,'4');
 assert.deepEqual(result.teamIds,[4,12]);
 assert.equal(result.label,'TEC BD · TEC AU');
 assert.equal(result.color.accent,teamCalendarColor(4,palette).accent);
});
test('unassigned opportunities have a different neutral colour from quoted green',()=>{
 const palette=calendarTeamPalette(teams);
 const result=calendarTeamAppearance([],teams,palette);
 assert.equal(result.label,'Unassigned');
 assert.equal(result.key,'unassigned');
 assert.equal(result.color.accent,'#94a3b8');
 assert.notEqual(result.color.accent,'#18a785');
});
test('calendar source and style separate team-coloured needs-quote from quoted state',()=>{
 const calendar=readFileSync(new URL('../tenders_frontend/src/components/opportunity-calendar.tsx',import.meta.url),'utf8');
 const style=readFileSync(new URL('../tenders_frontend/src/tender-v35.css',import.meta.url),'utf8');
 const form=readFileSync(new URL('../tenders_frontend/src/components/opportunities.tsx',import.meta.url),'utf8');
 assert.match(calendar,/event\.quoted\?null:needsQuoteAppearance\(event\)/);
 assert.match(calendar,/event\.quoted\?'is-quoted':'needs-quote team-coded'/);
 assert.match(calendar,/Needs quote · /);
 assert.match(style,/calendar-event\.needs-quote\.team-coded/);
 assert.match(form,/<option value="added">Recently added<\/option>/);
 assert.match(form,/useState\('due_desc'\)/);
});
