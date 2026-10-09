# TEC ConEst v3.4 — 9 October 2026

## Team and tender refinements — 9 October 2026

- **Teams:** Administrators can delete a team. Confirmation explains that members become unassigned and team-based editing access is removed; users and projects remain. Tender selectors show only currently managed teams. Future renames follow existing assignments; deletion displays Not specified/Unassigned. Old unmatched team labels are not guessed or added as extra choices. Returning to a tender tab refreshes its data and team list.
- **Activity chart:** Replaced recorded chase-ups with builder awards. Gold is unique projects; purple is awarded builder submissions. Both use submission-deadline month, because an award date is not recorded. Clicking an award bar opens those awarded submissions.
- **Shared project fields:** Region and submission deadline apply to all builders for a project, matched without case/spacing differences. Regions are trimmed and uppercased. Submission month is derived from the deadline. Sibling rows update together and receive new revisions, preventing stale edits from overwriting the change.
- **Existing inconsistent records:** One-time cleanup keeps the latest existing deadline and the most-used nonblank region (alphabetical tie-break) for each project. Month is recalculated. A `tec_tenders.pre-v34b.db` backup is created before this cleanup on an existing tender database.
- **Chase dates:** Status updated is read-only and derived from the latest dated chase-up, including edits and imported history. A backdated entry does not move it backwards. Without a dated chase-up it is blank/Not recorded; January 1900 placeholders are removed.
- **Overview editing:** Each submission in project/builder overviews has a pencil Edit action. The editor allows quote value, TEC status, builder outcome, pricing feedback, contact person and email changes. Contact details are displayed in the overview row.
- **Imports:** Blank optional fields remain blank, Nil or Not specified, and blank quote values remain unknown rather than zero. Missing TEC status defaults to Open. Project and builder identity are still required. Workbook project-field updates propagate to other builder submissions and are included in preview counts. Conflicting nonblank project fields in one upload produce a row/project validation message rather than silently choosing between them. Existing unchanged workbook cells still preserve website edits.
- **Pricing header:** Repeated clicks cycle No feedback, Competitive, High, Mid-Range, Lower, Mix and any additional stored categories to the top. All results remain available. The header identifies which category is first; the Filters panel can show only a chosen category.
- **Text cleanup:** Removed the redundant submission count beside builder counts on Projects, and contact names beneath builder names on the Builders list. Contact details remain available in overviews and tender details.

### Installation and checks

Use the full ZIP or overlay the cumulative changed-files ZIP on the existing v3.3/v3.4 source. Keep your live databases and uploads. Commit/push the code and restart Passenger after deployment. Release stays **3.4** and schema version stays **31**; an idempotent `v3.4-team-directory` migration adds the team alias table to an existing installation without replaying historical team initialization.

Verified: all 30 Python test modules; additional import/preview regressions; TypeScript compilation; activity-chart checks; production builds; browser checks for overview editing, contacts, project propagation, pricing cycling, team-delete controls, mobile overflow and console errors. No live deployment was performed.

The original v3.4 notes below describe the initial release; the refinements above supersede the chart, team-list and project-date behaviour where they differ.

## Deployment validation fix

Corrected the HTTP health-check test to expect release 3.4 instead of 3.3. The stale assertion stopped deployment during validation, before uploading application code. No database or application behaviour change is required for this fix. If v3.4 is already in your repository, replace `tests/test_http_v232.py`, commit and push, then rerun deployment.

## Changes

