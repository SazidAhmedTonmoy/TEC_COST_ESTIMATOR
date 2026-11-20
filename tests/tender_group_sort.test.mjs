import assert from 'node:assert/strict';
import test from 'node:test';
import {boundedPage,compareValues,paginateProjectRows,projectKey,sortGroupedSubmissions} from '../tenders_frontend/src/lib/reporting.ts';

const row=(id,project,builder,fields={})=>({id,project,builder,status:'Open',pricing:'Nil',value:null,due:'',latestDate:'',nextDue:'',...fields});
const rows=[
 row('a2','Alpha Project','Zen Builder',{value:200,due:'2026-11-09',latestDate:'2026-11-19',nextDue:'2026-12-16',status:'Open',pricing:'High'}),
 row('b2','Beta Project','Zen Builder',{value:100,due:'2026-11-05',latestDate:'2026-11-18',nextDue:'2026-12-02',status:'Lost',pricing:'Competitive'}),
 row('a1',' alpha   project ','Able Builder',{value:50,due:'2026-11-12',latestDate:'2026-11-17',nextDue:'2026-12-02',status:'Hold',pricing:'Competitive'}),
 row('c1','Charlie Project','Builder C',{status:'',pricing:''}),
 row('b1','BETA PROJECT','Able Builder',{value:300,due:'2026-11-02',latestDate:'2026-11-19',nextDue:'2026-12-30',status:'Won',pricing:'Nil'}),
];
const sortValue=(key,item)=>key==='project'?projectKey(item.project):key==='latest'?item.latestDate:key==='next'?item.nextDue:item[key];
const ids=items=>items.map(item=>item.id);
const groupNames=items=>[...new Set(items.map(item=>projectKey(item.project)))];
function assertContiguous(items){
 const complete=new Set();let previous;
 for(const item of items){const key=projectKey(item.project);if(key!==previous){assert.ok(!complete.has(key),'Project reappeared after another project: '+key);if(previous!==undefined)complete.add(previous);previous=key;}}
}

for(const key of ['project','pricing','status','value','due','latest','next'])for(const direction of ['asc','desc']){
 test(`${key} ${direction} keeps every builder submission with its project`,()=>{
  const before=structuredClone(rows),ordered=sortGroupedSubmissions(rows,item=>sortValue(key,item),direction);
  assertContiguous(ordered);
  assert.deepEqual([...ids(ordered)].sort(),[...ids(rows)].sort(),'sorting must retain every submission exactly once');
  assert.deepEqual(rows,before,'sorting must not mutate saved rows or input order');
  assert.deepEqual(ids(sortGroupedSubmissions([...rows].reverse(),item=>sortValue(key,item),direction)),ids(ordered),'equal values use stable project/builder/ID ties');
  for(const name of groupNames(ordered)){
   const members=ordered.filter(item=>projectKey(item.project)===name);
   for(let i=1;i<members.length;i++)assert.ok(compareValues(sortValue(key,members[i-1]),sortValue(key,members[i]),direction)<=0,'builders inside a project respect the selected column');
  }
 });
}

test('group values use lowest ascending and highest descending while missing values stay last',()=>{
 assert.deepEqual(ids(sortGroupedSubmissions(rows,item=>item.value,'asc')),['a1','a2','b2','b1','c1']);
 assert.deepEqual(ids(sortGroupedSubmissions(rows,item=>item.value,'desc')),['b1','b2','a2','a1','c1']);
 assert.deepEqual(ids(sortGroupedSubmissions(rows,item=>item.due,'asc')),['b1','b2','a2','a1','c1']);
 assert.deepEqual(ids(sortGroupedSubmissions(rows,item=>item.due,'desc')),['a1','a2','b2','b1','c1']);
});

test('same next-action dates stay together with stable alphabetical project and builder ties',()=>{
 const tied=[row('z','Zeta','Builder'),row('b','Alpha','Builder B'),row('a','Alpha','Builder A'),row('m','Middle','Builder')].map(item=>({...item,nextDue:'2026-12-02'}));
 for(const direction of ['asc','desc'])assert.deepEqual(ids(sortGroupedSubmissions(tied,item=>item.nextDue,direction)),['a','b','m','z']);
});

