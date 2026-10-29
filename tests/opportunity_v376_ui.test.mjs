import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const get=path=>readFileSync(new URL('../'+path,import.meta.url),'utf8');
const source=get('tenders_frontend/src/components/opportunities.tsx');
const types=get('tenders_frontend/src/lib/opportunity-types.ts');
const built=get('tenders_web/assets/opportunities-v376.js');
const app=get('tenders_web/assets/index-v376.js');
const html=get('tenders_web/index.html');
const css=get('tenders_web/assets/index-v376.css');
const backend=get('conest_app/opportunities.py');
const api=get('conest_app/opportunity_http.py');
const checks=[
  ['source has card and detail controls', source.includes('op-docs-card-row')&&source.includes('op-docs-detail-row')],
  ['source excludes rejected and expired status', source.includes("['pending','approved'].includes(item.status)")],
  ['source uses separate authorised Assign', source.includes('selected.permissions.assign')&&source.includes('selected.permissions.manage')],
  ['source calls availability endpoint', source.includes("mutate('/documents'")],
  ['typescript includes boolean availability and assignment permission', types.includes('documentsAvailable?:boolean')&&types.includes('assign:boolean')],
  ['compiled module includes availability and labels', built.includes('QeToggleDocs')&&built.includes('Documents not available')&&built.includes('Documents available')],
  ['compiled module hides rejected/expired controls', built.includes('![`pending`,`approved`].includes(e.status)')],
  ['compiled has separate team assignment permission', built.includes('Y.permissions.assign')&&built.includes('Y.permissions.manage')],
  ['compiled modules use matching version pins', app.includes('./opportunities-v376.js')&&built.includes('./index-v376.js')],
  ['page points to fingerprinted assets', html.includes('/tenders/assets/index-v376.js')&&html.includes('/tenders/assets/index-v376.css')],
  ['css includes accessible mobile controls', css.includes('.op-docs-toggle:focus-visible')&&css.includes('@media(max-width:380px)')],
  ['API enforces document status change', backend.includes('def set_documents_available')&&api.includes("prefix + '/documents'")],
];
for(const [name,ok] of checks){assert.ok(ok,name);console.log('PASS:',name)}
