import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {matchesSelectedValues,toggleSelectedValue} from '../tenders_frontend/src/lib/multi-filter.ts';

const root=new URL('../',import.meta.url);
const read=path=>readFileSync(new URL(path,root),'utf8');

test('no selection means All, and two selections within one filter use OR',()=>{
 assert.equal(matchesSelectedValues([], 'NSW'),true);
 assert.equal(matchesSelectedValues(['NSW','VIC'],'NSW'),true);
 assert.equal(matchesSelectedValues(['NSW','VIC'],'VIC'),true);
 assert.equal(matchesSelectedValues(['NSW','VIC'],'QLD'),false);
 assert.equal(matchesSelectedValues(['Unassigned'],undefined),false);
});

test('multiple fields use AND without altering the chosen set',()=>{
 const status=['Open','Won'], regions=['NSW','VIC'], team=['TEC BD TEAM'];
 const matches=record=>matchesSelectedValues(status,record.status)&&matchesSelectedValues(regions,record.region)&&matchesSelectedValues(team,record.team);
 assert.equal(matches({status:'Won',region:'VIC',team:'TEC BD TEAM'}),true);
 assert.equal(matches({status:'Open',region:'NSW',team:'TEC BD TEAM'}),true);
 assert.equal(matches({status:'Open',region:'QLD',team:'TEC BD TEAM'}),false);
 assert.equal(matches({status:'Hold',region:'NSW',team:'TEC BD TEAM'}),false);
 assert.equal(matches({status:'Open',region:'VIC',team:'TEC AU TEAM'}),false);
});

test('checkbox toggling maintains existing choices, and deselecting last means All',()=>{
 const two=toggleSelectedValue(toggleSelectedValue([], 'NSW'),'VIC');
 assert.deepEqual(two,['NSW','VIC']);
 assert.deepEqual(toggleSelectedValue(two,'NSW'),['VIC']);
 assert.deepEqual(toggleSelectedValue(['VIC'],'VIC'),[]);
});

test('Tenders pages share multi-picker, preserve dashboard option selections and clear/export semantics',()=>{
 const app=read('tenders_frontend/src/components/tender-app.tsx');
 assert.match(app,/function MultiPicker\(/);
 assert.ok(app.includes('matchesSelectedValues(filter,s.status)'));
 assert.ok(app.includes("setFilter([s])"));
 assert.ok(app.includes("filter.length&&'TEC status: '+filter.join(', ')"));
 assert.ok(app.includes('value={value as string[]}'));
 assert.ok(app.includes('allLabel={(options as string[])[0]}'));
 assert.ok(app.includes('setFilter([])'));
});

test('Estimator home search precedes the aligned buttons and keeps original element IDs',()=>{
 const html=read('assets/index.html');
 const search=html.indexOf('id="project-search"'),row=html.indexOf('class="home-project-button-row"');
 const create=html.indexOf('id="home-new-project-button"'),json=html.indexOf('id="project-json-open"');
 assert.ok(search>0&&search<row&&row<create&&create<json);
 const css=read('assets/styles.css');
 assert.ok(css.includes('#home-view .home-project-actions{display:flex;flex-direction:column'));
 assert.ok(css.includes('#home-view .home-project-button-row{display:flex'));
});
