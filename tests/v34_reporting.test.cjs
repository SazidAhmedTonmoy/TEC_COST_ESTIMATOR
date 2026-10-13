const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),ts=require(root+'/tenders_frontend/node_modules/typescript');
const Module=require('module'),orig=Module._extensions['.ts'];Module._extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,f);
const {tenderSummary,monthlySummary,compareValues}=require(root+'/tenders_frontend/src/lib/reporting.ts');const {activityMonths}=require(root+'/tenders_frontend/src/lib/activity.ts');
const rows=[{id:'1',project:'Alpha',builder:'A',value:100,due:'2026-07-19'},{id:'2',project:'Alpha',builder:'B',value:120,due:'2026-07-20'},{id:'3',project:'Beta',builder:'B',value:50,due:'2026-07-21'},{id:'4',project:'Gamma',builder:'C',value:300,due:'2026-09-01'}];
const chases=[{submissionId:'1',date:'2026-07-02'},{submissionId:'2',date:'2026-08-10'},{submissionId:'2',date:'2026-08-11'},{submissionId:'missing',date:'2026-10-10'}];
assert.deepEqual(tenderSummary(rows,chases),{projects:3,submissions:4,builders:3,value:470,chases:3});
assert.deepEqual(monthlySummary(rows,chases,'2026-07'),{projects:2,submissions:3,builders:2,value:170,chases:1});
assert.deepEqual(activityMonths(rows,chases),[{month:'2026-07',count:2,chases:1},{month:'2026-08',count:0,chases:2},{month:'2026-09',count:1,chases:0}]);
assert.equal(compareValues(20,100,'desc')>0,true);assert.equal(compareValues(null,20,'desc')>0,true);assert.equal(compareValues('alpha','ALPHA','asc'),0);
console.log('PASS: unique project totals, highest quote once, monthly chase dates, filtered attribution, numeric/text/null sorting.');

const {groupProjects,boundedPage}=require(root+'/tenders_frontend/src/lib/reporting.ts');
const variants=[{id:'a',project:'City  Hall',builder:'A',value:100,due:'2026-07-01'},{id:'b',project:' CITY HALL ',builder:'B',value:120,due:'2026-07-01'}];
assert.equal(tenderSummary(variants).projects,1);assert.equal(tenderSummary(variants).value,120);
assert.equal(groupProjects(variants).length,1);assert.equal(groupProjects(variants)[0].rows.length,2);
assert.equal(activityMonths(variants)[0].count,1);
assert.equal(boundedPage(4,21),2);assert.equal(boundedPage(4,0),1);
console.log('PASS: whitespace-normalized project grouping and pagination after shrinking results.');
