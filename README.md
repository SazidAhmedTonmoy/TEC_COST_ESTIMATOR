# Current release: v3.4

See [UPDATE_V3.4.md](UPDATE_V3.4.md) for the latest Tenders mobile layout, full-width pages, sorting and grouped filters, editable submission teams, monthly reporting, overview navigation, and Estimator Expand All / Shrink All. The release retains Estimator schema 31 and safely migrates missing Tender team labels.

Latest UI/chat patch: simplified View Contribution; five progress cards in one row; equal Help buttons, Normal/Project chat switch and composer model selection.

Previous v3.3 patch: live rate/mark-up autosave; two historical Excel uploads credited to Tonmoy without crediting imported submissions as work; Closed progress excluded from calendar totals; redesigned Help with inline attachments, memory settings and keyboard shortcuts. See UPDATE_V3.3.md for deployment and verification.

See [UPDATE_V3.3.md](UPDATE_V3.3.md) for attribution, editable chase history, per-person contributions and deployment instructions. The 8 October v3.3 update uses estimator schema 31; it adds View Contribution date ranges, Help memory/files and cross-tab copy/paste.

# v3.2 release — October 2026

The last three updates form v3.2:
- Project JSON import/export and example; component copy/paste; This month filter.
- Coloured JSON transfer cards; replaceable clipboard with copied-item label; This month default.
- Approved Blueprint split login with responsive layout and reduced-motion support.

Database schema remains 29. Existing migration names and data are preserved.

## Tender Excel update — 5 October 2026

- Dashboard: **Import Excel** sits beside **+ New tender**. Preview new, updated and unchanged submissions before importing.
- Accepts `.xlsx` and `.xlsm` files with the original **Raw Data** layout, or a TEC **Tenders** export. VBA macros are never executed.
- Uses Submission ID when supplied; otherwise matches project + builder (case and extra spacing ignored). Row order is not an identifier. For name changes, use the exported Submission ID; renaming an original-workbook project/builder is otherwise treated as a new submission.
- Adds new records, updates changed imported fields and skips unchanged rows. Previous imports establish a baseline so unchanged Excel cells do not undo later app edits. Changed workbook values take precedence when applied.
- Imports dated chase history and exported scheduled reminders. Existing records, notes and reminders absent from the workbook are preserved; importing is not a deletion operation.
- Conflicting duplicate rows or ambiguous matches stop the import. Changes apply together in a database transaction. If another user changes tender data after preview, preview again.
- Import limit: 15 MB / 20,000 submissions. Formulas must have saved results: recalculate and save in Excel before uploading if prompted.
- Export: a visual overview with separate TEC-outcome, builder-outcome and pricing-feedback charts; clearer KPI totals, status colours, striped rows, value bars, readable dates, filters and frozen headers. Technical IDs remain in hidden columns for safe reimport.
- Project value counts the highest quote for each project once. Builder awards and TEC wins are separate measures.

**Deployment:** apply the changed-files ZIP over the latest Blueprint-login release, retaining folder paths, or use the full v3.2 ZIP. Deploy code and restart Passenger. Do not replace or delete live `.db` files. No new package dependency or estimator schema migration is required; import baselines are stored in the existing tender settings table. Built Tenders assets are included.

**Checks:** import idempotency, original-workbook row reordering, additions and updates, history/reminder preservation, duplicate rejection, concurrent edits, authentication and CSRF, export structure and totals, native charts, desktop dark and mobile light import flow. Visual previews were checked; desktop Microsoft Excel was not available in this environment.



# Tenders integration

See [TENDERS_UPDATE.md](TENDERS_UPDATE.md) for the shared-login workspace, database migration and update instructions.

# TEC ConEst · v3.4

### Electrical estimating, connected costs and team collaboration

A shared estimating workspace for catalogue assemblies, project quotations, supplier lighting prices and connected Excel exports. Built with Python, SQLite, a plain JavaScript Estimator and a React Tenders workspace, with a GitHub Actions workflow for the existing cPanel deployment.

| Estimate | Collaborate | Operate |
| :--- | :--- | :--- |
| Reusable assemblies and item build-ups | Shared projects, notes and activity | Separate estimator and tender `.db` files |
| Lighting supply and installation costs | Teams, account roles and revisions | Automated code deployment and database backups |
| Connected Excel quantities and totals | Searchable supplier quotations | Desktop, mobile and dark mode |

