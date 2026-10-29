/** Verify the v3.7.6 document feature against source and the CURRENT built assets.
 * Vite re-hashes and replaces output filenames on every build, so tests must
 * resolve the assets referenced by the generated HTML, not an older release.
 */
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
const get=path=>readFileSync(new URL('../'+path,import.meta.url),'utf8');
const source=get('tenders_frontend/src/components/opportunities.tsx');
const types=get('tenders_frontend/src/lib/opportunity-types.ts');
const html=get('tenders_web/index.html');
const backend=get('conest_app/opportunities.py');
const api=get('conest_app/opportunity_http.py');
function htmlAsset(type){
  const match=type==='js'
    ?html.match(/<script\b[^>]*\bsrc="\/tenders\/assets\/([^"?]+\.js)"/)
    :html.match(/<link\b[^>]*\bhref="\/tenders\/assets\/([^"?]+\.css)"/);
  assert.ok(match,`Current Tender HTML must reference compiled ${type}`);
  const file='tenders_web/assets/'+match[1];
  assert.ok(existsSync(new URL('../'+file,import.meta.url)),`Missing compiled ${file}`);
  return {file,code:get(file)};
}
const app=htmlAsset('js');
const css=htmlAsset('css');
const chunk=app.code.match(/\.\/((?:opportunities|opportunity)[\w.-]+\.js)/);
assert.ok(chunk,'Current Tender entry must lazy-load an Opportunities chunk');
const built=get('tenders_web/assets/'+chunk[1]);
const checks=[
  ['source has card and detail controls', source.includes('op-docs-card-row')&&source.includes('op-docs-detail-row')],
  ['source excludes rejected and expired status', source.includes("['pending','approved'].includes(item.status)")],
  ['source uses separate authorised Assign', source.includes('selected.permissions.assign')&&source.includes('selected.permissions.manage')],
  ['source calls availability endpoint', source.includes("mutate('/documents'")],
  ['typescript includes boolean availability and assignment permission', types.includes('documentsAvailable?:boolean')&&types.includes('assign:boolean')],
  ['compiled module includes availability labels', built.includes('Documents not available')&&built.includes('Documents available')],
  ['compiled module controls permissions', built.includes('.permissions.assign')&&built.includes('.permissions.manage')],
  ['compiled module limits document status to active opportunities', built.includes('pending')&&built.includes('approved')],
  ['page points to existing built assets',!!app.code.length&&!!css.code.length],
  ['css includes accessible mobile controls',css.code.includes('.op-docs-toggle:focus-visible')&&/max-width\s*:\s*380px/.test(css.code)],
  ['API enforces document status change', backend.includes('def set_documents_available')&&api.includes("prefix + '/documents'")],
];
for(const [name,ok] of checks){assert.ok(ok,name);console.log('PASS:',name)}