test('distinct names that compare equally remain deterministic after a data refresh',()=>{
 const input=[row('a','Cafe','Builder'),row('b','Café','Builder'),row('c','Project 2','Builder'),row('d','Project 02','Builder')];
 for(const direction of ['asc','desc']){
  const ordered=sortGroupedSubmissions(input,item=>item.nextDue,direction);
  assert.deepEqual(ids(sortGroupedSubmissions([...input].reverse(),item=>item.nextDue,direction)),ids(ordered));
  assert.equal(groupNames(ordered).length,4,'similar names are separate projects unless their normalized keys match');
 }
});

test('mixed missing values stay after recorded values and zero is a real tender value',()=>{
 const input=[row('a0','Alpha','A',{value:0}),row('an','Alpha','B',{value:null}),row('be','Beta','A',{value:''}),row('b2','Beta','B',{value:2}),row('cu','Charlie','A',{value:undefined})];
 assert.deepEqual(ids(sortGroupedSubmissions(input,item=>item.value,'asc')),['a0','an','b2','be','cu']);
 assert.deepEqual(ids(sortGroupedSubmissions(input,item=>item.value,'desc')),['b2','be','a0','an','cu']);
});

test('pricing priority moves the entire matching project and puts its matching builders first',()=>{
 const ordered=sortGroupedSubmissions(rows,item=>item.pricing,'asc',item=>item.pricing==='High'?1:0);
 assert.deepEqual(ids(ordered).slice(0,2),['a2','a1']);
 assertContiguous(ordered);assert.equal(ordered.length,rows.length);
});

test('project grouping normalizes case, spacing and Unicode without changing display names',()=>{
 const names=[row('1',' NSW AIP Bundle 10 ','Builder Z'),row('2','Other','Builder'),row('3','ＮＳＷ AIP Bundle 10','Builder A'),row('4','nsw   aip bundle 10','Builder B')];
 const ordered=sortGroupedSubmissions(names,item=>projectKey(item.project),'asc');
 assert.deepEqual(ids(ordered),['3','4','1','2']);
 assert.equal(ordered[0].project,'ＮＳＷ AIP Bundle 10');
});

const projectRows=(name,count)=>Array.from({length:count},(_,index)=>row(name+'-'+index,name,'Builder '+index));

test('pagination keeps whole projects even when that requires more pages than fixed row slicing',()=>{
 const input=[...projectRows('A',19),...projectRows('B',2),...projectRows('C',19),...projectRows('D',2)];
 const pages=paginateProjectRows(input);
 assert.deepEqual(pages.map(page=>page.length),[19,2,19,2]);
 assert.deepEqual(ids(pages.flat()),ids(input));
 assert.equal(boundedPage(4,pages.length,1),4,'the fourth complete-project page must remain reachable');
 assert.equal(boundedPage(99,pages.length,1),4,'a removed page clamps to the last real page');
 const projectPages=new Map();
 pages.forEach((page,index)=>page.forEach(item=>{const key=projectKey(item.project);assert.ok(!projectPages.has(key)||projectPages.get(key)===index);projectPages.set(key,index);}));
});

test('a large project receives its own complete page and no builder rows are lost',()=>{
 const input=[...projectRows('A',5),...projectRows('B',24),...projectRows('C',4),...projectRows('D',16)];
 const pages=paginateProjectRows(input);
 assert.deepEqual(pages.map(page=>page.length),[5,24,20]);
 assert.deepEqual(groupNames(pages[1]),['b']);
 assert.deepEqual(ids(pages.flat()),ids(input));
});

test('dashboard limits and empty pages preserve complete visible project groups',()=>{
 assert.deepEqual(paginateProjectRows([]),[]);
 const input=[...projectRows('A',8),...projectRows('B',4),...projectRows('C',3)];
 assert.deepEqual(paginateProjectRows(input,10).map(page=>page.length),[8,7]);
 assert.deepEqual(paginateProjectRows(projectRows('Large',14),10).map(page=>page.length),[14]);
 assert.deepEqual(paginateProjectRows(input,0).map(page=>page.length),[8,4,3]);
});
