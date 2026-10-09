import assert from 'node:assert/strict';
import {activityMonths,awardActivityMonths} from '../tenders_frontend/src/lib/activity.ts';
const rows=[{due:'2024-12-20'},{due:'2025-02-01'},{due:'2025-02-15'},{due:''},{due:'invalid'},{due:'2025-13-01'}];
assert.deepEqual(activityMonths(rows),[{month:'2024-12',count:1,chases:0},{month:'2025-01',count:0,chases:0},{month:'2025-02',count:2,chases:0}]);
assert.deepEqual(activityMonths([]),[]);assert.deepEqual(activityMonths([{due:'2026-01-01'}]),[{month:'2026-01',count:1,chases:0}]);
assert.equal(activityMonths(rows).reduce((s,m)=>s+m.count,0),3);
console.log('Activity month counts passed: year boundary, zero gaps, invalid/undated exclusion and empty data.');

assert.deepEqual(awardActivityMonths([{project:'Same',due:'2026-01-01',builderStatus:'Awarded'},{project:'same',due:'2026-01-01',builderStatus:'Unsuccessful'},{project:'Other',due:'2026-03-01',builderStatus:'Awarded'},{project:'Undated',due:'',builderStatus:'Awarded'}]),[{month:'2026-01',count:1,awards:1},{month:'2026-02',count:0,awards:0},{month:'2026-03',count:1,awards:1}]);
