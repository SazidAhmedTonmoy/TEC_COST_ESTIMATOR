# TEC Flow — v3.8.13

**TEC Flow — Electrical Estimating & Tender Management Platform**  
**From Opportunity to Award**

TEC Flow connects estimating, quotations, tenders, follow-ups and awards in one workspace.
The platform includes Open–Awarded and automated quotation chase-ups. This repository
contains the current app, frontend source, required database migration code, and focused tests.

## Workspaces

- **Estimator:** estimate projects, cost breakdowns, item references, labour/materials,
  rate controls, saved revisions, Catalog, pricing, Excel exports, and read-only sharing.
- **Tenders:** submissions, builders, project chase-ups, opportunities, approvals,
  quotes, reminders, calendars, reporting, and team assignments.
- **Open–Awarded:** builder-awarded projects whose TEC quote status is still Open.
  Cards and Calendar show awards, estimated starts, latest chase-ups, submitted values,
  linked Opportunity URLs, and shared builder contacts.
  Multiple people, phone numbers and emails are shared with Tender/Chase-up and its linked Opportunity.
  Calls use the device dialler; email uses Outlook web compose.

See [USER_GUIDE.md](USER_GUIDE.md) or **? Help → User Guide** for feature instructions.
See [OPERATIONS.md](OPERATIONS.md) for encryption keys, recovery, load checks and monitoring.

## Updating from v3.8.12

Help opens the searchable user guide in both workspaces. The first estimate and first
quotation walkthroughs include screenshots and worked examples. Catalogue matching
uses the local database. The upgrade removes retired provider settings, including
the stored provider key, when the application opens its database.

When applying an update ZIP or replacing an existing checkout, copying files does
not delete retired source. This also applies if the discarded v3.9.0 AI update was
previously extracted into the checkout. From the repository root, after copying
this release's files, run:

```text
python tools/cleanup_retired_ai.py --apply
python tools/cleanup_retired_ai.py
git status --short
```

The utility removes only explicitly listed retired AI source, compiled assets,
AI documentation and obsolete tests. It does not modify databases, data folders,
environment files or hosting configuration. Review the deletions, stage them
with `git add -A`, commit and push to `main` to start a new GitHub Actions run.
The workflow now checks that these obsolete files are absent before building.
It still runs every current test. Do not rerun an older commit to apply the fix.

Build Tenders and deploy using the normal deployment workflow below.

## Notification and screenshot import correction (v3.8.12)

- Recording a new chase-up creates a per-user inbox notification for active Tender workspace users, with the author, project, builder, date and note excerpt.
- The notification bell refreshes after saving and polls other users’ updates. Search the complete inbox by user name, project or message; filter by Chase-ups, Opportunities or Reminders.
- Missing notifications for authenticated chase-ups recorded during the last 30 days are recovered on the notification sweep using audit records and original timestamps. Imported history is not replayed; existing receipts and read state are preserved.
- Screenshot parsing rejoins wrapped email addresses and builder headings, recognizes short builder names, and warns about unresolved email fragments instead of creating false contact rows. Review all OCR fields before saving. No database migration.

## Calendar and contact import (v3.8.10)

- Hover or focus calendar agenda entries to see the same project preview as the
  month grid, including Approved Opportunities, Chase-up, Open–Awarded and Estimator.
- New/Edit Opportunity → Builders → **Import screenshot** accepts Ctrl+V/Cmd+V,
  drag and drop, or selecting a cropped PNG, JPEG or WebP. Review builder/name/phone/email
  previews and save through the existing shared contact directory.
- Screenshot recognition runs inside the browser using Tesseract.js and local,
  version-pinned WebAssembly/English assets generated during `npm run build`.
  Only recognized text is submitted to the authenticated contact parser. No OS
  OCR executable, external AI API, or server setup is required.
- No database migration. See OPERATIONS.md for build requirements.

## Usability update (v3.8.8)

- Opportunity analytics is readable in both light and dark modes, including donut
  totals, legends, filters and report tables.
- Approved Opportunities calendar shows a softer event tone when tender documents
  are not available. The hover card states the document availability explicitly.
- New/Edit Opportunity keeps the save actions visible when entering long builder
  contact lists, while the form fields scroll independently. Contact changes are
  saved with the Opportunity.
- Existing database schema and login configuration are unchanged.

## Calendar update (v3.8.7)

