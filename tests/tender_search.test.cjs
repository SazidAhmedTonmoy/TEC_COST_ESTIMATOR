const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('../tenders_frontend/node_modules/typescript');
const exportsObject={};vm.runInNewContext(ts.transpile(fs.readFileSync('tenders_frontend/src/lib/search.ts','utf8'),{module:ts.ModuleKind.CommonJS}),{exports:exportsObject});const match=exportsObject.matchesTender;
const closed={status:'Close',builderStatus:'Awarded',pricing:'High'},open={status:'Open',builderStatus:'In Progress',pricing:'Competitive'},won={status:'Won',builderStatus:'Unsuccessful',pricing:'Nil'};
for(const q of ['open','OPEN','Open']){assert.ok(match(open,'sydney',q));assert.ok(!match(closed,'historical note: open tender',q));}
assert.ok(match(closed,'','AWARDED'));assert.ok(!match(won,'builder once awarded', 'awarded'));
assert.ok(match(won,'','TEC won'));assert.ok(match(closed,'','closed'));assert.ok(match(open,'','IN PROGRESS'));assert.ok(match(won,'','No pricing feedback'));assert.ok(match(open,'sydney library','open SYDNEY'));assert.ok(!match(closed,'sydney open','open sydney'));
console.log('Tender category search passed: case, aliases, mixed terms, historical-note exclusion and separate awards/wins.');

const searchText=exportsObject.tenderSearchText;
const sample={...open,id:'s1',project:'La Trobe',builder:'Example Builder',quoteNo:'Q58',submittedByTeam:'TEC BD TEAM',remarks:'Confirm access',latest:'Latestcommentonly'};
const chases=[{id:'c1',submissionId:'s1',note:'Historicalcommentonly',author:'Yunus',date:'2026-10-09'}];
const reminders=[{id:'r1',submissionId:'s1',note:'Manualreminder',due:'2026-10-20'}];
for(const view of ['dashboard','chase-up','search']){
 const index=searchText(sample,chases,reminders,view,['$10,000','20 October 2026']);
 for(const query of ['latestcommentonly','HISTORICALCOMMENTONLY'])assert.equal(match(sample,index,query),false,view+': comment matched');
 for(const query of ['LA TROBE','example builder','q58','TEC BD TEAM','Confirm access','Yunus','manualreminder','$10,000','Open','Competitive'])assert.equal(match(sample,index,query),true,view+': missing '+query);
}
assert.ok(match(sample,searchText({...sample,project:'Historicalcommentonly'},chases,reminders,'dashboard'),'historicalcommentonly'),'A comment word still matches when independently present in project details');
assert.ok(match(sample,searchText(sample,chases,reminders,'projects'),'historicalcommentonly'),'Other pages retain their existing search');
console.log('Dashboard and Chase-up exclude latest and historical comments while retaining tender details.');