1. **Tenders on mobile:** Estimator-style brand header with logo, workspace switch and Menu control. Navigation closes after selecting a page. Summary cards scroll horizontally on small screens.
2. **Full-width pages:** Tenders uses the available workspace width, including when zooming out. Tables keep readable column widths and scroll within their containers on phones.
3. **Help theme:** The Help button and chat send button use the Tender gold accent in light and dark modes.
4. **Expand All / Shrink All:** One Estimator button beside Find in estimate expands every category and item component list, or collapses both. This changes the view only.
5. **Sortable tables:** Click any data-column heading in Project Chase-up, Projects or Builders to sort descending, then ascending. Numeric amounts/counts sort numerically; dates sort chronologically; text and status types sort alphabetically. Blank values remain last. The arrow shows the active direction.
6. **New columns:** Pricing feedback in Project Chase-up; submission deadline in Projects. For a project with different submission deadlines, the table shows the earliest and labels it as one of multiple deadlines.
7. **Submitted by team:** Tender details and Edit tender include the team selector. This is separate from the user who imported or edited the tender. Existing dated submissions are assigned TEC AU TEAM before **20 July 2026**, and TEC BD TEAM on or after that date. Undated records remain unassigned. Current teams are available alongside the two historical team labels. Manual selections are preserved through restarts and workbook updates; new imports receive the date-based default.
8. **Grouped filters:** Filters opens labelled sections for TEC status, region, builder outcome, pricing feedback, submission team and builder/project. Filters combine with the case-insensitive search. Calendar and Reminders use the same filters. Dashboard has prominent region, team and builder-outcome selectors, with further options beside its search bar. Defaults are All.
9. **Live result summaries:** Summary counts follow search, filters and the selected chase-up tab. They include submissions, unique projects, builders, highest quotes counted once per project, and recorded chase-ups. Excel exports use the matching submissions.
10. **Tender overviews:** Builder/region text is larger and bold. Project and Builder overviews include Back, restoring the previous detail view. Submissions and Builder awards cards open/filter the submission list.
11. **Calendar summary:** Monthly projects due, builder submissions and distinct builders, recorded chase-ups, and quoted sum replace the explanatory paragraph. Quoted sum counts only the highest quote for each project in that month's matching submissions. Event-type selection changes the visible event list; the summary continues to describe the full month under the search filters.
12. **Dashboard filters:** KPI cards, outcome charts, monthly activity, reminders and the open-tender list all use the selected filters.
13. **Monthly activity:** Gold bars show unique projects by submission-deadline month; purple bars show recorded chase-up entries by chase date. A project counts once within a month even when quoted to several builders. Bar clicks open the related submissions; all-months view and year selection remain available. Undated records are excluded.
14. **Open tenders:** Dashboard shows the latest ten open submissions instead of five, ordered by deadline by default.

## Deployment

- Back up `conest_catalog.db` and `tec_tenders.db`. Keep all live database files and WAL/SHM files excluded from Git. Neither release ZIP includes databases.
- Overlay the changed-files ZIP on the latest v3.3 code, preserving relative paths. Alternatively, use the full v3.4 ZIP and retain the live databases and server configuration.
- Both frontends are built and included. Deploy source files and their fingerprinted assets together. No npm build is needed on the host for these ZIPs.
- Restart Passenger after copying the code. The existing `passenger_wsgi.py` remains compatible and is included in the full ZIP.
- Health should report **version 3.4**, **Estimator schema 31**. No Estimator schema change is needed. On first Tender access, a one-time migration assigns missing submission teams and invalidates stale edit revisions. An existing Tender database is backed up to `tec_tenders.pre-v34.db` before this migration, unless that backup already exists.
- No user, contributor, submission value, chase history or estimate is deleted by this update. Team assignment does not grant project access or count as a staff contribution.

## Verification

16 targeted Python tests passed, covering cutoff boundaries, editable teams, idempotent migration, conflict protection, authenticated bootstrap, workbook import/export regression and Tender integration. Frontend checks covered highest-quote deduplication, monthly project/chase counting, missing dates and numeric/text sorting. TypeScript checking and both frontend builds passed.

Browser checks passed for Expand/Shrink All, ten dashboard rows, full-width layout at a 5,000-pixel viewport, dashboard and combined filters, ascending/descending sorting, editable teams, overview Back and summary cards, calendar totals, mobile menu and gold Help button, and desktop/mobile light and dark layouts. Checks used isolated test databases. No live deployment or production load benchmark was performed.

## Changed files

- README.md
- UPDATE_V3.4.md
- assets/app.57ec87590b5c.js
- assets/estimate_workspace.js
- assets/help_shared.css
- assets/index.html
- assets/tender_boot.css
- assets/tender_theme.js
- assets/workspace.js
- conest_app/__init__.py
- conest_app/auto_upgrade.py
- conest_app/http_workspace.py
- conest_app/teams.py
- conest_app/tender_http.py
- conest_app/tender_import.py
- conest_app/tenders.py
- tenders_frontend/index.html
- tenders_frontend/package-lock.json
- tenders_frontend/package.json
- tenders_frontend/src/components/group-detail.tsx
- tenders_frontend/src/components/tender-activity.tsx
- tenders_frontend/src/components/tender-app.tsx
- tenders_frontend/src/globals.css
- tenders_frontend/src/lib/activity.ts
- tenders_frontend/src/lib/reporting.ts
- tenders_frontend/src/lib/types.ts
- tenders_web/assets/index-BEKV6x3p.js
- tenders_web/assets/index-DPZm7Tft.css
- tenders_web/index.html
- tests/tender_activity.test.mjs
- tests/test_http_v232.py
- tests/test_v34.py
- tests/test_v34_followup.py
- tests/v34_reporting.test.cjs

Old fingerprinted assets no longer referenced (optional cleanup after deployment):

- assets/app.c21ea600d619.js
- tenders_web/assets/index-BCJvm32p.css
- tenders_web/assets/index-CDht-Xeg.js
