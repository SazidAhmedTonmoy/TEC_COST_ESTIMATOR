<div align="center">

# ⚡ TEC ConEst

**Electrical estimating · Tender intelligence · Team collaboration**

**Release 3.6** · Python 3.11 · SQLite · JavaScript / React · Responsive web app

**One sign-in. Two connected workspaces. One source of project truth.**

[Quick start](#quick-start) · [Use the app](#daily-workflows) · [Operations](#production-deployment) · [Backups](#data-and-safety) · [Troubleshooting](#troubleshooting)

</div>

---

## At a glance

| ⚡ Estimator (teal) | 🟡 Tenders (gold) | 🛠 Platform |
| :--- | :--- | :--- |
| Take-offs, assemblies and rate build-ups | Opportunities and deadlines | Shared accounts, roles and sessions |
| Lighting supply / install split | NSW and VIC regions | Private team assignments and alerts |
| Sections as included or optional cost | Approvals, quotes and follow-ups | SQLite backups, migrations and audit trails |
| Catalogue and supplier price checks | Builder outcomes and project chasing | Secure GitHub → cPanel deployment |
| Editable estimates, revisions and exports | Import/export of opportunities | Readable mobile experience and responsive layouts |

> **Data first:** Neither release ZIP contains your live project databases. Deploy code without replacing `data/`, `.env`, `passenger_wsgi.py`, `.htaccess`, uploads or existing backups.

## Contents

1. [What changed in 3.6](#whats-new-in-36)
2. [Quick start](#quick-start)
3. [Daily workflows](#daily-workflows)
4. [Opportunities and quotation decisions](#opportunities-and-quotation-decisions)
5. [Estimator costs and Excel](#estimator-costs-and-excel)
6. [Accounts, teams and permissions](#accounts-teams-and-permissions)
7. [Architecture and files](#architecture-and-files)
8. [Production deployment](#production-deployment)
9. [Data and safety](#data-and-safety)
10. [Performance and mobile](#performance-and-mobile)
11. [Tests and release verification](#tests-and-release-verification)
12. [Troubleshooting](#troubleshooting)
13. [Condensed release history](#condensed-release-history)

## What's new in 3.6

**Release 3.6** brings together the shared Estimator/Tenders sign-in experience, mobile navigation consistency, responsive Tender dashboards and the performance/documentation improvements introduced during the preceding 3.5 development series. This is a release-label and README update only; application files must be versioned separately if you want the running server to identify itself as 3.6.

- **Login controls:** hide Estimator-only floating controls while login, loading or non-estimate screens are active. This corrects the intermittent stray round minus button on the login screen.
- **Estimator phone navigation:** the Menu button now opens a full-height **slide-out drawer**, matching the Tender workspace. The navigation is one column; the profile and sign-out controls remain at the bottom. Tap outside, choose a page, press Escape or resize to desktop to close the drawer. The drawer no longer expands the page and pushes estimating controls downward.
- **Tender dashboard cards:** replaced the mobile sideways-scrolling KPI strip with a **two-column grid**, matching the Estimator Home metrics. Other dashboard charts and tables remain inside responsive wrappers, with deliberate internal horizontal scrolling only for dense data tables.
- **Cross-workspace mobile audit:** updated touch sizing, modals, filters, cards and form constraints for the 320–820px range. The original Tender source and the **already built website CSS** both include the changes, so deploying does not require rebuilding npm dependencies.
- **No business-logic or schema changes:** current approval, quote, costing, import, security and audit rules remain as they were. Database schema remains **32**; no data reset or migration is introduced.

### Deployment guidance for 3.6

For an application rollout of this documented release, use the complete application package or a verified update package appropriate to the exact existing installation. A README-only update does **not** change executable files, built assets, or the runtime version. Upload all changed `assets/` and `tenders_web/` browser files alongside source changes, preserve `data/`, your `passenger_wsgi.py`, uploads and environment settings, and restart Passenger. Hard-refresh the browser to replace cached CSS; the new Estimator JS has a new content fingerprint to prevent stale code. Confirm `GET /api/health?check=tenders` reports **schema 32** and the correct **running application version** (3.6 once the application version metadata is also updated).

## What's new in 3.5.11 (historical)

- **Shared sign-in:** removed Estimator-only subtitle; both Estimator and Tenders now have equal billing. Three locally bundled electrical-design blueprint illustrations rotate every **3 seconds**, with tender/estimate/team messaging and teal + gold accents. Slide controls can be clicked; animation pauses in hidden tabs and honours reduced-motion settings.
- **Mobile usability:** additional CSS layouts for both apps across phones/tablets, including navigation, cards, filters, catalogues, forms, modals, responsive totals, touch targets and table scrolling. Dense data tables intentionally remain scrollable rather than hiding columns.
- **Performance:** large public `.js`, `.css` and `.svg` files served by the Python app are gzip-compressed and cached by content mtime; private exports and API data are excluded. Estimator GET requests recover once from certain transient network/gateway failures; mutations are never retried automatically. Unnecessary background brief refreshes are reduced. Tender continues using its existing paginated and lazy-loaded views.
- **Documentation:** release-note TXT/MD files, quality reviews and old manifests have been consolidated into **this README**. Historical milestones are summarized below. The optional cleanup utility lists legacy documentation it can safely remove on an existing manual installation.
- **No database schema change:** schema **32**; no new opportunity reset, migration or data deletion introduced by this release.

### What's unchanged

Existing opportunity approval/expiry business rules, quote-to-Chase-up linking, category inclusion/optional costs, permissions, tender and Estimator data, and database backups are unchanged. Desktop theme colours remain teal for estimating and yellow/gold for tenders.

## Quick start

### Requirements

- Python **3.11 recommended** (minimum supported 3.10); dependencies from `requirements.txt`.
- Node.js **22.13+** when you need to rebuild the React Tenders frontend.
- SQLite included in Python; host runtime must support the operations checked by `tools/check_runtime.py`.
- Modern desktop/mobile browser. A local filesystem for SQLite storage; network-mounted SQLite files are not recommended.

### Windows

1. Extract into a project folder outside system-protected directories.
2. Run **`START_TEC_SERVER.bat`** and allow Python dependencies to install.
3. Open `http://127.0.0.1:8080/`.
4. Use the administrator setup/sign-in details from your existing installation. Change any initial credentials.

### Linux / macOS

```bash
sh run.sh
```

Or use a dedicated Python environment and your existing application startup:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python app.py --help
```

Start with the appropriate supported option for your hosting environment. The full UI and uploaded data are available only after the server has been started successfully.

### Navigation

The landing page is the **shared TEC ConEst login**. After signing in, switch between **Estimator** and **Tenders** using the app's workspace control; account/profile permissions carry across. Estimator is at `/`, Tenders is at `/tenders/`.

## Daily workflows

### Estimator

1. **Home:** see project status, due dates, notes and board filters; create or open a project.
2. **Estimate:** add catalogue items, adjust quantities, material/labour/markup, and create or edit components. Category switches determine whether their values count as included or optional costs; no component data is deleted by switching off.
3. **Catalog:** search and modify reusable item assemblies, preview duplicates, and import source workbooks.
4. **Light Price:** compare supplier lighting fittings and associated installation/supply components.
5. **Calendar and reminders:** review submission and internal review deadlines; dismiss visible individual reminders.
6. **Export Excel:** receive connected totals and item-level details, including optional costs.
7. **Project JSON:** transfer projects/revisions through the supported import/export workflow; review imported content before applying.

### Tenders

1. **Dashboard:** open submissions, awards, outcomes, pricing feedback, tender activity and project values.
2. **Opportunities:** create potential jobs, select region, deadline, builders, scope, estimated tender value, distance origin and URL; preview an Excel import.
3. **Projects and Project Chase-up:** link submitted quotes to builder records, assign follow-ups and capture builder feedback/outcomes.
4. **Builders:** manage the directory and builder-specific submission history.
5. **Calendar and reminders:** keep track of tenders and follow-ups.
6. **Notifications:** assignment and reminder alerts share one inbox with per-user read state.
7. **View Contribution:** administrators can review recorded Estimator/Tender/Opportunity actions for staff within the available reporting window.

## Opportunities and quotation decisions

### Fields and multiple builders

Each opportunity can contain project name, NSW/VIC region, site/location, closing date, builder(s), working scope, category, budget range, estimated tender value in AUD, optional link, notes, and optional distances. Each region has a configurable origin; the initial defaults are:

| Region | Distance origin |
|---|---|
| NSW | 63–79 Parramatta Rd, Silverwater NSW 2128 |
| VIC | CBD, Melbourne |

Distances are **entered/imported**; the route link is for manual road-distance checking, not an automatic calculation. A new builder name can be retained for future suggestions. Contact persons are not single fields on the opportunity because several builders may participate.

### Initial opportunity seed and one-time reset history

The packaged `opportunities_seed/seed.json` intentionally contains **no opportunity projects**. Automatic replay of the original NSW/VIC source workbooks was removed in v3.5.1. The owner-requested legacy register clear was implemented as a guarded one-time operation: before first reset, the application takes a verified Tender SQLite backup under an `upgrade_backups/` path. Later compatibility releases preserve connected historical records and audit/contribution data while retiring the old register from active searches and counts. Once the reset marker is committed, manually created and imported projects persist across subsequent restarts. **v3.6 does not trigger or repeat that reset.** Restoring a backup taken before the reset needs a deliberate migration/recovery plan, otherwise older projects can become active again or the reset can run when the store initializes.

The new blank import template contains an `Opportunities` sheet and `Instructions` sheet; imports add missing records but do not bypass admin/team approval. Original uploaded cell values and source decisions remain available as source notes where supported; an imported status does not automatically approve a project.

### Status and actions

- **Awaiting approval:** team members who meet approval permissions or admins can approve/reject; rejection note is optional.
- **Assigned team:** automatically approves the opportunity, even if its date has passed.
- **Approved:** stays approved after its deadline; expired-date items retain normal grey deadline labels and do not get a Reject button.
- **Expired:** deadline has passed without approval; existing controls follow current approval permissions. Expired cards and details **do not show Reject** (since 3.5.10).
- **Quoted:** for an eligible current approved opportunity, enter electrical submission value and relevant builder(s); linked submissions are created in Chase-up. A recorded quote preserves its Chase-up link.
- **Not quoted:** for an eligible current approved opportunity, moves it to Rejected with optional note.
- **Reopening:** extending the deadline may return an unapproved expired record to Awaiting approval; existing approval remains approved.

The server records actor, time, and action. Do not use browser-only UI hiding as an authorization boundary; server permissions must also apply.

### Opportunities Excel template

Use **Opportunities → Import Excel → Download template**. Enter one opportunity per row; multiple builders are entered on separate lines in the same cell. Use genuine Excel date cells or `YYYY-MM-DD`. The workbook includes **Link**, not a single shared contact/email pair. Import preview reports added, duplicate and invalid rows; existing opportunities are not silently overwritten.

## Estimator costs and Excel

### Included vs optional sections

Each estimate category has a switch, initially enabled. When off, its quantities, units, component prices and markups remain visible but **do not contribute to the included estimate total**. Export and share views identify excluded categories as **Optional cost** with a separate optional subtotal, including labour and material components. Switching on restores the cost to the included estimate.

### Lighting supply and installation

Lighting and Emergency/Exit lighting items can have project-specific supply values. Supply/installation and relocation/demolition breakdowns appear in the quoted summary and exported workbook. Catalogue components and recurring rates are not silently overwritten by a project-specific supplier price.

### Estimates, copies and revisions

The Estimate page supports project revisions, copying projects, shared team access, notes, search, category reordering, markups and rates. Changing a local estimate can be saved back to that project without overwriting the catalogue unless the user explicitly chooses a catalogue operation. Store full backups before making bulk changes.

## Accounts, teams and permissions

- Authentication is shared by both workspaces. Admins manage people, roles, teams and application settings from Estimator.
- Opportunity **creator or administrator** controls assignments, deletion and editing-access delegation. Delegated editors can edit details but are not automatically granted administrative powers.
- Eligible active members of a team and admins can approve awaiting opportunities.
- Assignment notifications are sent to assigned people and teams. Viewing notifications marks them read for the individual user.
- Quoted submissions and opportunity activity are recorded for audit and contribution; automation is not attributed to a human.
- Sessions, passwords, passwords changes and CSRF protection are server managed. Never commit API keys, password databases or `.env` files.

## Architecture and files

| Folder/file | Purpose |
|---|---|
| `app.py` | Python HTTP application / API and static asset delivery |
| `passenger_wsgi.py` | Hosted WSGI adapter; **server-specific, preserve on deployment** |
| `conest_app/` | Estimator, Tender, catalogue, opportunity, storage, reporting, auth and export logic |
| `assets/` | Estimator markup, source JS/CSS, local login SVG slides and compiled browser assets |
| `tenders_frontend/` | React / TypeScript source and npm dependencies |
| `tenders_web/` | Compiled Tender page and assets for direct serving |
| `templates/` | Downloadable Excel import templates |
| `tenders_seed/` | First-time Tender initialization seed (not production data) |
| `tools/build_frontend.py` | Rebuild fingerprinted Estimator JS/CSS from sources |
| `tools/check_runtime.py` | Verify required host Python and SQLite behavior |
| `tools/run_tests.py` | Run Python test modules with isolated temporary databases |
| `tools/prune_legacy_docs.py` | Optional **dry-run-first** cleanup of pre-3.5.11 documentation files |
| `.github/workflows/deploy-cpanel.yml` | CI build, test, code upload, Passenger restart, readiness check |
| `data/` | Live runtime data; never deploy a replacement from a ZIP |

### Database layout

`data/conest_catalog.db` holds core accounts, estimator projects, catalogues, supplier prices and settings. `data/tec_tenders.db` holds Tender submissions, opportunity records and associated histories. A host may override these using `CONEST_DB_PATH` and `CONEST_TENDERS_DB_PATH`.

**One-time schema migrations are not seed imports.** Keep live databases in place; first startup may perform a guarded upgrade and record its completion. Current release adds **no migration**, and the application schema is **32**.

## Production deployment

The established site is `https://tec-const.ampecportal.com/` and the existing app directory is:

```text
/home/ampecportal/tec-const.ampecportal.com/
```

### GitHub → cPanel (recommended)

1. Back up **both** live databases and relevant uploads, then confirm your Git working tree.
2. Commit code changes to the existing repo; do not create another repo or push runtime databases.
3. Push to `main`; GitHub Actions uses Python 3.11 and Node 24 to build/test and sync over SSH.
4. Check the **Deploy production** run through upload, dependency install, restart and deep readiness check.
5. Open both workspaces after the health check; hard-refresh to load the new frontend assets.

| GitHub Actions secret | Function |
|---|---|
| `CPANEL_HOST` | SSH host |
| `CPANEL_USER` | SSH user |
| `CPANEL_SSH_KEY` | Private key for code upload |
| `CPANEL_SSH_PORT` | SSH port, if not 22 |

The rsync workflow uses `--delete` for tracked code files but excludes `data/`, environment configuration, runtime databases, `.htaccess`, `.well-known`, `passenger_wsgi.py`, and virtual environments. It does **not** configure your Passenger interpreter. The live host was previously configured to use:

```text
/home/ampecportal/tec-conest-py311/bin/python
```

The deployer's Python is not the hosted Passenger Python. Confirm the interpreter shown by a fresh diagnostic rather than assuming it changed because the GitHub step used Python 3.11.

### Manual ZIP update

- Use **CHANGED_FILES** ZIP only when the destination is confirmed to be the immediately previous complete release. Otherwise use **FULL** ZIP.
- Extract the inner `TEC_COST_ESTIMATOR/` contents over the application root, preserving relative folders.
- Keep the live `data/`, `.env`, uploads, server-managed WSGI configuration and virtual environment unchanged.
- The compiled Estimator (`assets/`) and Tender (`tenders_web/`) UI files **must** be uploaded with source files. Manual hosting does not require npm if compiled assets are included.
- Restart Passenger from the application root using the hosting panel or:

```bash
mkdir -p tmp
touch tmp/restart.txt
```

Then check [deep production readiness](https://tec-const.ampecportal.com/api/health?check=tenders). Expected schema is `32`; the release field will show `3.6` **only after executable version metadata and deployment are updated**. Success includes checks for `tenders`, `opportunities`, `timezones` and `sqlite`.

### Aligning release identifiers

This file documents the combined feature release as **3.6**. **Only `README.md` is delivered with this request**: copying it onto the host will not change the running application build (which may still report `3.5.12`), its assets, or the database schema. When publishing code as release 3.6, update the application version constant, built frontend references and CI/release metadata together, then verify the health endpoint. Do not edit production databases simply to change the displayed version.

### Building frontends locally

```bash
python tools/build_frontend.py
cd tenders_frontend
npm ci
npm run build
```

On build machines without Node dependency access, **do not overwrite the supplied prebuilt Tender frontend with incomplete build output**. The changed CSS in `tenders_frontend/src/mobile-v3511.css` is also shipped as a prebuilt compatible CSS asset for this release.

### Retiring old document files

Older releases accumulated `UPDATE_*`, `QUALITY_REVIEW_*`, `CHANGED_FILES_*`, `V*_FILE_MANIFEST.json` and separate Tender release notes. This single README now contains the operational guide and condensed history. New archives do not bundle those root documents.

For a **manual ZIP update** those old files may remain on the host because extracting an archive does not delete files. Review the safe dry run first:

```bash
python tools/prune_legacy_docs.py
python tools/prune_legacy_docs.py --apply
```

The cleanup only targets known legacy *root documentation filenames*, not live databases, uploads, scripts or this README. When deploying via rsync with `--delete`, removed repository documents are deleted automatically.

## Data and safety

- Always back up **both** databases before code upgrades or resets; preserve your production uploads and config too.
- `data/backups/` contains core database snapshots, `data/tender_backups/` Tender snapshots. Some schema migrations have their own `upgrade_backups` safety copies; those are separate from routine retention.
- Routine backup retention typically keeps the latest successful set; export important checkpoints to external storage if you need longer history.
- Restore only using supported app tooling and after verifying backup integrity and that the administrator account exists. Restores can sign users out.
- SQLite: do not copy an active `.db` file while ignoring its WAL/journal state. Prefer the SQLite backup API or the supplied backup tools.
- Do not disable SQLite foreign keys or manually delete connected opportunity tables to work around migration errors.
- Keep permissions least-privileged. Never publicly expose diagnostic endpoint payloads or `.env`/database folders.

## Performance and mobile

**Performance work in this release:** static assets compressed/cached by mtime; read-only transient retries; fewer broad background-refresh operations; off-screen long lists may use browser rendering containment; existing Tender pagination and request dedupe remain in place. `Server-Timing` / slow-request logs help identify slow API endpoints on your own server.

**Mobile design:** form controls are readable at phone font size, touch targets have comfortable height, dialogs scroll within the viewport, and dashboards/filters/cards reflow to one or two columns. Very wide estimate and tender tables **scroll horizontally** because squeezing or hiding financial columns risks misquoting. In the Estimator, the mobile menu contains the full navigation; in Tenders, the sidebar sheet and topbar adapt to the viewport.

**Limitations:** app/server capacity and intermittent hosted 5xx errors depend on the deployed Passenger environment, SQLite locking, database size, hosting I/O and network. The release cannot guarantee zero latency or eliminate unknown hosting faults; check the health endpoint and startup diagnostics when a failure appears.

## Tests and release verification

From the application root:

```bash
python -m compileall -q app.py conest_app
python tools/run_tests.py --workers 4
python tools/build_frontend.py
# For Node-installed environments:
cd tenders_frontend && npm ci && npm run build
```

**3.6 feature baseline verification (22 October 2026):** **400 Python tests across 54 modules passed**, including migrations, approvals, quotes, import/export and schema-readiness regression checks. **27 JavaScript tests passed** with Node's TypeScript stripping enabled. Static server requests verified the newly fingerprinted compiled Estimator JS, both new mobile CSS files and Tender landing HTML. Chromium fixture checks covered **94 navigation/login/KPI assertions**, **36 Estimator view/viewport no-overflow checks** (nine views at four widths), and Tender Opportunities at 320, 390, 768 and 1280px with no page-level horizontal overflow. The Estimator drawer screenshot was reviewed at 320 and 390px; Tender dashboard 2x2 metric cards were reviewed at those widths. The login regression explicitly tested stray controls even when a stale UI state removes their original `hidden` class.

**Verification limits:** Mobile checks use browser fixtures with the real shipped HTML/CSS and interaction scripts. They do not assert that every live authenticated route, form or hosting integration is flawless. The Tender React/Vite bundle was **not rebuilt** in this offline environment (npm dependencies are unavailable); the patch includes a production-served CSS override that takes effect without npm, as well as the updated React source import for future connected builds. Local tests do not replace a post-deployment smoke test using your real accounts and data.

**v3.5.11 local verification (historical):** **396 Python tests in 53 modules passed** using Python 3.13.5 and SQLite 3.46.1; **37 JavaScript tests passed**. The source Estimator bundle passed Node syntax checks and the static gzip route passed its response/encoding checks. Self-contained Chromium checks of the login passed at 320, 390, 768 and 1280 px, including three-second rotation, manual dots, and reduced-motion; Tender layout fixture checks at the same widths found no document-level horizontal overflow. These are local tests, **not production hosting benchmarks or authenticated, end-to-end mobile tests of every Tender and Estimator page**. The React/Vite Tender bundle could not be rebuilt in this offline environment: the ZIP includes the existing compiled Tender bundle plus a validated external responsive CSS layer, and the React source imports the same layer for a normal connected CI build. Both data stores and live hosting remain untouched.

Quick integration checklist after deployment:

- Both login slides and manual slide dots work; teal/gold accents appear, no Estimator-only login subtitle.
- Open Estimator Home, Estimate, Catalog, Calendar, Imports, Users/Settings (as admin), and profile at mobile and desktop widths.
- Open Tenders Dashboard, Opportunities, Chase-up, Projects, Builders, Calendar and Reminders at mobile and desktop widths.
- Create an opportunity and estimate on a **test project**; export, edit and reload without data loss.
- Test permission boundary using a non-admin account; notification read state stays per user.
- Confirm `https://tec-const.ampecportal.com/api/health?check=tenders` reports schema `32`, the deployed application version, and all checks `ok`.

### GitHub Actions: Tender CSS build validation

The deployment workflow runs `npm ci && npm run build` for Tenders **before** Python tests. Vite bundles the `mobile-v3511.css` and `mobile-v3512.css` imports into a generated stylesheet named like `index-<hash>.css`; it may remove the old separately copied CSS files while cleaning `tenders_web/`. The two mobile release tests now inspect the stylesheet link in the **built Tender HTML** and verify that the responsive rules are actually present, rather than requiring obsolete filenames. This keeps the protection against missing mobile styles while supporting production builds.

To reproduce the deployment sequence in a connected development environment:

```bash
cd tenders_frontend && npm ci && npm run build && cd ..
python tools/build_frontend.py
python tools/run_tests.py --workers 4
```

If a test fails, the runner repeats its failure details at the bottom of the GitHub Actions log and adds an error annotation. **Only the CI test/build verification changed in this hotfix**; application version metadata remains `3.5.12` until an explicit executable 3.6 release is made.

## Troubleshooting

| Symptom | What to inspect |
|---|---|
| `TENDERS_STARTUP_FAILED` / HTTP 503 | `/api/health?check=tenders` and (admin session) `/api/admin/startup-diagnostics?reference=<error_reference>` |
| Hosted runtime differs from CI | Diagnostic `runtime.python_executable`; Passenger's interpreter setting |
| `sqlite3.OperationalError` or foreign-key failure | Error traceback, database schema, failed migration; preserve a backup before repair |
| Page works locally but not hosted | Compiled asset upload, Passenger restart, app root, environment and `.htaccess` |
| Login shows an older version | Hard refresh, verify HTML asset fingerprint, restart Passenger, avoid stale service cache |
| CSS or mobile layout missing | Check both `assets/` and `tenders_web/`, and the new mobile CSS asset |
| Excel import invalid | Keep template headings and true date cells; preview errors before applying |
| Large tables on phones | Scroll the table region horizontally; summary cards retain compact values |
| Slow requests | Check `Server-Timing`, backend slow-request output, DB size and concurrent worker count |
| No `stderr.log` | cPanel may route logs through Passenger/Apache; admin startup diagnostics capture some startup failures |

Production health only confirms application readiness; it is not a guarantee that every form and integration is error-free. If a problem persists, provide the fresh error reference and relevant redacted diagnostic/traceback.

## Condensed release history

| Release | Major themes |
|---|---|
| **3.6** | Consolidated shared Estimator/Tenders login and mobile release: drawer navigation, hidden login floating controls, Tender KPI 2x2 grid, responsive checks, performance and documentation cleanup |
| **3.5.11** | Shared login carousel, mobile coverage, static delivery and refresh improvements, consolidated docs |
| **3.5.10** | Removed Reject actions from Expired cards/details |
| **3.5.9** | Neutral regular-weight deadlines for decided/expired records; no Reject on Approved |
| **3.5.8** | Optional costs correctly separated in Excel/shared links; refined expired actions and deadline presentation |
| **3.5.7** | Team assignment auto-approval, quote/Not quoted to Chase-up, inclusive category switches |
| **3.5.6** | Migrated legacy `creator_id`, added opportunity Link, countdown and updated import template |
| **3.5.5** | Safer opportunity register retirement respecting linked foreign keys |
| **3.5.4** | Legacy builder table migration |
| **3.5.3** | Missing `deleted_at` migration and Python interpreter check |
| **3.5.2** | Private admin startup diagnostics |
| **3.5.1** | Hosting diagnostic/readiness, initial opportunity reset and Excel template |
| **3.5** | NSW/VIC opportunities, team assignments, history, integrated Tender navigation and notifications |
| **3.4** | Tender opportunity import, reporting/search and UX refinements |
| **3.3 / 3.2 / 3.1** | Shared login, tender integration, approval/review, mobile/dark theme |
| **2.4–2.0** | Estimator speed improvements, project/role management, catalogue and supplier price consolidation |
| **1.x** | Core cataloguing, estimates, quantities, pricing and project workflows |

---

<sub>TEC ConEst is a private operational application. This repository's code and documentation do not include production passwords or databases. Keep releases and user access within authorised company systems.</sub>