- Estimator, Approved Opportunities, Project Chase-up and Open–Awarded use
  consistent month calendars with teal weekday headers, compact events, clear
  date selection and hover or keyboard-focus previews. Select a date for its
  agenda below the grid. Saturday and Sunday are marked **Off day**; existing
  deadlines and events on those dates remain visible.
- Estimator summary cards appear in this order: **Projects due this month →
  Labour allowance → Total labour price → Total material cost →
  Total estimate / quoted value**.
- The shared register summary is labelled **Lifetime Total Quotes**. Its
  calculation is unchanged: each project is counted once, using its highest
  builder submission. Monthly calendar figures remain specific to that month.
- This update requires no database migration.

## Security and capacity update (v3.8.6)

- New database backups use authenticated
  AES-256-GCM encryption.
- Sessions expire after 12 hours by default. Unchanged bundled starter passwords
  require a password change before business data is available.
- Private-file rules protect Apache deployments while preserving cPanel settings.
  The runtime installer updates the WSGI adapter while preserving host bootstrap configuration.
- Bounded request admission, batched queries and generation-aware caches improve
  concurrency. Admin-only runtime metrics and repeatable offline load checks are included.
- Local validation passed at 10, 25 and 50 simulated users: 6,800 requests,
  1,700 verified writes, no unexpected errors, and p95 below 2 seconds at each level.
  The workload and hosting limits are documented in **OPERATIONS.md**.

**Live SQLite business databases still require encrypted hosting storage for full
encryption at rest.** Keep the original encryption key securely and separately
from backups; it is not included in a backup or a source ZIP.

## Local setup

Requirements: **Python 3.11+** and **Node.js 22+** for building the Tender UI.

```sh
python -m pip install -r requirements.txt
cd tenders_frontend
npm ci
npm run build
cd ..
python tools/build_frontend.py
python app.py --host 127.0.0.1 --port 8080 --no-browser
```

Open `http://127.0.0.1:8080`. On macOS/Linux, `./run.sh` can initialize a Python
virtual environment, but the Tender frontend must still be built separately.

## Deployment

Pushing to `main` runs `.github/workflows/deploy-cpanel.yml`:

1. Build the Tender React frontend and Estimator assets.
2. Run isolated Python regression checks.
3. Resolve and validate the website's existing Passenger application root.
4. Upload application code and verify its file hashes, preserving runtime data.
5. Install dependencies, private-file rules and the current WSGI adapter.
6. Request a restart in the configured Passenger restart directory and require
   two fresh health responses for the expected release.

Use your existing GitHub Actions secrets and server configuration. **Before updating a
production installation, back up both SQLite databases and keep `.env`, `data/`, and
uploads.** Never overwrite live databases with local files.

The public address is `https://tec-flow.ampecportal.com/`. The deployment
workflow defaults to the application root verified in cPanel:
`/home/ampecportal/tec-flow.ampecportal.com`. No GitHub path variable is required
for this installation. An optional repository variable **CPANEL_DEPLOY_PATH**
takes precedence; a same-named repository secret is also supported. Empty or
whitespace-only overrides fall back to the next available setting.

The target must be an existing TEC Flow installation owned by the SSH account
and must agree with any cPanel Passenger registration or `PassengerAppRoot`
that can be discovered. **CPANEL_SITE_URL** can override the health-check address.
Commit and push the updated workflow to `main` and use the new run. Re-running
an earlier failed run uses its original commit and will not load this correction.
For a manual update, build both frontends and run
`sh tools/install_runtime.sh` before restarting Passenger. This installs the new
`cryptography` dependency and the Apache/WSGI protection hooks.

A health response with `status: ok` but an older `release` is a deployment-version
mismatch. It does not by itself indicate a failed database migration. The workflow
reports the expected and served versions and keeps the version check enabled;
see **OPERATIONS.md → Deployment version mismatch**.

The **UPDATE_ONLY** ZIP overlays the current v3.8.9 source. It preserves your
host's `passenger_wsgi.py`; the installer delegates that existing entry point to
the updated runtime without removing its interpreter or environment setup.
Rebuilding the Estimator assets also removes the superseded generated bundle.
The **FULL_SOURCE** ZIP includes a generic entry point for a fresh installation.

Validation uses the shipped `conest_app.wsgi_runtime` directly, including when
an update retains an older host entry point. Keep the validation step enabled.
The server installer preserves cPanel setup.

