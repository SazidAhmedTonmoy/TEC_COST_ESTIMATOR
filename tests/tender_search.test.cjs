const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('../tenders_frontend/node_modules/typescript');
const exportsObject={};vm.runInNewContext(ts.transpile(fs.readFileSync('tenders_frontend/src/lib/search.ts','utf8'),{module:ts.ModuleKind.CommonJS}),{exports:exportsObject});const match=exportsObject.matchesTender;
const closed={status:'Close',builderStatus:'Awarded',pricing:'High'},open={status:'Open',builderStatus:'In Progress',pricing:'Competitive'},won={status:'Won',builderStatus:'Unsuccessful',pricing:'Nil'};
for(const q of ['open','OPEN','Open']){assert.ok(match(open,'sydney',q));assert.ok(!match(closed,'historical note: open tender',q));}
assert.ok(match(closed,'','AWARDED'));assert.ok(!match(won,'builder once awarded', 'awarded'));
assert.ok(match(won,'','TEC won'));assert.ok(match(closed,'','closed'));assert.ok(match(open,'','IN PROGRESS'));assert.ok(match(won,'','No pricing feedback'));assert.ok(match(open,'sydney library','open SYDNEY'));assert.ok(!match(closed,'sydney open','open sydney'));
console.log('Tender category search passed: case, aliases, mixed terms, historical-note exclusion and separate awards/wins.');
