import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const component=readFileSync(new URL('../tenders_frontend/src/components/tender-notifications.tsx',import.meta.url),'utf8');
const app=readFileSync(new URL('../tenders_frontend/src/components/tender-app.tsx',import.meta.url),'utf8');
test('notification search sends full-history filters to the server before pagination',()=>{
 assert.match(component,/type="search" aria-label="Search notifications by user name, project or message"/);
 assert.match(component,/new URLSearchParams\(\{page:String\(page\),pageSize:String\(PAGE_SIZE\),kind,q\}\)/);
 assert.match(component,/\['chases','Chase-ups'\]/);
 assert.match(component,/changeQuery\(''\)/);
 assert.match(component,/active\.current\?\.abort\(\)/);
 assert.match(component,/active\.current!==controller/);
 assert.match(component,/No matching notifications/);
});
test('new chase-up refreshes the notification bell and opens current history',()=>{
 assert.match(app,/\['chases','reminders'\]\.includes\(path\)\)window\.dispatchEvent\(new Event\('tenders:notifications-changed'\)\)/);
 assert.match(component,/tenders:notifications-changed',changed/);
 assert.match(component,/setInterval\(refresh,30000\)/);
 assert.match(component,/onOpenTender\(n\.submissionId,n\.kind==='chase-recorded'\?'history':'chase'\)/);
 assert.match(app,/onOpenTender=\{async\(id,tab\)=>\{const updated=await refreshOpportunitySubmissions\(\)/);
});