On first startup the server creates an owner-only key outside the website.
Keep a separate secure copy before relying on encrypted backups. When moving
the database to another path or host, configure the original key using
`CONEST_ENCRYPTION_KEY_FILE`; see **OPERATIONS.md** for recovery commands.

## Data compatibility

- Application version: **3.8.13**
- Estimator SQLite schema: **36**
- Tender data: additive shared contact directory and selection tables.
- Database migration for v3.8.3: automatic, idempotent import of existing Tender and Open-Awarded contacts; original source records are preserved during migration.
- v3.8.4 automatically adds deleted-contact records to prevent stale forms from restoring a removed contact.
- Legacy internal paths/identifiers such as `conest_catalog.db` remain for
  compatibility with deployed databases and existing exports.
- Older migration Python modules remain in the code because upgrades from
  existing installations may still need them.

## Branding and compatibility

- TEC Flow is the public name; the tagline is **From Opportunity to Award**.
- Deployed site hostname, database paths, session cookies, API headers, import formats, and environment variable names remain unchanged.
- Previous Excel exports, JSON files, and saved browser preferences remain compatible.

## Maintaining the repository

- Keep `README.md` for deployment and `USER_GUIDE.md` for user instructions.
- Current tests live under `tests/`. Run `python tools/run_tests.py --workers 4`.
- Do not commit `.env`, SQLite files, backups, import/export runtime files,
  node_modules, caches, or temporary deployment artifacts.
- `tenders_web/` is generated by `npm run build` and is intentionally omitted
  from the clean source ZIP; **build before serving** or use the GitHub deployment workflow.

## Quotation follow-ups (introduced in v3.8.1)

- Builder **Unsuccessful** closes that builder quotation and cancels its pending reminders; Closed/Lost quotations cannot receive new chase-ups. Other builders on the same project remain independent.
- Enter the **actual submitted date** to start a 14-day first-chase waiting period, then the first following Wednesday at 9:00 am Sydney time. Automatic first schedules repeat every 14 days. Existing records with unknown submitted dates are not guessed.
- Manual schedules may also repeat every 14 days. Click a chase-up calendar day to view the day's agenda underneath. Schedule authors and administrators can delete schedules.
- Older records with builder outcome Unsuccessful are reconciled on startup; **back up both databases before rollout**.

## Shared builder contacts (v3.8.3)

- Add optional contact people per builder when creating or editing an Opportunity or Tender. Each person supports multiple phone numbers and email addresses.
- Choose a saved person, or enter a matching name, email or phone number to autofill their details. Ambiguous names require a selection.
- Tender/Chase-up and Open-Awarded use the same quotation contacts. Explicitly linked Opportunities keep the same selected people for that builder. Changes to a saved person apply wherever selected.
- Builders shows all available people, including contacts from Opportunities without a submitted tender. Open a builder to view, add or edit contacts. **Download all contacts** exports the complete directory to Excel.
- Removing a person from a project's selection does not delete them from the builder directory.

## Contact management and navigation (v3.8.4)

- All administrators and members assigned to a builder's Opportunities or Estimator projects can delete a shared contact from **Builders**. Individual assignees also have access. A confirmation explains that the contact will be removed from every current selection; historical audit entries remain available.
- **Open Linked Project** on an Opportunity card opens its explicitly linked Estimator project, or its linked Tender project overview when there is no Estimator link. Change/unlink controls remain in the details view.
- Project Chase-up sorts keep all builder submissions for the same project together. Pagination also keeps each project on one page.

## Opportunity assignment and closing dates (v3.8.5)

- An unassigned Opportunity card shows **Assign team** in the left footer, matching **View details**. After assignment, the card displays the assigned names; change assignments through **View details → Assign**. Existing assignment permissions and automatic approval rules apply.
- Selecting a closing date shows a nonblocking warning when other Opportunity projects share that date. The count covers the whole register across statuses, teams and regions, excludes deleted/retired records and the edited project, and counts each Opportunity once regardless of its builders.
- The warning also shows assigned team names and project counts. Projects shared by several teams appear under the combined team names; **No team assigned** identifies projects without a team. Each project appears in one group, keeping the breakdown equal to the total. This feature is part of the corrected v3.8.5 baseline.
- This update requires no database migration.
