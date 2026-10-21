# TEC ConEst v3.5

Release date: 21 October 2026. Application release: **3.5**. Estimator database schema: **31**.

This release adds an Opportunities register to the Tender workspace, connects its approvals, assignments and audit history to the existing users and teams, and brings opportunity alerts and chase-up reminders into one notification centre. The Estimator Home page also gains a **New Project** button beside **Project JSON**.

For installation, follow [UPDATE_INSTRUCTIONS_V3.5.txt](UPDATE_INSTRUCTIONS_V3.5.txt). The packaged source data is documented in [opportunities_seed/SOURCE_NOTES.md](opportunities_seed/SOURCE_NOTES.md).

## Opportunities workflow

Open **Tenders → Opportunities** to track potential work before creating an estimate. The register includes search, region and assignment filters, deadline sorting, a list for each team, and separate status views.

| Section | Behaviour |
| --- | --- |
| Awaiting approval | New opportunities start here when their deadline is current or blank. A permitted reviewer can approve or reject them. |
| Approved | Records accepted to progress, with the reviewer, decision time and optional decision note retained. |
| Rejected | Records declined with a required rejection reason. The creator or an administrator can request approval again when the deadline is current or blank. |
| Expired | Opportunities awaiting approval or already approved move here after their closing date. An authorised editor can extend the deadline to return the opportunity to Awaiting approval. |

Closing dates apply through the end of the selected region's local day. NSW uses Australia/Sydney time and VIC uses Australia/Melbourne time, including daylight saving. An undated opportunity remains available for review. Rejected records retain their rejection decision after their closing date.

The opportunity editor includes the project name, multiple builders, region, location, closing date, **Working Scope**, category, project budget/range, estimated tender value, contact details, distance, added date and notes. Budget ranges and estimated tender values have separate labels. Existing builders are suggested from Estimator projects, Tender submissions and saved opportunities; new names are saved for later use.

Approving an opportunity records the team's decision in this register. Use the normal **New Project** workflow when an estimate is required.

## Permissions and assignments

Permissions are checked on the server against current account roles and team membership. A changed or stale record must be reopened before a conflicting save can replace it.

| Action | Who can perform it |
| --- | --- |
| View the active register or add an opportunity | An active signed-in user. |
| Edit project details and working scope | The creator, an administrator, or a person/team explicitly granted editing access. |
| Approve or reject an opportunity awaiting approval | An administrator, including one without a team, or an active user who belongs to a team. |
| Assign teams or individuals | The creator or an administrator. |
| Grant or remove editing access | The creator or an administrator. |
| Delete an opportunity | The creator or an administrator. |

Assignments identify who is working on an opportunity. **Editing access** is a separate permission controlled by the creator or an administrator. Assigning a team notifies its active members; assigning an individual notifies that person. The register provides team lists and an **Assigned to me** filter that includes work assigned through the user's team.

Deleting removes the opportunity from the working register. Its recorded activity and contribution history remain available; there is no Deleted tab. Retained deleted details are restricted to the creator and administrators.

## Notifications, deadlines and contributions

The Tender header has one notification centre for opportunity updates, assignments and the existing chase-up reminders. The header search field aligns to the right on desktop and adapts to smaller screens. Opening the bell displays the alerts and marks those displayed as read for the current user. Older alerts load inside the notification panel. Reminder completion remains a separate action.

Opportunity history records creation, changes, assignments, access changes, approval, rejection, reopening, deletion, approaching deadlines, expiry and Excel imports. Actions retain their actor and time. Earlier activity can be loaded from the detail panel. Deadline stages are recorded once for each opportunity/deadline combination so repeated checks do not create duplicate alerts.

Administrators' **View Contribution** now includes an Opportunities section alongside Estimator and Tender activity. It shows recorded actions, opportunities contributed to and imported rows within the selected date range. Mirrored audit records are excluded from the Tender contribution totals to avoid counting an opportunity action twice. Initial workbook loading and automatic deadline events use system attribution rather than assigning historical work to a current user.

Deadline processing runs in these ways:

- The local Python server checks in the background approximately every 60 seconds while the server is running and the Tender database exists.
- Requests for opportunities and notifications also check for approaching or expired deadlines, with a short interval between repeated checks.
- For Passenger/cPanel, the supplied backup cron installer also installs a deadline worker every five minutes. This supports checks while nobody has the page open. It uses the database paths registered by the running website and operates on existing databases.

Read [installation instructions](UPDATE_INSTRUCTIONS_V3.5.txt) before installing or updating the cron entries. Producing these files has not installed a schedule or deployed the application to a live server.

## Supplied NSW and VIC data

The update contains **54 source records**, added once when the Tender database is first opened after the update. It imports the actual project rows and skips the unused spreadsheet template rows containing only formulas and checkboxes.

| Region | Source records | Awaiting approval on 21 October 2026 | Rejected | Expired |
| --- | ---: | ---: | ---: | ---: |
| NSW | 7 | 7 | 0 | 0 |
| VIC | 47 | 4 | 11 | 32 |
| **Total** | **54** | **11** | **11** | **32** |

These status counts reflect the original source data and closing dates as at 21 October 2026. They will change with time, later decisions and user edits. The VIC workbook contains one historical approval and eleven **Not interested** decisions. Its originally approved opportunity has an elapsed deadline and appears in Expired while retaining **Approved** as its original workbook decision. The source does not identify a reliable approver or decision time, so none is invented.