**Quick links:** [Start](#1-start-and-deploy) · [Daily use](#2-daily-use) · [Backups](#3-data-and-backups) · [Architecture](#4-architecture-and-pricing) · [Files](#5-file-guide) · [Release history](#6-release-history) · [Troubleshooting](#7-troubleshooting)

> [!IMPORTANT]
> Your deployed database is authoritative. Update application code without replacing production data with a ZIP snapshot. The workflow excludes the entire `data/` directory from synchronization.

## Previous release · v3.2

Major release: Estimator and Tenders share login, users, profile and theme. Switch with the circular-arrow control beside the brand. Tenders uses yellow accents and now matches Estimator's desktop sidebar geometry, typography and account controls. Its Workspace label and admin links are removed; user management and app settings remain in Estimator. A coloured title wipe reveals the destination workspace using a one-second transform animation; navigation and data loading start immediately, and reduced-motion users skip the wipe.

**Deployment and data:** read `TENDERS_UPDATE.md`. Keep live databases excluded from Git. Commit the code and `tenders_seed/seed.json`; the first Tender visit creates `data/tec_tenders.db` and imports the seed once. Subsequent deployments preserve live data. Replace `passenger_wsgi.py` manually in cPanel because the workflow deliberately excludes it. Restart Passenger. `/api/health` reports release `3.2` with estimator schema `29`; responses through the adapter report `X-ConEst-Adapter: 3.2`.

The v3.1 Passenger adapter retains one-time initialization, the idle estimator WAL connection, transport-header cleanup, exact response lengths and negotiated gzip. It also compresses eligible dashboard, reminders, tender JSON and public JavaScript/CSS/SVG when Python serves those assets; precompressed, partial and no-transform responses are left intact. Public tender pages and bundles skip estimator database initialization. No production latency guarantee is implied.

## Previous release · v2.4

Latest estimate-page update (r5): reorder acknowledgements contain only order/revision metadata and skip full estimate calculations. The UI moves rows immediately, prevents overlapping drag/copy actions and restores the previous order on save failure. Dragging onto a component row also targets its parent estimate item. Updated clients negotiate changed-line responses for item changes and copies; legacy clients still receive complete responses. Pricing-setting changes fall back to full results. Outdated mutation responses cannot replace a newer project revision.

Component detail rows render only when expanded, textarea sizing batches layout reads/writes, and successful manual edits no longer reload the dashboard and entire estimate. Catalogue reindexing updates changed metadata/preference rows instead of rewriting every item. Passenger r5 compresses large successful project/catalog mutation responses as well as GET responses; replace the standalone adapter and restart Passenger to enable this. The adapter header reports 2.4-r5.

Copy Estimate adds an unchecked “Start all estimate quantities at 0” option. It resets assembly quantities, clears independent supply-quantity overrides and zeros fixed-total component quantities; ordinary per-unit build-ups and unit prices remain reusable. Source estimates remain unchanged. No database split or new schema migration is needed. Validation includes 118 Python tests, extra catalogue checks, and frontend delta/order/rollback tests. Production latency still needs verification after deployment.

Latest update (r4): App Settings now controls the default “Save changes to” destination: estimate only (initial default), update catalog, or new catalog item. The dialog still lets the user override it, and falls back safely when no original catalog item exists. Defaults use the requested three-row order. The server now accepts and persists default labour-hour markup; the previous settings allowlist inadvertently omitted it.

The r4 Passenger adapter compresses large GET project/catalog JSON when the browser accepts gzip, maintains the actual transmitted Content-Length, and strips connection-specific transport headers before returning to Passenger. Responses include `X-ConEst-Adapter: 2.4-r4` and `Server-Timing`. Replace passenger_wsgi.py in cPanel and restart Passenger; the deployment workflow intentionally preserves that file. These measures reduce transfers and prevent forwarding invalid transport headers, but do not establish or fix every possible Apache, network or browser-extension cause of HTTP/2 resets. No production performance result is claimed. No additional schema migration is required for the new default.

Labour hour mark-up is stored as a fraction (10% = 0.1). Adjusted hourly labour = base hours × (1 + labour-hour markup). Labour cost, person-days, crew working days and quoted totals use adjusted hours; fixed labour prices are unaffected. Excel exposes the linked control in COST ESTIMATE!F7. Application Settings supplies the default for new projects. Existing project values default to zero.

The browser loads one CSS bundle and one deferred application bundle, with content-based filenames. Edit the source JS files or assets/styles.css, then run `python tools/build_frontend.py` before deployment. Old version-specific CSS files have been consolidated. Required historical database migrations remain. assets/.htaccess enables long-lived caching and compression when Apache serves assets directly; the Python server also caches fingerprinted bundles.

Replace passenger_wsgi.py manually in cPanel (the deployment workflow preserves it), then restart Passenger. It keeps an idle SQLite connection between requests and adds Server-Timing so application time can be distinguished from hosting/queue time in browser Network timings. The root .htaccess and production data remain untouched. These changes reduce repeated requests and database work; production hosting latency still requires verification after deployment.

Estimate searches prioritize matching catalog items most recently added to saved estimates, including existing usage history. Catalog Explorer keeps its normal ordering.

Refresh restores the requested page behind a neutral loading screen. Startup requests run concurrently, background board updates skip unchanged data, reminders avoid estimate calculations, and component reads use one query per project. Versioned static assets can be reused from the browser cache. The duplicate profile heading is removed. Identical pending reads share one request; neither reads nor saves are automatically replayed after failure. Background polls pause during foreground requests. Startup failures show a retry screen without treating them as logout. Project Board adds total-cost ordering within currency groups and offers Cards/List views. Schema 26 adds labour-hour markup, defaulting existing estimates to 0%.

Apply this changed-files ZIP over the previous v2.4 package and restart the app. Keep your production data folder. The health endpoint reports `2.4`. Regression checks cover startup, network failures, board sorting, calendar and Excel formulas. On the supplied four-project snapshot, calculation queries fell from 254 to 12 with byte-equivalent serialized results. This measures database work, not production hosting latency.

## Previous release · v2.3.6

A simpler project workspace with Cards, List and Compact views beside search. Each account remembers its view and sort order. Explorer-style View and Sort controls offer name, deadline, creation and update ordering. Keep on Schedule combines upcoming deadlines and unread reminders in one place. Project cards emphasize status, deadline, value and Open Estimate; secondary details expand when needed.

Copy Project opens an editable form with a blank deadline, preserving the source estimate’s items and rates. Import Files and My Profile use consistent labels, and the team refresh control is removed. New Project is available only on Build Estimate. Redundant refresh controls and board tabs are removed, while Newly added badges remain. The Manage Project dialog puts Open Estimate beside its summary. Rounded cards, clearer spacing and responsive controls work with both themes.

**Updating v2.3.5:** extract the changed-files ZIP into your existing app folder, replacing matching files. The full ZIP contains the complete application source. Both packages omit runtime data and Git history; keep your existing `data/` folder, server configuration and repository. Restart the app after updating. This release keeps database schema 25 and reports `2.3.6` at `/api/health`.

Validation: run `node tests/workspace_v236.test.js` and the existing calendar tests. The new interface stylesheet is `assets/v236.css`. Historical release instructions below apply only to their named versions.

## v2.3 update

This version adds monthly calendar estimates and project detail, optional Won/Lost results, safe admin account deletion, a four-project scrollable chooser, project-only lighting refs with same-cell Excel export, and an inline editable lighting-price library with explained totals, searchable nicknames and photos. The sidebar is reordered as requested.

**Existing installation:** use the update-only ZIP, preserve your current data folder and follow [UPGRADE_v2.3.md](UPGRADE_v2.3.md). See [release notes](RELEASE_NOTES_v2.3.md) for calculation/storage definitions and [test report](TEST_REPORT_v2.3.md) for validation and limits. Pillow is now required for light photos; both startup launchers check it.

## 1. Start and deploy

### Run locally

| Platform | Start command | What happens |
| --- | --- | --- |
| Windows | Double-click `START_TEC_SERVER.bat` | Creates `.venv`, installs requirements and starts the server. |
| Linux / macOS | `sh run.sh` | Creates `.venv`, installs requirements and starts the server. |

Install Python 3.10 or newer first. The initial dependency installation needs internet access. Open `http://127.0.0.1:8080` on the host, or use its printed team URL from another computer. Keep the server running and allow the required private-network connection through the host firewall. Stop it with Ctrl+C. Use one server process and keep SQLite on the host's local disk.

### Existing cPanel production deployment

The included [.github/workflows/deploy-cpanel.yml](.github/workflows/deploy-cpanel.yml) deploys on pushes to `main` or a manual GitHub Actions run. It retains the supplied deployment path and site address.

1. Update the files in your existing checkout, retaining its Git history and your production data.
2. Review the changes, commit them and push to `main`.
3. GitHub Actions installs requirements, checks Python syntax and runs the release tests.
4. It connects over SSH, creates a consistent pre-deployment SQLite backup and removes backup sets older than the latest one.
5. It uploads application code, installs requirements, restarts Passenger and checks `/api/health`.

| GitHub secret | Purpose |
| --- | --- |
| `CPANEL_HOST` | SSH host |
| `CPANEL_USER` | SSH username |
| `CPANEL_SSH_KEY` | Deployment private key |
| `CPANEL_SSH_PORT` | Optional SSH port; defaults to 22 |

The workflow preserves server-owned `.htaccess`, `passenger_wsgi.py`, Python environments, certificate verification files, temporary restart files and the full production data directory. It does not create the cPanel account, SSL certificate or Passenger adapter. Those are part of the existing deployment. The delivered ZIP contains code and configuration, not local Git internals; copy it into your existing checkout. No live deployment is performed by producing this release.

### Upgrade from a version earlier than v2.0

Stop the old app and back up its current main and lighting databases. Put the old `lighting_prices.db` beside the live main database for the first v2.x startup, or point `CONEST_LIGHT_PRICES_DB` to its legacy location. Startup verifies it, creates a migration backup, then transactionally merges supplier quotes into `conest_catalog.db`. Matching quotes are skipped on repeated startup; related IDs are remapped when necessary. The old file is not deleted automatically. Once verified, archive it outside the live data directory and remove the legacy path variable. Subsequent operation needs only the main database.

## 2. Daily use

### Features included in v2.2

| Area | Behaviour |
| --- | --- |
| Mobile navigation | A compact header with Menu replaces the squeezed desktop sidebar. The menu contains account controls and closes after navigation or Escape. |
| New projects | A submission deadline can be today or later. Past dates are blocked in the picker and API. The server's local date is authoritative; existing overdue projects are preserved. |
| Settings | Backup and application-default panels share the available width. |
| Component editor | Description, size, quantity, unit, material price, labour basis, labour value and delete action have balanced widths. Phones show labelled component cards. |
| Save feedback | Errors appear inside the editor without losing entered values. A successful write is confirmed before screen refreshes, avoiding a misleading save failure if refresh fails. |
| Backup retention | Only the latest completed backup set is kept in the active backup folder. |

### Home, teams and projects
The project board shows accessible projects, their status and deadlines. Use its search bar to locate a project. Team members can work on projects assigned to their team, and a project created by a user is shared with their team. Administrators can manage all projects, users, roles and teams. Newly created user projects appear for admin review. All active signed-in users can view every company project in every status, including other teams' notes, revisions and recorded activity. Only the owner, assigned team members, individually assigned users or administrators may change project content. Owners and administrators control project deletion and assignment of existing teams or individual editors; this does not grant account-administration permissions. Viewing does not grant editing permission.

My profile contains personal details and team membership. Administrators can rename teams, change members, promote or demote users, and activate/deactivate accounts through management screens. The deadline calendar and homepage reminders help identify approaching and overdue submissions. The activity record attributes project changes to users.

### Build an estimate

1. Open a project and type an item title into the main search bar. Suggestions appear as you type. Select an item to review its build-up, then add the required Qty. **Zero is allowed**, so an item can remain in the estimate while its quantity is still undecided.
2. The round **search icon** at the lower right scrolls to and focuses that main search bar. The **↓ button** goes to the bottom of the estimate. Clearing the search text or pressing × removes the result and cancels pending searches.
3. **Find in estimate** searches the items already added, including their names, sizes, scopes and component descriptions. It changes only what is visible; the quoted total and Excel export still include the whole estimate. Clear this field to show the full list.
4. Items are grouped by scope. Use **+/− beside a scope** to hide/show that whole group. Use **+ beside an item** to show its components; components initially start collapsed. Typing a new live-estimate search reveals matching items. Collapse all still minimizes categories while that search is active.
5. Change the estimate name, Category, Qty or lighting Supply cost / unit directly on the line. Category suggestions show full names and allow pointer or keyboard selection. Custom categories are still allowed. Names and category text wrap to show long values. These changes save to the project without creating catalogue records.
6. Use **Copy item** for an independent copy immediately below the source. Drag the **⠿ grip** beside its title to reorder items **within the same scope**. To move between scopes, change Category. The order is saved and is used by Excel.
7. Expanded components have their own **+ copy** and **⠿ drag** controls. Copies appear immediately below the original; components can be moved within their own item. Copies preserve the displayed rates, sizes, units and factors. Copying or moving a component does not change its source catalogue item.
8. **Edit item / components** opens the full editor, including work type, assembly size, component descriptions, units, sizes, factors and prices. The editor also supports component copy and drag controls. Assembly and component sizes are shown in bold on the website. Component size has its own visible editor column; exported component descriptions use regular text and a separate Size / specification column.

The main Qty field is the single visible estimate quantity. Historical parenthetical take-off lengths/quantities are removed from presentation titles and from the text inserted into search when an item is selected. Useful specifications such as IP ratings and millimetre sizes are retained. This title cleanup does not rename raw catalogue records automatically. Catalogue Explorer searches by title; source codes, component descriptions and historical aliases do not determine catalogue title matches.

### Lighting supply and installation

Lighting and Emergency & Exit Lighting use the same pricing rules. The designated parent component (otherwise the first component) is the fitting supply allowance. Enter the supplier's price for **one fitting** in **Supply cost / unit**, before project mark-ups. The main Qty scales supply and installation together. Previously saved independent supply quantities are preserved until a quantity is edited, so an upgrade does not silently change a quotation.

**Supplier prices are saved with the project, not written back to the reusable catalogue.** They must be stored in the project database so reopening, project copies, backups and tender revisions retain the quotation. Editing the main supply field never creates a new catalogue item. Saving a new catalogue item from the estimate, or choosing to update its existing catalogue record, writes zero fitting supply prices into the reusable record while retaining the actual supplier prices in the project. Installation materials and labour are reusable. Other saved estimates keep their own snapshots.

The live estimate shows **Supply / unit** and **Install material / unit** separately. These calculated amounts include the project material mark-up. The first is the fitting supply allowance; the second is the remaining material build-up. Labour is shown separately. In categories without a separate fitting allowance, the material build-up appears under installation materials. The scope summary separates lighting supply cost from installation cost, with all labour included in installation.

Copying a fitting component preserves its current price and marks it as another fitting supply allowance, so it stays in the supply subtotal after reordering. The main supply-price field controls the original designated fitting; copied fitting prices can be edited in the component editor. When that build-up is saved to the catalogue from an estimate, all of these fitting supply prices are excluded. Existing imported catalogue prices are not erased as part of upgrading the database.

### Choose where an edit is saved

| Choice in the estimate editor | Result |
| --- | --- |
| **Save this estimate only** | Saves the edited name, size, components, quantity and prices to this project. The original catalogue item and other estimates are unchanged. |
| **Update existing catalog item** | Updates the same catalogue ID for future use and saves the edit to this estimate. No new version is created. Fitting supply prices stay in the project. |
| **Save as a new catalog item** — default | Creates a separate reusable item and updates/adds the estimate line. Lighting fitting supply prices are zero in the catalogue and retained in the estimate. |

A completely new manual item created while estimating is saved for future use automatically. If a catalogue source has since been deleted, its saved estimate can still be edited; choose a new catalogue item only when you want to make it reusable again. Work types include Assembly, Supply only, Installation only, Supply & installation, Relocation, Demolition, and Relocation and Demolition. Work-type controls remain in the full editor. Supply-only excludes labour; installation-only excludes material in this editor, so choose Assembly or Supply & installation if you need materials and labour in the build-up.

### Copy a project

Use **Copy** on a project card or **Copy project** above its estimate, then enter the new project name. The copy retains the scope of work, client, currency, project rates, estimate quantities, fitting supply prices, item order and component snapshots. Every copied item/component receives a new ID so subsequent edits are independent.

The copied project starts as **Not started**, with a new owner/creator and activity history. Set its new deadline in Manage project. User-created copies share automatically with the creator's current team and enter the admin's newly-added review queue. Admin-created copies can be assigned to teams through Manage project. Old assignments, submission/completion records, shared notes and tender revisions are not copied. A submitted project from another team may be copied when you have permission to view it; that does not grant permission to edit the original.

### Rates and summaries
Rates and mark-ups are visible above the estimate. Material mark-up affects material; labour rate affects hourly labour; final mark-up applies to direct cost. Save project settings to apply edits. Fixed labour prices stay independent of the hourly rate.

The summary switches between By scope and By work type. Scope totals include separate lighting supply and installation lines. Work-type totals group complete estimate lines according to their saved classification. These are two views of the same estimate, not additional costs to add together. Parent scope rows and their child breakdowns likewise must not be added together twice.

### Catalogue editing and deletion
Catalogue Explorer contains saved details, versions, sources and pricing history. Users and administrators can create, import and edit catalogue items. Every saved item, including imported records, has **Edit catalog** to update that exact record in place. Select the exact record before editing or deleting it. Estimate search results also include **Delete**, so an incorrect catalogue item can be removed without leaving the estimate page.

**Delete catalog item** asks for confirmation and permanently deletes that selected catalogue record and its catalogue-owned components, source links, aliases and price history. It does not delete other saved versions. Existing estimates keep their snapshot descriptions, components and prices; their link to the deleted catalogue item is cleared. Saved tender revisions remain snapshots. Another equivalent saved version may still appear in search. Re-importing its original workbook can recreate a deleted item. Restore a database backup if you need to undo a deletion; restoring affects the whole database, including later changes.

### Imports and price history
Upload supported Excel layouts through Imports. Preview new items, changed prices, duplicates and parsing messages; choose what to import. Confirming an import creates a backup first. Unsupported layouts cannot be treated as successful imports. Source filenames, relevant quantities and pricing data are stored in the database. Low/high budget ranges are kept as distinct labelled options rather than averaged into an invented rate. Enter supplier and quote-date information where available for price history.

### Notes, collaboration and revisions
Add Note stores shared notes with the author's name. A small unread indicator is tracked separately for each user and clears when that user opens the notes. Members with the applicable project access can remove obsolete notes.

Presence information shows active project users. Revision numbers on project/line writes detect stale edits and ask for a refresh instead of silently overwriting another person's changes. The activity log records contributors. This is shared estimating, not simultaneous character-by-character document editing.

Save tender revisions such as Original, Revision 1 or Final Submission to preserve a quotation snapshot. Compare revisions and export their Excel files. The revision creator or an administrator can delete a revision. Deleting a revision does not delete the current working estimate.

### Excel export
The workbook has COST ESTIMATE and CONNECTED COST DETAIL sheets. The first shows project assumptions, scope totals and a separate Work Type Cost Summary. The detail sheet contains parent assemblies and their component build-ups. Pale gold input cells can be edited. Parent quantities drive component quantities; unit prices, project mark-ups and labour rate feed connected formulas. Parent categories feed the scope summary, and column O work types feed the work-type summary. Excel recalculates when opened in a compatible spreadsheet application. Parent Material / unit cells show separate, formula-linked Supply and Install values on two lines, while component material cells remain numeric inputs. These parent display cells are not extra amounts to add to the total. Assembly and component sizes have a separate Excel column; component descriptions use regular text. Reordered items and components export in their saved order. Zero parent quantities produce zero scaled allowances without division errors; explicitly fixed component quantities still apply.

The exported workbook is an independent file: edits made in Excel do not automatically sync back into the website. Keep revisions in the app when you want to preserve a submitted quotation there.

### Supplier lighting prices

Open **Light price check** directly below Imports in the sidebar. Use the Supplier dropdown to filter connected groups containing that supplier, together with your search text. Supplier and Cat No are separate detail columns. The visible Add supplier prices panel is at the bottom of the page. Type any combination of supplier, description, catalogue number or project name; matching is case-insensitive, every search word must occur in the connected group's searchable data, and suggestions refresh without pressing Enter. Quote reference is searchable too. Results show 40 groups per page, with Previous/Next controls. Open a result to see the quantities, unit and line prices of all linked parts and freight, plus source quote, project, date and PDF page. Results support browser Back/Forward, refresh and opening in a new tab.

All displayed prices are **AUD excluding GST**. The internal Type field connects rows but is not shown in the website. Connections are local to each quote:

1. A non-empty Type starts a group or joins an existing group with the same type, including when it reappears later.
2. A blank Type joins the preceding type. Leading untyped rows have their own standalone group.
3. Where a separate Type cell is blank but the description contains a marker such as `Type PD01`, that marker supplies the type. This connects fittings and globes that the PDF places on different rows.
4. The first row of a group provides its primary quantity. The connected unit price is **sum of linked line totals ÷ primary quantity**. It is not the sum of the component unit rates. For example, one chandelier at $100 plus twelve globes at $5 gives $160 per chandelier. A zero or missing primary quantity has no calculated connected unit price. Missing component prices mark a group incomplete; its known line sum is explicitly a partial total.
5. Standalone commercial notes and unpriced note-only rows are excluded. Priced freight is retained even when its catalogue number says NOTE. Included zero-price equipment is retained. Original source-row metadata, including raw types and available GST/ETA values, remains in the main database for traceability; commercial notes are not displayed as price results.

The importer preserves the original quoted line totals and retains any source-header rounding differences rather than inventing a balancing item.

Use **Add supplier prices** to upload the connected `.xlsx` workbook format or a text-based TLE quote `.pdf` matching the samples. Workbook import reads the **All Items** sheet once, not the repeated project-specific tabs. Optional Project Index totals are kept for reference. PDF parsing recognises the 12-column item table and quote metadata across repeated pages. Scanned PDFs, other supplier layouts and arbitrary spreadsheets are not supported by this importer; it reports an error instead of guessing. Uploads are limited to 30 MB and PDFs to 100 pages.

Identical quote reference/date/content is skipped even when the same quote is uploaded once as XLSX and once as PDF. Changed content is retained as another quotation record rather than overwriting previous prices. Import parses first, then writes the whole batch transactionally under a write lock. Before an import adds records to an existing database, a consistent backup is saved through the normal main-database backup system in `data/backups`.

**Light prices remain separate from the main catalogue and projects.** Importing a supplier quote does not change any estimate. Review a connected price, then enter the required price in the estimate's Supply cost / unit field. The Help assistant can retrieve up to four supplier groups and provide links to check them. With AI enabled, those selected supplier facts are sent to the configured provider along with the question; without AI, matching prices and links are still available through the built-in guide.

**One database from v2.0.** `conest_catalog.db` contains accounts, catalogue records, projects, estimate snapshots, settings and supplier quotes. All future imports write there. Main database backups include lighting prices, and restoring them restores lighting prices too. `CONEST_DB_PATH` selects the active file. The old lighting path is used only for the one-time deployment migration above.

### Fixed component quantities and uploads

Open **Specifications, factors & notes** and tick **Fixed total** to restore its original database quantity and stop it multiplying by the parent assembly quantity. For imported items, this uses the original workbook quantity; old estimate rows are matched to their source by order, description and size. Unmatched rows use their saved allowance. A fixed quantity applies even when the parent quantity is zero; set the component quantity to zero to exclude it. Material, labour, copies and connected Excel formulas use the same rule. Untick to use a per-item allowance again.

After an item is added successfully, the search quantity returns to **1**. Failed adds keep your entered quantity. Both upload panels accept drag-and-drop or file selection; preview/import still requires pressing the existing button. Workbook imports accept XLSX/XLSM up to 80 MB; supplier quotes accept XLSX/PDF up to 30 MB.

Help reads live saved project estimates, notes, revisions and recorded activity; catalogue components/allowances; and lighting-quote components/prices. Search by name, ID, catalogue number or lighting nickname, or ask about the open record. Source links open the matching record. Data lookups use application calculations and do not need an AI key. Optional Gemini is used only for how-to guidance; retrieved business records are not sent to it. Answers never edit your work. Result limits are stated and a missing price is not represented as a complete price.

## 3. Data and backups

**One active database:** `data/conest_catalog.db` contains catalogue records, projects, estimate snapshots, accounts, settings and supplier lighting prices. Passwords are stored as one-way hashes. Browser theme preferences stay in browser storage.

### Keep one current backup

All routine app backups, supplier/catalogue import backups, restore safety backups, command-line backups and GitHub pre-deployment backups share `data/backups`. Each set contains a `.db` snapshot and, where present, its `.json` metadata. Retention uses file modification time, so different filename formats are ordered consistently. Older sets are deleted automatically after a successful new backup, at startup and when the backup list is refreshed. A failed backup does not trigger pruning of existing restore points.

Use **App settings → Back up now**, or run `BACKUP_DATABASE.bat`. Download any backup you want to retain longer to a location outside the active backup folder. One-time migration archives and copies already downloaded elsewhere are not part of routine retention.

Restore checks database integrity, relationships, schema compatibility and the presence of an active administrator. It takes a safety snapshot first and signs users out after restoring. The selected snapshot is loaded before retention removes older files, so the selected backup can be restored safely even when it is replaced by the safety snapshot.

> [!NOTE]
> Do not copy only the `.db` file while SQLite is actively writing. Use the backup function, which includes committed WAL transactions, or stop the server first. For rollback to older code, restore the corresponding pre-upgrade files together.

| Location | Contents |
| --- | --- |
| `data/conest_catalog.db` | Live application data |
| `data/backups/` | Latest routine backup set |
| `data/migration_backups/` | One-time upgrade rollback snapshots |
| `data/import_previews/` | Temporary catalogue import previews |
| `.venv/` or `venv/` | Installed Python environment |

## 4. Architecture and pricing


- **Assembly normalization:** source component quantities are divided by the source assembly quantity to create per-unit component ratios. Adding an assembly scales those ratios by the estimate quantity.
- **Material:** quantity × component material rate × material factor × (1 + material mark-up). A direct fitting supply-price override uses the entered supplier unit price with factor 1, before project mark-ups.
- **Hourly labour:** quantity × unit hours × labour factor × project hourly rate.
- **Fixed labour:** quantity × fixed labour price × labour factor. This is a monetary allowance, not hours, and is unaffected by hourly-rate changes.
- **Quoted cost:** (material + labour) × (1 + final mark-up).
- **Independent snapshots:** adding a catalogue item copies its components into the project. Later catalogue editing/deletion cannot rewrite those saved component prices. Tender revisions preserve another snapshot as JSON.
- **Duplicate grouping:** assembly-level size plus normalized identity and component allowance comparisons group equivalent catalogue results. Different dimensions, units, work types or allowances can remain separate. Grouping is not the same as deleting source records.
- **Classification:** scope describes the electrical service (Lighting, Power, etc.); work type describes the operation (Installation, Relocation, etc.). Both summaries reconcile to the same estimate.
- **Connected workbook:** cell references, SUM/IF formulas, category helper rows and conditional formatting connect detail rows to summaries. Work-type dropdown validation guides edits. No source Excel template is needed at runtime.

| Technology | Purpose and why it is used |
| --- | --- |
| Python 3 | Runs the server and application logic locally. Most facilities come from Python's standard library. |
| ThreadingHTTPServer / HTTP handlers | Serves browser assets and JSON API requests, with separate request threads. No Flask or Django installation is required. |
| SQLite / Python sqlite3 | The main `.db` stores catalogue, accounts and projects. The same file also stores supplier quote records and their connections. No separate database server is required. |
| SQLite WAL | Write-ahead logging lets readers continue while writes are committed. Foreign keys preserve relationships; a busy timeout handles brief contention. |
| Write lock and transactions | Serialize application writes in one process; each transaction commits its related changes together. |
| HTML and CSS | Define the screens, forms, responsive layout, tables, dialogs, focus states and visual styling. |
| Plain JavaScript | Updates browser views, fetches API data and handles editing/search. No React, npm build or front-end compilation is required. |
| Fetch / JSON | Browser requests and responses communicate structured application data to the Python server. |
| openpyxl | Reads supported `.xlsx` inputs and writes formatted formula-based exports. It does not run Microsoft Excel. |
| pdfplumber | Extracts text and table rows from supported TLE supplier quotation PDFs. Its required PDF-processing dependencies are installed by pip. It does not perform OCR. |
| SVG | The lightweight TEC initials mark used by the website and browser tab. It is a placeholder mark, not a separately supplied official logo. |
| Optional Gemini API | Can interpret/rerank title-matched candidates when configured. Local searching remains available without it. |
| Python venv / pip | Launchers isolate Python dependencies in `.venv` and install `requirements.txt`. |
| Git ignore rules | Keep local databases, credentials, generated files and environment folders out of routine source-control commits. GitHub hosting/synchronization is not built into the app. |

### Authentication and safe writes
Passwords are salted scrypt hashes, not readable passwords and not reversible encrypted passwords. Session tokens are random; only token hashes are stored in the database. Browser cookies use HttpOnly and SameSite, and authenticated writes check a CSRF token plus request/origin rules. Permissions are checked again inside the write connection to account for role changes or session revocation.

Sessions have no routine server expiry and survive closing the browser. The cookie is renewed during authenticated use; browsers impose their own retention limits. Sign-out, account deactivation, password changes, database restore or clearing cookies can end access. Persistent sign-in means users should sign out on shared devices. The database itself is **not encrypted**: project data and saved configuration are readable to someone who can access that file. Password hashing does not encrypt other database contents.

### Performance and update handling
Search uses bounded shared read caching. Database generation triggers invalidate cached catalogue results after catalogue changes. The browser debounces typing to avoid one request per keystroke and checks request versions so stale search responses do not replace newer results. Display values are escaped to prevent item text being treated as page markup. SQLite foreign-key cascades remove dependent catalogue records on deletion; SET NULL preserves project references safely.

The release checks include 20 simultaneous authenticated clients and stale-write detection. This is a test scenario, not a guarantee for every host or workload. Keep one server process running and monitor large imports on the host.

### Backups and migrations
Main-database daily backups are scheduled by the running server; there is no external scheduler when it is stopped. Imports and restores create protective backups. SQLite's backup API captures a consistent committed database, including WAL changes. Restore validates integrity and relationships and signs users out. The latest completed backup set is retained; older snapshots and their metadata are removed automatically. Migrations inspect schema/one-time markers so restarts do not repeatedly reset accounts. The application keeps legacy tables/code needed for compatible databases even when an old screen has been removed.

## 5. File guide

<details>
<summary><strong>Application, deployment and test files</strong></summary>

| File | Responsibility |
| --- | --- |
| `.github/workflows/deploy-cpanel.yml` | Production CI/CD: validates Python and release tests, connects over SSH, backs up and retains one snapshot, uploads code while protecting production data, restarts Passenger and checks health. |
| `assets/file_drop.js` | Validated drag-and-drop selection for workbook and supplier-price uploads; uses the existing import confirmation buttons. |
| `assets/mobile.js` | Mobile menu state, keyboard dismissal and automatic closing after navigation. |
| `assets/responsive.css` | Mobile layouts, aligned settings panels, component column sizing and visible dialog save errors. Loaded after both themes. |
| `tests/test_release.py` | Automated date validation, one-backup retention and restore tests; used by GitHub Actions. |
| `README.md` | This usage, architecture, maintenance and release guide. |
| `app.py` | Server entry point, main API routes, request/error handling, import/export integration and server lifecycle. |
| `requirements.txt` | Supported openpyxl and pdfplumber dependency ranges for installation. |
| `START_TEC_SERVER.bat` | Windows environment setup and server launcher; displays local/team access details. |
| `BACKUP_DATABASE.bat` | Windows entry point for the standalone database backup utility. |
| `run.sh` | Linux/macOS virtual-environment setup and server launcher. |
| `.gitignore` | Rules excluding local/private/generated files from normal Git tracking; it does not prevent the app reading those files locally. |
| `data/conest_catalog.db` | Bundled SQLite snapshot: catalogue, components, accounts, teams, projects, settings and related application records. Replace with your latest backup when upgrading. |
| `conest_app/lighting_migration.py` | Repeatable transactional legacy lighting import, integrity checks, duplicate detection, ID remapping, pre-upgrade backup and migration markers. |
| `assets/estimate_extras.js` | Password visibility, crew-day displays, the floating estimate total and bulk component expansion/collapse. |
| `assets/light_prices.js` | Supplier search, paginated quote cards, connected component details and file uploads. |
| `conest_app/light_prices.py` | Supplier table schema in the main database, workbook/PDF parsing, internal type connections, quantity-aware linked prices, duplicate detection and pre-import backups. |
| `tools/backup_database.py` | Creates a consistent snapshot in `data/backups` using the same one-backup retention policy. |
| `assets/theme.js` | Applies system or saved light/dark preference before painting the page; handles the accessible sidebar toggle and browser-local persistence. |
| `assets/theme.css` | Navy dark surfaces, teal accents, readable controls, tables, dialogs, status colours and focus states. Static CSS overrides; no runtime dependency. |
| `assets/index.html` | Main page, navigation, forms, tables and dialogs. |
| `assets/help_chat.js` | Help dialog, questions, plain-text replies, local source links and session-safe response handling. |
| `conest_app/help_chat.py` | Built-in guidance, bounded catalogue/project retrieval, project access checks, optional Gemini answers and local fallback. |
| `assets/navigation.js` | Hash-based page addresses, deep-link startup, browser history and stale-navigation protection. Native links support opening pages/projects/catalogue items in a new tab. |
| `assets/estimate_workspace.js` | Scope collapse, live-estimate search, navigation, copy/project-copy actions and drag event handling. Loaded after the main UI scripts. |
| `assets/app.js` | Estimator, catalogue, manual item editor, settings, search and import interactions. |
| `assets/styles.css` | Base appearance, estimating layout, responsive rules and component styles. |
| `assets/workspace.js` | Login, board, profile, teams, user/project administration, activity, notes and calendar interactions. |
| `assets/workspace.css` | Workspace, management, profile and board styling. |
| `assets/productivity.js` | Revisions, price history, backup controls, import preview, presence and reminders. |
| `assets/tec-mark.svg` | TEC initials branding and favicon asset. |
| `conest_app/__init__.py` | Python package identity/version. |
| `conest_app/accounts.py` | Password hashing/verification, sessions, account validation, sign-in throttling and public user records. |
| `conest_app/assistant.py` | Quantity/query interpretation and optional Gemini integration with local fallback. |
| `conest_app/backups.py` | In-app backup listing, creation, validation, restoration and daily-backup logic. |
| `conest_app/catalog.py` | Catalogue queries, details, duplicate presentation, manual creation/editing and selected-version deletion. |
| `conest_app/component_master.py` | Parser for recognized component-pricing master workbook layouts. |
| `conest_app/database.py` | SQLite paths/connections, schema creation/migration, settings, write lock and catalogue index refresh. |
| `conest_app/estimate_tools.py` | Transactional project/item/component copying and order validation, preserving independent snapshots and checking revisions. |
| `conest_app/estimate_options.py` | Display-title cleanup, lighting fitting identification, estimate supply/size fields, fitting-copy flags and persistent-session migration. |
| `conest_app/exporter.py` | Styled, connected two-sheet Excel estimate generation and export naming. |
| `conest_app/http_productivity.py` | API routing for revisions, presence, backups, pricing history and import preview. |
| `conest_app/http_workspace.py` | Authentication/CSRF checks, request permission checks and workspace API routes. |
| `conest_app/import_preview.py` | Temporary parsed previews, duplicate/price comparison and importing selected preview rows. |
| `conest_app/importer.py` | Core workbook layout detection, parsing, normalization and catalogue/source insertion. |
| `conest_app/initial_roster.py` | Initial testing roster definitions and precomputed password hashes; supports initial account provisioning. |
| `conest_app/productivity.py` | Revision snapshots/comparison, price-history records, presence and deadline data; includes legacy check support retained for compatibility. |
| `conest_app/project_notes.py` | Shared note storage and per-user unread/read state. |
| `conest_app/projects.py` | Project and estimate-line operations, snapshots, cost calculations, scope/work summaries and line options. |
| `conest_app/range_importer.py` | Recognized low/high budget workbook parser; preserves both pricing alternatives. |
| `conest_app/read_cache.py` | Bounded thread-safe catalogue read cache and generation triggers. |
| `conest_app/taxonomy.py` | Scope and work-type definitions, normalization, quality/specification and grouping helpers. |
| `conest_app/teams.py` | Team membership/management and team-aware project sharing support. |
| `conest_app/utils.py` | Text cleanup, safe filenames, timestamps, hashing and numeric helpers. |
| `conest_app/workspace.py` | Project access, activity, statuses, optimistic revision checks and board visibility. |

</details>

## 6. Release history

Versions are listed oldest to newest. Early milestones are grouped where individual change records were not supplied.

| Version | Main changes |
| --- | --- |
| v1.0–v1.2 | Initial release series. Detailed change records for these versions were not included in the supplied history. |
| v1.3 | Manual supply, installation, relocation and demolition pricing; hourly/fixed labour; editable units/components and reusable catalogue versions. |
| v1.4 | Project deletion, floating search, duplicate result grouping, live scope breakdown, Data.xlsx assemblies and connected Excel calculations. |
| v1.5 | TEC ConEst branding, saved API-key Show/Hide, aligned project/export controls, separate connected-detail Excel tab and simplified summaries. |
| v1.6 | Duplicate matching ignoring codes, removal of visible Code/Phase fields, wrapping category editor and refreshed website/Excel presentation. A repaired ZIP was also supplied. |
| Team/productivity releases through v1.12 | Login and roles, user/team administration, shared projects, board/status review, profile teams, calendar, shared notes/unread indicators, contribution activity, tender revisions/deletion, backup/restore, import preview, price history, presence and deadlines. Extra board filters and submission-check controls were subsequently removed; management alignment and horizontal team presentation were refined. |
| v1.13 | Removed historical Quality Control panel; slim runtime ZIP without already-imported Excel copies; existing testing accounts directly active while future accounts retain setup. |
| v1.14 | Collapsed estimate details, estimate-only fitting supply price/quantity, lighting supply/installation summary, cleaned display titles, live title-only catalogue search and persistent sessions. |
| v1.15 | Linked lighting quantities, switchable work-type summary, combined Relocation and Demolition type, Excel work-type summary, cancel-search behavior and expanded rates controls. |
| **v1.16** | Removes inline work-type selector and duplicate supply quantity. Keeps plain Supply cost / unit without a yellow box. Initially moved classification to Item options; this fixed release removes the extra control. Refines visual hierarchy, rates panel, buttons and row spacing. Adds authenticated selected-version catalogue deletion while preserving estimate snapshots. Expands this guide to explain all delivered files, technology, techniques and release milestones. |
| **v1.17** | Uses the latest uploaded database. Adds main-search navigation and bottom navigation; in-place edits for imported and manual catalogue items; deletion from estimate search; estimate-only save mode; project-specific fitting prices; split material rates; scope collapse; zero quantities; search within estimates; clean selected titles; assembly size; item/component copying and dragging; project copying; compact controls and this updated guide. |
| **v1.17_Fixed** | Adds page/project/catalogue addresses, Back/Forward and refresh restoration, native new-tab links, inline estimate size editing, matching Delete buttons and larger left-aligned scope headings. No database migration or bundled data changes. |
| **v1.18** | Removes inline size from estimate rows; compacts title/category/supply controls; adds draggable whole categories and up/down controls with persistent Excel/copy order; adds optional read-only Help chat using the existing Gemini setting with a built-in fallback. |
| **v1.19** | Adds password Show/Hide; separate Excel/editor size columns and regular component descriptions; floating quoted total and category totals; configurable crew/day planning; Expand all / Collapse all; separate supplier-price search/database with connected XLSX/PDF imports, duplicate detection, backup download and Help integration. |
| **v1.19_Fixed** | Bulk controls now minimize/expand categories; adds a supplier filter, separate Supplier/Cat No detail columns, a clearer bottom upload panel, removes the database download button, and moves Light price check below Imports. Both database files are unchanged. |
| **v1.20** | Uses the newly uploaded database; enlarges the floating total with hours/days, aligns scope totals/actions, adds new-project crew defaults, full-width profile with optional email and a password section, TEC home link, and persistent light/dark themes. |
| **v2.0** | Unifies supplier-price tables and all application data in conest_catalog.db; adds a backed-up, transactional legacy migration for deployed servers; all backups now include supplier records. |
| **v2.1** | Mobile menu, stacked deadline reminders and labelled estimate cards; floating +/− category control; equal settings widths; no past deadlines for new projects; latest-one backup retention across app, script and deployment; balanced eight-column component editor; visible modal errors and clearer save confirmation; reorganized documentation; reset add quantity, drag-and-drop uploads, fixed component totals, and access-controlled project Help. |
| **v2.2** | Moves Fixed total into each component’s expandable Specifications, factors & notes section; retains all previous estimating and data behavior. |

| **v2.3–v2.3.5** | Monthly calendar totals, project outcomes and access, unified import history, profile and supplier photos, optional builders, and weekend calendar styling. |
| **v2.3.6** | Simplified project board with three remembered views, integrated schedule reminders, estimate-only creation, clearer page titles and prominent Open Estimate access. |

| **v2.4** | Direct refresh restoration, shared read requests, lighter background updates, batched component queries, browser asset caching and total-cost sorting. |
| **v3.1** | Review workflow, Completed-to-Submitted migration, shared review reminders, Builders project filter and expanded monthly activity. |
| **v3.0** | Integrated Tenders with shared authentication, yellow workspace, matching sidebar, compact updates, protected runtime database deployment and Passenger v3.0. |

## 7. Troubleshooting

| Symptom | Check |
| --- | --- |
| Mobile layout still looks old | Refresh the page to reload the new CSS and JavaScript; open Menu for navigation and account controls. |
| Catalogue save rejected | Read the alert inside the editor. Your inputs remain available. Check missing descriptions/units, invalid prices and work-type constraints. If repeated, retain the exact error text for diagnosis. |
| Save succeeded, but the view did not refresh | Reload the page before saving again; the write has already completed. |
| New project date rejected | Choose today or later. Check the server's date/time configuration if its calendar differs from yours. |
| Older backup disappeared | The single-backup policy applies to the active backup folder. Keep longer-term copies elsewhere. |
| Changes missing after deployment | Verify the production database path and the preserved data directory. Do not overwrite the live database with a packaged snapshot. |
| Excel formulas show no result yet | Open with automatic calculation enabled in a compatible spreadsheet application. The exporter writes formulas; it does not run Excel. |
| Deployment fails | Open the failed GitHub Actions step; check repository secrets, SSH access and the existing Passenger setup. |
| Forgotten password | Ask an administrator to reset it through user management. |

### Run release checks

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m compileall -q app.py conest_app
```

The release tests use temporary databases. They check date boundaries, backup retention, metadata cleanup and restoring the older snapshot. Additional development regression checks cover estimation, permissions, import/export, sessions and migration. Browser rendering should also be checked at your team's actual screen sizes.


### v3.4 search refinement (13 October 2026)
Dashboard and Project Chase-up searches exclude chase comments, including the latest-update copy. See UPDATE_V3.4.md for deployment notes.
