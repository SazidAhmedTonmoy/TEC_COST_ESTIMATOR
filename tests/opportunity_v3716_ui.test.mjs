/** v3.7.16 new opportunity form and approved-review source-level contracts.
 * The React/Vite build is run in CI before deployment. These checks are
 * intentionally independent of the old prebuilt Tender chunk names.
 */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const get=file=>readFileSync(new URL('../'+file,import.meta.url),'utf8');
const ui=get('tenders_frontend/src/components/opportunities.tsx');
const css=get('tenders_frontend/src/tender-v35.css');
const py=get('conest_app/opportunities.py');
const cases=[
  ['deadline picker rejects calendar days before Added date',ui.includes('min={legacyDatePairUnchanged?undefined:form.addedDate||undefined}')],
  ['moving Added date clears previously invalid closing deadline',ui.includes("form.due&&e.target.value&&form.due<e.target.value?'':form.due")],
  ['browser form checks date order before saving',ui.includes("payload.due<payload.addedDate&&!legacyDatePairUnchanged")],
  ['server validates the same date order',py.includes("fields['due'] < fields['addedDate'")],
  ['historical date pairs remain editable when unchanged',ui.includes('const legacyDatePairUnchanged=')],
  ['new opportunity has persistent document available option',ui.includes('op-documents-create')&&ui.includes('documentsAvailable:available')],
  ['document option uses explicit Yes and No',ui.includes("label==='yes'?'Yes':'No'")&&ui.includes('aria-pressed={form.documentsAvailable===available}')],
  ['new document flag is checked for strict boolean before saving',py.includes("type(documents_available) is not bool")],
  ['new opportunity defaults document availability to No',ui.includes('documentsAvailable:false')],
  ['region uses a select, not free-text datalist',ui.includes('<label className="op-field">Region<select required')&&!ui.includes('op-region-options')],
  ['region menu preserves NSW and VIC and configured regions',ui.includes('...defaultRegions,...regions')],
  ['approved eligible opportunities can move to review',ui.includes("['pending','approved'].includes(selected.status)")&&ui.includes("setDecision('review')")],
  ['linked or quoted approvals cannot move to review',ui.includes('!isOpportunityQuoted(selected)&&!selected.linkedAt')],
  ['expired approval requires extension before review',ui.includes('Extend the closing deadline before moving this opportunity to In Review.')],
  ['mobile-friendly focus and responsive style available',css.includes('.op-documents-create-options')&&css.includes('@media(max-width:380px)')],
];
for(const [label,ok] of cases){assert.ok(ok,label);console.log('PASS:',label)}