Category, added date, closing date, budget text, named builders, comments and supplied distances are retained. Source filenames, worksheet names, row numbers and original populated cells remain attached to each imported record. The source workbooks do not have a dedicated Working Scope column, so that field starts blank; scope-related comments remain in Notes.

Two source warnings are retained and displayed:

- VIC row 17 mentions six builders but names only three. Only the named builders are imported.
- VIC row 30, **Office Warehouse in Tullamarine - Stage 1 Only**, names no builder. Its builder list remains empty.

Project titles and budget strings are preserved. For example, the apparent incomplete postcode in the NSW title containing `Sydney NSW 200` has not been silently corrected, and a budget of `5m-10m` remains a project budget range rather than becoming an electrical tender price.

## Regions and distance origins

The initial region list contains NSW and VIC. Further regions appear when added to the register; specify the distance origin for a new region.

| Region | Initial distance origin |
| --- | --- |
| NSW | 63-79 Parramatta Rd Silverwater, NSW 2128 |
| VIC | CBD, Melbourne |

Distances are entered manually or copied from the source workbook. The application does not automatically calculate road distances. When a location is available, the route link opens the nominated origin and project location in Maps for checking. Changing the location or origin clears the distance in the editor so a previously entered value is not silently presented for a different journey.

## Excel import and export

Use **Import Excel** to select or drag and drop an `.xlsx` workbook. The importer accepts the supplied NSW/VIC layout and the application's **Opportunities** export. A blank template is available from the import dialog. Use a Region column, a detectable NSW/VIC source heading, or the default-region selector. Put separate builders on separate lines or in numbered builder columns; punctuation inside a company name is preserved.

The preview shows new records, records already present, changed existing records that will be skipped, invalid rows and source warnings. Large previews state how many workbook rows are represented. The import limit is 15 MB and 10,000 actual opportunities, with additional limits on expanded workbook size and table dimensions. Missing formula results in imported fields must be recalculated and saved in Excel before import. The derived Remaining Time column is not used to determine expiry.

**Opportunity imports add missing projects only.** Existing project details, decisions, assignments, editing permissions and deleted records are preserved. Changed duplicates are explicitly reported as **kept app values / skipped**; use the opportunity editor to change those existing records. This differs from the earlier Tender-submission importer described in older README sections.

Exported Opportunity IDs provide stable matching even when a workbook title changes. Other matches use region and normalized project name. Conflicting duplicate rows and invalid data must be corrected before application, and a changed database requires a fresh preview. The import is transactional, so invalid rows do not leave a partially applied workbook.

Historical status values in later uploads remain source information. They do not bypass the approval permissions: newly imported records begin Awaiting approval, or Expired if their closing date has passed. Export follows the register's active filters, includes multiple builders and the recorded fields, and writes notes as literal text rather than executable spreadsheet formulas.

## Performance and mobile layout

The Opportunities interface loads when opened. Lists use server-side filtering and pagination, delayed search requests, cancellation of superseded requests and bounded activity loading. The inbox uses per-user read receipts, and reading an alert does not invalidate an Excel opportunity preview. Database indexes support status, region, assignment, deadline and activity queries.

Desktop, mobile, light and dark layouts retain the existing TEC workspace colours: teal for Estimator and yellow for Tenders. Forms, status views, assignment controls and source information adapt to narrow screens. Loading states and actionable error messages keep the current task visible during requests.

These changes reduce unnecessary work; production responsiveness still depends on the deployment and database. No production load benchmark is claimed.

## Reliability fixes

The opportunity detail panel stays in place while its approval, editing or assignment dialog is open. Closing a dialog restores an interactive detail panel, including its Activity tab, without a leftover overlay blocking clicks.

The shared Tender store now keeps an idle database connection for the server worker's lifetime, following the existing Estimator approach. Migration and backup connections close explicitly, and an orderly server shutdown releases the Tender store. Concurrency and restart checks cover writes, reads, inbox operations, backups and database integrity.

The local launchers and deployment runtime check include the new `tzdata` dependency. Shell launchers use Unix line endings so they can run on Linux and macOS; the Windows launcher remains available.

## Installation and data compatibility

- The full and changed/new-file ZIPs are code packages. Live databases, credentials, uploads and Git history are not supplied in them.
- Overlay files at the existing project root, keeping the folder structure. Preserve the live `data/` folder, database files and sidecars, `.env` files, uploaded files, `.git`, Python environment and hosting configuration.
- A consistent backup of both current databases before updating is strongly recommended. Preserve that backup separately from rotating scheduled backups until the update has been checked.
- Install `requirements.txt` into the interpreter used by the application. This release adds **tzdata** so regional date handling also works on systems without a system time-zone database, including Windows.
- Both frontends' built assets are included. Copy the source and referenced assets together; no Node build is required to run the supplied ZIPs.
- Restart the existing application server or Passenger process. `/api/health` should report `release: "3.5"` and `schema_version: 31`.
- Estimator schema 31 remains in use. The separate Tender database creates the opportunity, notification and audit tables automatically. Per-workbook markers make the supplied opportunity seed a one-time operation on both existing and fresh installations.
- A fresh installation can initialize a new database, but recovering existing estimates and users requires the operator's existing live databases or backups; they are not reconstructed from this code package.

The detailed local and Passenger update steps are in [UPDATE_INSTRUCTIONS_V3.5.txt](UPDATE_INSTRUCTIONS_V3.5.txt). No live deployment was performed as part of preparing this release.
