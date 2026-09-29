import assert from 'node:assert/strict';
import {activityMonths} from '../tenders_frontend/src/lib/activity.ts';
const rows=[{due:'2024-12-20'},{due:'2025-02-01'},{due:'2025-02-15'},{due:''},{due:'invalid'},{due:'2025-13-01'}];
assert.deepEqual(activityMonths(rows),[{month:'2024-12',count:1},{month:'2025-01',count:0},{month:'2025-02',count:2}]);
assert.deepEqual(activityMonths([]),[]);assert.deepEqual(activityMonths([{due:'2026-01-01'}]),[{month:'2026-01',count:1}]);
assert.equal(activityMonths(rows).reduce((s,m)=>s+m.count,0),3);
console.log('Activity month counts passed: year boundary, zero gaps, invalid/undated exclusion and empty data.');
