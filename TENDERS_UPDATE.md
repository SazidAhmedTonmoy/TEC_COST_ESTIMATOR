# TEC ConEst v3.1 — deployment and database guide

Extract the changed-files ZIP into the existing TEC ConEst application folder and replace matching files, then restart the Python app / cPanel application. Keep the existing `data/` directory. The full ZIP is the complete source alternative. Neither package replaces your estimator database. Compiled frontend assets are included; Node is not required on the hosting server.

Use the small circular-arrow button beside **Estimator** to open **TEC ConEst Tenders**. The reverse button returns to Estimator. Both use the same sign-in, users, profile photo, password rules and light/dark preference. Tenders uses a yellow accent. Profile is shared. Manage Users and App Settings are accessed from Estimator; Tenders has no separate links to them. The old tender-only Settings page is removed.

## v3.1 tender views

Builders now has an **All Projects** selector in place of its redundant builder selector. Selecting a project limits the builder rows, project counts, awards, TEC wins and submitted values to matching submissions. Keyword, region and TEC-status filters still work together. Other pages retain their builder selector.

Tender activity keeps its six-month dashboard preview. **View all months** opens a wide, scrollable chart with a year selector and every month between the earliest and latest dated submission, including zero-activity gaps. Selecting a nonzero bar opens that month's tender submissions. This uses the data already loaded; it makes no extra server request.

Both ZIPs include the earlier review workflow and alignment changes. The changed-files ZIP is cumulative from the last pre-review v3.0 package. Runtime databases are excluded. The deployment health check now expects release **3.1**, schema **27**. The Passenger adapter version is **3.1**; if your deployment excludes `passenger_wsgi.py`, replace that file manually in cPanel as before and restart the application.

## Review workflow update — 28 September 2026

Progress is now **Not started → In progress → In review → Submitted**. Review is optional and may be reopened after submission. Completed is removed from the UI. On the first start after deployment, schema 27 automatically moves every existing Completed project to Submitted, preserving estimates, submission deadlines, activity and historical completion attribution. A protected pre-upgrade backup is created by the existing migration process. No database file is included in the update ZIP.

Choose **In review** in Manage Project and set a review deadline. Active colleagues, including read-only users on other teams, see it in **Keep on Schedule**. Mark seen is individual; reopening a review or changing its deadline creates a fresh reminder. Edit permissions are unchanged.

The calendar shows project titles in yellow while In review and adds a labelled entry at the review deadline. Returning to Submitted removes that review entry and reminder. The original submission entry remains. If both dates are the same, a single calendar entry carries both labels. Review-only entries are excluded from monthly project counts, labour, material, quoted and result totals, even if the review is in another month.

Category totals use fixed columns so labels and amounts align consistently between sections. Compiled browser assets are included. Replace the matching files and restart all application workers after deployment so the new workflow and automatic migration take effect.

## Estimate layout and shared-use update — 28 September 2026

- Rates and mark-ups now uses an accessible + / − toggle. The cost-summary toggle is larger; the summary remains collapsed by default.
- Item actions have matching buttons, clearer dark-theme contrast and aligned numeric columns. Category totals have consistent labels and values. The search clear button sits inside its input. Mobile editing retains its stacked layout.
- Project lists fetch names, teams, individual-user display details and contributor summaries in four batch queries, replacing repeated per-project metadata queries. Permission checks still read live account and assignment records; no account-specific results are shared between users or cached across requests.
- Local tests compare batch output with individual project reads, check immediate membership/account changes, and run 16 list reads across eight threads using four accounts. This reduces database work; live hosting capacity still requires measurements on the deployed server.

## Existing tender database

If you have used the standalone tender app since this ZIP was created, stop that standalone server and copy its `data/tec_tenders.sqlite3` into the estimator's `data/` directory before first opening Tenders. Keep any SQLite sidecar files with it if they remain after shutdown. The application makes a consistent SQLite backup into `tec_tenders.db`; it keeps the original `.sqlite3` file. If a `tec_tenders.db` already exists, that existing database is used.

The uploaded ZIP contained seed JSON, not a live SQLite database. A new installation initialises **291 submissions and 332 recorded chase-ups** from that seed. It does not insert them again on subsequent starts. Estimator data remains in `conest_catalog.db`; tender records live separately in `tec_tenders.db`. Both are SQLite databases. Optional `CONEST_TENDERS_DB_PATH` overrides the tender path.

Tender daily snapshots are retained separately in `data/tender_backups/` (latest one). The existing App Settings database restore applies to the estimator database, not to the tender database. Keep both databases in your server backup plan.

