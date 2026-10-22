import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';

const source=readFileSync('tenders_frontend/src/components/opportunities.tsx','utf8');
const built=readFileSync('tenders_web/assets/opportunities-v3510.js','utf8');
const entry=readFileSync('tenders_web/assets/index-v3510.js','utf8');
const html=readFileSync('tenders_web/index.html','utf8');

test('expired cards do not expose a reject action',()=>{
  assert.doesNotMatch(source,/className="op-expired-actions"/);
  assert.doesNotMatch(built,/className:`op-expired-actions`/);
});

test('expired detail copy offers approval but not rejection',()=>{
  assert.match(source,/The closing deadline has passed/);
  assert.doesNotMatch(source,/approve or reject this opportunity|also reject it/i);
  assert.doesNotMatch(built,/approve or reject this opportunity|also reject it/i);
});

test('deployable frontend uses new chunks, preserving all existing views',()=>{
  assert.match(html,/\/tenders\/assets\/index-v3510\.js/);
  assert.match(entry,/\.\/opportunities-v3510\.js/);
  assert.match(built,/\.\/index-v3510\.js/);
  assert.match(source,/canReject\(selected\)/);
  assert.match(source,/canQuote\(selected\)/);
  assert.match(source,/status==='expired'/);
});
