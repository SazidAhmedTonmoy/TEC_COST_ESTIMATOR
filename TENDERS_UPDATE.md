# TEC ConEst v3.0 — deployment and database guide

Extract the changed-files ZIP into the existing TEC ConEst application folder and replace matching files, then restart the Python app / cPanel application. Keep the existing `data/` directory. The full ZIP is the complete source alternative. Neither package replaces your estimator database. Compiled frontend assets are included; Node is not required on the hosting server.

Use the small circular-arrow button beside **Estimator** to open **TEC ConEst Tenders**. The reverse button returns to Estimator. Both use the same sign-in, users, profile photo, password rules and light/dark preference. Tenders uses a yellow accent. Profile is shared. Manage Users and App Settings are accessed from Estimator; Tenders has no separate links to them. The old tender-only Settings page is removed.

## Existing tender database

If you have used the standalone tender app since this ZIP was created, stop that standalone server and copy its `data/tec_tenders.sqlite3` into the estimator's `data/` directory before first opening Tenders. Keep any SQLite sidecar files with it if they remain after shutdown. The application makes a consistent SQLite backup into `tec_tenders.db`; it keeps the original `.sqlite3` file. If a `tec_tenders.db` already exists, that existing database is used.

The uploaded ZIP contained seed JSON, not a live SQLite database. A new installation initialises **291 submissions and 332 recorded chase-ups** from that seed. It does not insert them again on subsequent starts. Estimator data remains in `conest_catalog.db`; tender records live separately in `tec_tenders.db`. Both are SQLite databases. Optional `CONEST_TENDERS_DB_PATH` overrides the tender path.

Tender daily snapshots are retained separately in `data/tender_backups/` (latest one). The existing App Settings database restore applies to the estimator database, not to the tender database. Keep both databases in your server backup plan.

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