## Startup update

Tenders now starts its authenticated bootstrap request while its JavaScript loads. That single response supplies the session and initial data, removing the previous sequential session/data requests. A public sidebar shell is visible immediately, with the Estimator-style loader centred in the content viewport. Failed connections retain the sidebar and offer Retry. No user records are stored in browser storage. Password-change and authentication restrictions remain enforced. The requested one-second workspace transition remains unchanged. Estimator's tab title is now TEC ConEst Estimator.

Local verification covered delayed loading, loader position, a single bootstrap request, failed-request retry, authentication/password restrictions, search and both workspace transitions. Production response times have not been measured.

## Changes

- Submission pipeline, Tender activity, Builder outcomes and Pricing feedback share one desktop row. Chart legends and activity bars open filtered submissions. Up next spans the row below. Narrow screens stack cards.
- Removed the overlapping sticky toolbar, generic page slogans, import footnotes and standalone tender settings page.
- Project and builder overviews include builder awards, awarded builders/projects and pricing-feedback counts.
- Distinct colours identify outcomes and calendar event types. Calendar events also retain text labels.
- Tender details offer deletion for administrators and the tender creator. A confirmation and revision check prevent accidental or stale deletion; related chase history and reminders are deleted with that submission.
- Chase-up authors come from the authenticated user, not a typed name.

## Performance and validation

Estimator pages do not load the React tender bundle or tender dataset. Tender resources are fingerprinted, cached and compressed. Tender edits return a compact affected-record response instead of reloading every submission. Search uses deferred input and indexed history lookups. Project, builder and calendar agenda lists are paginated. Calendar events are computed only on that page. SQLite read snapshots are cached per process and invalidated through a database generation counter.

Validation included 121 Python tests, TypeScript checking, frontend production builds and browser checks for chart filtering, create/edit/delete, the two workspace links, shared profile, dark mode and mobile overflow. On the test machine, the initial tender JSON compressed from 239,686 to 34,395 bytes; a new-submission update was 402 bytes. Cached data reads had a median of 0.21 ms. These are local measurements, not HostGator benchmarks; hosting latency still depends on the VPS and network.

To rebuild after frontend changes: `npm ci --prefix tenders_frontend`, `npm run build --prefix tenders_frontend`, then `python tools/build_frontend.py`. The included GitHub workflow builds both frontends. Its upload excludes runtime databases and node_modules.

## Deploy v3.0 through Git without overwriting databases

1. Commit the updated application source, `tenders_seed/seed.json`, frontend source/lockfile and deployment workflow. Keep `.db`, `.sqlite3`, SQLite sidecars and `data/` runtime contents out of Git. The included `.gitignore` excludes database files; the deployment workflow excludes the entire runtime `data/` directory from rsync, including deletion.
2. Push your code. The workflow builds both frontends and uploads code. It never copies a database. Retain the existing estimator `data/conest_catalog.db` and any existing `data/tec_tenders.db`.
3. In cPanel, replace the app-root `passenger_wsgi.py` with the supplied v3.0 file, then restart the Python application (or touch `tmp/restart.txt`). The Git workflow intentionally does not overwrite this adapter or your root `.htaccess`.
4. Sign in and open Tenders. If `tec_tenders.db` is absent, the server creates it from the tracked seed. This needs write access to `data/` for the application user. Existing estimator users and passwords remain in the estimator database; there is no second login database.
5. Check `/api/health`: release must be `3.0`, schema version `26`. Responses routed through Passenger should show `X-ConEst-Adapter: 3.0`. Public files served directly by Apache will not have that adapter header.

The `.db` suffix still represents SQLite; it is not a different database engine. If your standalone Tenders database has newer records than the bundled seed, follow **Existing tender database** above before first opening the integrated workspace. Do not replace an existing production tender database with a seed copy. If both databases already have new records, a deliberate merge with ID/conflict checks is needed instead of copying one over the other.

The seed is a one-time starting dataset, not ongoing synchronisation. Changing `seed.json` in a later Git push does not update existing tender records. Add and edit ongoing records through the app. Keep the seed in a private repository because it contains project and builder data. If a database was already tracked by Git, `.gitignore` alone does not untrack it: back it up, use `git rm --cached` for that exact database path, and commit the removal; this leaves the working file on disk.

## v3.0 sidebar and transition

