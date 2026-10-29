import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {test} from 'node:test';

const source=readFileSync('tenders_frontend/src/components/opportunities.tsx','utf8');
const html=readFileSync('tenders_web/index.html','utf8');
const assets='tenders_web/assets/';
const builtFiles=readdirSync(assets).filter(name=>name.endsWith('.js')).map(name=>readFileSync(assets+name,'utf8'));
const built=builtFiles.find(text=>text.includes('Reject opportunity')&&text.includes('Record quoted project'));
const entryMatch=html.match(/<script[^>]*type="module"[^>]*src="\/tenders\/assets\/([^"]+\.js)"/);
const entry=entryMatch?readFileSync(assets+entryMatch[1],'utf8'):'';

test('expired cards do not expose a reject action',()=>{
  assert.doesNotMatch(source,/className="op-expired-actions"/);
  assert.ok(built,'The deployed opportunity component must be included');
  assert.doesNotMatch(built,/className:`op-expired-actions`/);
});

test('expired detail copy offers approval but not rejection',()=>{
  assert.match(source,/The closing deadline has passed/);
  assert.doesNotMatch(source,/approve or reject this opportunity|also reject it/i);
  assert.doesNotMatch(built,/approve or reject this opportunity|also reject it/i);
});

test('deployable frontend uses new chunks, preserving all existing views',()=>{
  assert.ok(entryMatch,'HTML should load the current Tender entry');
  assert.ok(entry.length>100,'Compiled entry must be present');
  assert.ok(built.includes('Record quoted project'));
  assert.match(source,/canReject\(selected\)/);
  assert.match(source,/canQuote\(selected\)/);
  assert.match(source,/status==='expired'/);
});
