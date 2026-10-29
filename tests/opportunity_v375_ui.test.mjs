import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync,existsSync,readdirSync} from 'node:fs';
import {canQuoteOpportunity} from '../tenders_frontend/src/lib/opportunity-display.ts';

const source=readFileSync('tenders_frontend/src/components/opportunities.tsx','utf8');
const html=readFileSync('tenders_web/index.html','utf8');
const htmlEntry=html.match(/<script[^>]*type="module"[^>]*src="\/tenders\/assets\/([^"]+\.js)"/);
const assets='tenders_web/assets/';
const jsFiles=readdirSync(assets).filter(name=>name.endsWith('.js'));
const builtFiles=jsFiles.map(name=>readFileSync(assets+name,'utf8'));
const built=builtFiles.find(text=>text.includes('Deadline: Low to High')&&text.includes('Deadline: High to Low'));

const now=Date.parse('2026-10-29T08:00:00Z');
const item={status:'approved',region:'NSW',due:'2020-05-10',permissions:{quote:true,approve:true},builders:['Contractor']};

test('approved unlinked opportunity remains quote-eligible after its deadline',()=>{
  assert.equal(canQuoteOpportunity(item,[],now),true);
  assert.equal(canQuoteOpportunity({...item,link:'https://example.com/plans'},[],now),true,'External tender URL does not count as a linked submission');
  assert.equal(canQuoteOpportunity({...item,linkedAt:'2026-10-01T00:00:00Z'},[],now),false);
  assert.equal(canQuoteOpportunity({...item,submissionIds:['abc']},[],now),false);
  assert.equal(canQuoteOpportunity({...item,quoteStatus:'quoted'},[],now),false);
  assert.equal(canQuoteOpportunity({...item,status:'expired'},[],now),false);
});

test('sort menu exposes both directional deadline orders in source and deployed bundle',()=>{
  for(const [value,label] of [['due_asc','Deadline: Low to High'],['due_desc','Deadline: High to Low']]){
    assert.ok(source.includes(`value="${value}"`));
    assert.ok(source.includes(label));
    assert.ok(built?.includes(`value:\`${value}\``) || built?.includes(`value:"${value}"`));
    assert.ok(built.includes(label));
  }
});

test('updated browser asset graph loads the patched Opportunity chunk',()=>{
  assert.ok(htmlEntry,'HTML should reference a compiled application entry');
  const entry=assets+htmlEntry[1];
  assert.ok(existsSync(entry),'HTML entry asset must exist');
  assert.ok(built,'Built Javascript must contain the current sort options');
  assert.ok(built.includes('You can still record Quoted or Not quoted'));
  assert.ok(!built.includes('Use Project Chase-up for existing submissions.'));
});