The desktop sidebar uses the same 236px width, 24px/16px padding, 42px logo, 51px menu rows, 5px menu gaps and bottom profile/sign-out positions as Estimator. Name/photo still open the shared profile; initials use the first and last name. Tenders keeps yellow accents. Workspace labels, the separate navigation divider and admin footer links are removed.

Switching uses a shared coloured title wipe (yellow into Tenders, teal into Estimator), then reveals the destination with a one-second transform animation. Navigation and requests start immediately. The cover releases when the destination is ready, with a 1.8-second fallback so a slow request cannot obscure its loading/error screen indefinitely. Reduced-motion skips the wipe. No other-workspace dataset is preloaded.

V3.0 validation: all 122 Python tests passed, including transport compression/header handling and tender integration. TypeScript and both production builds passed. Browser checks covered matching desktop geometry, shared profile, tender create/edit/delete, chart filtering, theme switching and 390px mobile overflow.

## v3.0 visual refinement

Estimator’s swap icon and shared profile initials use teal. Tenders headings match Estimator’s title size; profile and topbar dividers are removed. Dark-mode calendar dates, tabs, hovered rows and navigation icons use contrasting foreground/background pairs. Dashboard order is Submission pipeline, Builder outcomes, Pricing feedback, Tender activity. New tender appears only on Dashboard; its date uses the full Sydney weekday/date without an icon.

Project and builder overviews now show a pricing-feedback segmented chart, consistent category colours, and selectable records for each pricing/outcome category. Builder awards and successful TEC quotes remain separate concepts; the lists identify the recorded builders and projects without inventing award authorities or named contacts. Frontend type checking, production builds and browser checks passed.

## v3.0 compact overviews and workspace polish

The Tenders browser tab now has its TEC favicon. Project/builder overviews contain one submission register with quote, TEC status, builder outcome and pricing feedback. Chart selections and the award metric filter that single register, replacing four repeated lists and the separate quote bars. Follow-up history is collapsed and long lists reveal 20 records at a time. The active filter resets when opening another project or builder.

The table now uses one hover background with no competing row/cell colour transition. Rounded cards, buttons, heading layout and border colours match the Estimator style while keeping the Tenders yellow accent. Latest chase-up and next reminder are indexed once per dataset change rather than searched/sorted for every rendered row.

Validation: TypeScript, production builds and Estimator startup regression checks passed. Browser checks covered favicon delivery, stable pointer-hover geometry/colour, overview filtering, tender opening, both coloured workspace wipes, reduced-motion and mobile dashboard width. No production hosting latency claim is made.

## Search and outcome badges

The header search appears only on Dashboard. Type a query and press Enter or the search icon; results open in Search Tenders, where the local search remains available. Local project, builder and tender searches use the same case-insensitive category matching. Open/OPEN/Open return recorded open submissions; Awarded, Won, Competitive, High, Closed and other category values work similarly. Exact category queries do not match incidental words in historical notes.

Builder awarded uses a blue badge; TEC won uses a green badge. A record can carry both independently. Workspace transition titles now show only TENDERS or ESTIMATOR, with a one-second wipe.

## Estimator switching and calendar performance update

Estimator now fetches its session, settings and dashboard in one authenticated bootstrap response while scripts load. The response supports gzip. Catalogue overview reads use the existing cache with database-change invalidation. Loading preserves the desktop sidebar; workspace clicks immediately display progress while navigation is pending. The one-second destination transition remains. The Tenders profile-photo and initials borders are yellow. Timeout limits have not been increased.

Calendar project details now open their dialog immediately and fetch only project metadata, access options and activity in one request. They no longer calculate or download all estimate lines. Read-only detail refreshes use the same smaller endpoint. Opening the actual estimate still fetches the latest estimate and checks access.

Validation: full existing Python suite (124 tests), the added calendar detail/authentication test, startup checks, TypeScript, and browser checks with delayed navigation, failed startup/retry, both workspace switches and a delayed calendar details request passed. Live hosting response times remain unverified.

## Concurrent-user load and startup recovery

Board totals are cached by a fingerprint of every calculation input read from the current database snapshot. Identical concurrent reads share one calculation. The bounded cache stores numeric totals only; permissions and account data remain live. Direct component edits, transactions and rollback were verified against uncached results.

Presence updates run every 30–35 seconds instead of 10 seconds. Board and reminder refreshes run every 60–70 seconds; notes and read-only details every 30–35 seconds. Intervals are staggered across tabs to reduce simultaneous request bursts. Explicit saves and navigation still request current information.

