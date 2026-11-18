import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = relative => readFileSync(new URL('../' + relative, import.meta.url), 'utf8');

test('multi-select options keep checkbox beside the option label', () => {
  const css = source('tenders_frontend/src/tender-v35.css');
  const app = source('tenders_frontend/src/components/tender-app.tsx');
  assert.match(css, /\.tender-multi-choices\s*>\s*label\.tender-multi-choice[\s\S]*?grid-template-columns:18px minmax\(0,1fr\)\s*!important/);
  assert.match(css, /\.tender-multi-choices\s*>\s*label\.tender-multi-choice\s*>\s*input\[type=checkbox\]/);
  assert.match(app, /<label className="tender-multi-choice" key=\{option\}><input type="checkbox"/);
});

test('region, submission team and builder outcome have a three-column desktop row', () => {
  const css = source('tenders_frontend/src/tender-v35.css');
  const app = source('tenders_frontend/src/components/tender-app.tsx');
  assert.match(css, /\.dashboard-filters\{[\s\S]*?grid-template-columns:repeat\(3,minmax\(0,1fr\)\)\s*!important/);
  assert.match(css, /@media\(max-width:520px\)\{\.dashboard-filters/);
  assert.ok(app.includes("['Region',region,setRegion"));
  assert.ok(app.includes("['Submission team',team,setTeam"));
  assert.ok(app.includes("['Builder outcome',outcome,setOutcome"));
});

test('Estimator project search remains above and equals combined project button width', () => {
  const css = source('assets/styles.css');
  const html = source('assets/index.html');
  assert.match(css, /#home-view \.home-project-actions\{display:flex;flex-direction:column;[\s\S]*?width:max-content/);
  assert.match(css, /#home-view \.home-project-actions \.home-project-search\{[^}]*width:100%/);
  assert.match(css, /#home-view \.home-project-button-row\{[^}]*width:max-content/);
  assert.ok(html.indexOf('id="project-search"') < html.indexOf('class="home-project-button-row"'));
});