After 20 seconds of startup delay, a reload option appears. Tenders bootstrap has a finite 90-second limit, matching Estimator; timeout limits were not increased. A Tenders rendering failure preserves the navigation shell and shows recovery instead of a blank root. Slow API requests over two seconds now log method, route (without query data), worker process ID and elapsed time to the Python error log. Server-Timing headers measure application processing; they cannot measure time queued at the hosting proxy before a worker receives the request.

Validation: existing 125-test Python suite, two additional concurrent totals/edit/rollback tests, transport checks, TypeScript, and browser switching/calendar/failed-bundle/render-error recovery checks passed. The concurrent cache test used 16 reads across eight threads and verified one calculation. These local tests do not measure live hosting capacity.

If freezes continue, capture the Python application error log and hosting CPU/memory/process-limit readings while several accounts are using the site. Do not replace the live database or increase worker limits blindly.

## v3.1 — 29 September refinement

- Project Board defaults to Newest created; deadline ascending/descending keep undated projects last. The selected order is remembered per user.
- Removed the separate Reviews due this month list. Review stamps and Keep on Schedule remain.
- Light Price supports multiple supplier checkboxes. Search and pagination match any selected supplier, including suppliers of package components. Clear the filter with All suppliers.
- Search Tenders is merged into Project Chase-up with search, status/region/builder filters, dashboard chart drilldowns, tabs and Excel export. Existing /tenders/search links open Chase-up.
- Edit estimate item includes three independent Exclude mark-up checkboxes: Material, Labour hours and Final. All are unchecked by default. They affect only this estimate item, persist when copied, are recorded in revisions and apply to Excel formulas. Fixed labour prices do not gain labour-hour markup.
- Schema 28 adds these three settings with defaults that preserve existing totals. Startup makes a protected backup and migrates the existing database; no database file is shipped.

Deploy the changed files over the previous v3.1 release and restart Passenger. Do not replace the live database. Old fingerprinted frontend assets can be removed after cached sessions have expired; the updated HTML references the new files.

## v3.1 — 30 September search and alignment fixes

- Project Board list view uses stable columns for status badges, item counts, quoted totals and Open Estimate buttons.
- Supplier selector has a live Search suppliers field. Hidden supplier selections remain selected while searching other names; All suppliers clears the selection.
- Estimate autocomplete no longer stops at eight results: title matches are paginated with Show more matches and a visible result count. Quick Search and Catalog Explorer also allow loading subsequent matches. Matching remains case-insensitive and respects category/incomplete-item filters.
- Database schema remains 28. No live database is included or replaced.

## v3.1 — deployment health and complete title matching

The deployment log reported healthy schema 28/release 3.1 but the workflow still expected schema 27. Health validation now reads CURRENT_SCHEMA and the release from the deployed checkout's code. This removes the false failure and its 18 retries. The new isolated-process runner executes all unittest modules with four workers; no test gate is skipped. Removed the unnecessary pip self-upgrade.

Catalog grouping now preserves different item titles, categories and work types even when allowances match. This prevents a broad isolator search hiding surface-isolator titles that appear in a narrower search. Additional autocomplete results load automatically near the bottom of the list; a visible count and manual Show more fallback remain.

Push .github/workflows/deploy-cpanel.yml and tools/check_deployment_health.py and tools/run_tests.py together with the rest of the patch. Schema remains 28; no database changes.

## v3.1 — optional importance stars and search visibility

- Catalogue items support an optional shared importance rating from 1–5, coloured #D3AF37. Default 0 means unstarred; Clear stars removes the rating. Existing-item stars save immediately and separately from estimate/catalogue cost edits, so closing the editor does not undo a saved star selection. New-item stars save with the new item. All users see the same catalogue rating.
- Star controls appear beside + Detail row in both item editors. Saved stars appear in autocomplete, search results, Catalogue Explorer results and its details panel. Ratings never change prices or estimate quantities. Identical grouped catalogue records retain the highest-rated representative.
- The marked estimate search field has a more visible background/border in light and dark modes. The overall themes remain unchanged.
- Result columns, star controls and catalogue header actions align consistently and wrap for mobile screens.
- Removed Show records needing prices from Catalogue Explorer. Its previous default priced-item filter remains in effect.
- Schema 29 adds the optional rating with an unstarred default. Existing estimates remain unchanged; migration creates a protected backup. The deployment health check already reads the schema from code and needs no schema-number edit.

Validated with 143 backend tests and desktop/mobile browser checks covering set/clear/reload, both editors, search/detail displays, new item creation, colours, alignment and unchanged estimate costs.
