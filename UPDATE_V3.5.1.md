# TEC ConEst v3.5.1

Release date: 21 October 2026. Application release: **3.5.1**. Estimator database schema: **31**.

This update improves Tender startup diagnostics, provides a blank Opportunities Excel template, and implements the owner's request to clear the opportunity register once before adding new projects. The v3.5 workflow, permissions, notifications and existing visual themes remain available.

**Installing this release will empty the opportunity register on its first Tender initialization.** A verified safety backup is required when existing opportunity data is present. This package has been prepared locally; it has not been deployed and has not deleted opportunities from the live website.

Follow [UPDATE_INSTRUCTIONS_V3.5.1.txt](UPDATE_INSTRUCTIONS_V3.5.1.txt). The changed-files ZIP is an overlay for the previously delivered **v3.5**. The full ZIP contains the complete application code. Both include compiled frontend assets and the blank template.

## Confirmed hosted observations

These observations were made before this update was deployed:

| Check | Observed result | What it establishes |
| --- | --- | --- |
| `/api/health` | HTTP 200, release `3.5`, schema `31` | The existing application and basic Estimator health route responded. |
| `/tenders` | HTTP 200 for the page shell | The Tender page shell was reachable. |
| Session and Tender bootstrap requests without authentication | HTTP 401 | Those requests required sign-in. They did not reproduce the reported authenticated startup exception. |
| Opening the website in the browser | Login page displayed | The public entry page was reachable. |

The exact exception encountered by a signed-in user on the hosted site remains **unconfirmed**. A healthy page shell and basic health response do not exercise every part of authenticated Tender startup. Missing dependencies, a different Passenger Python environment, database paths or permissions, and an old worker process are possible causes to investigate. None is presented as the confirmed diagnosis.

## Startup errors and recovery feedback

The server now reports startup failures with a safe HTTP 503 response and a diagnostic code:

| Code | Meaning |
| --- | --- |
| `SESSION_STARTUP_FAILED` | Application or sign-in startup could not complete. |
| `TENDERS_STARTUP_FAILED` | The Tender store or required runtime checks could not complete. |

The browser receives a short message and `error_reference`. The corresponding reference and full exception traceback are written to the server log. Raw exception text and server filesystem paths are kept out of the browser's startup message.

The Tender startup screen preserves the existing session when the server fails. It provides Retry or Reload feedback for connection failures, timeouts, unavailable services and unexpected responses. A real HTTP 401 still sends the user to sign in. Session and Tender bootstrap data are validated before the workspace opens, so malformed data produces a recovery screen instead of being treated as valid application data.

If a save request loses its connection, the request feedback tells the user to refresh and check the saved state before submitting again. A mutation with an uncertain outcome is not automatically repeated.

## Deeper deployment health check

Use `/api/health?check=tenders` after installing the complete update and restarting the application. A successful response includes:

```json
{
  "success": true,
  "status": "ok",
  "release": "3.5.1",
  "schema_version": 31,
  "checks": {
    "tenders": "ok",
    "opportunities": "ok",
    "timezones": "ok",
    "sqlite": "ok"
  }
}
```

The check opens the actual Tender store, exercises the user/team directory path, verifies opportunity and notification tables, checks SQLite JSON and UPSERT support, and checks regional timezone availability. It verifies write access with a transaction that is rolled back and returns readiness labels without publishing server paths.

**This endpoint initializes the Tender store. Its first call after this update can perform the one-time opportunity reset below.** Database initialization and the reset are separate from the rolled-back write probe.

The deployment workflow now requires this deeper check to pass, including the expected release and schema. Basic `/api/health` remains available, but its success alone does not establish Tender readiness. Follow a successful deeper check by opening Tenders with the user's normal signed-in account.

## Owner-requested opportunity reset

The reset runs once when v3.5.1 first initializes the active Tender database. This may happen through the website, the deeper health check, or a configured worker that opens the Tender store.

Before clearing a nonempty register, the application creates and verifies a SQLite backup of the active Tender database. It is stored alongside that database in:

```text
upgrade_backups/<database-stem>-before-opportunity-reset-v351-<timestamp>-<suffix>.db
```

This location follows the actual Tender database path, including a custom `CONEST_TENDERS_DB_PATH`; it is not necessarily the default `data/` folder. The backup is a portable file containing the pre-reset Tender database. The server log records its location. An already empty register needs no reset backup.

If backup creation, verification or the reset transaction fails, opportunity records are not cleared. The application reports the startup failure so an administrator can resolve it and retry.

The reset removes all existing opportunity records, including previously deleted records and their duplicate-matching keys. It also clears opportunity assignments and delegated editing access, the opportunity builder directory, deadline-event keys, and opportunity notifications. A new workbook can then add projects with names or IDs that existed before the reset.

It preserves Estimator data, accounts and teams, Tender submissions, chase history, reminders, region configuration, and audit/contribution history. Historical opportunity actions remain available as history even though their old projects are no longer in the working register. Builder suggestions originating from Estimator projects or Tender submissions are not removed by clearing the opportunity-specific directory.

The marker `opportunities-owner-reset-v351` is committed with the reset. New opportunities entered or imported afterwards survive later requests, process restarts and repeated deployment health checks. The packaged seed is empty and startup no longer imports the earlier opportunity workbooks.

### Recovering a pre-reset database

The safety backup contains the whole Tender database at that time. Restoring it may replace later Tender changes as well as recovering opportunities. Preserve the current state and review the required recovery scope first.

Stop all application processes and deadline workers before restoring. A pre-reset backup lacks the completed v3.5.1 reset marker, so restoring it and immediately starting the same reset-enabled code would clear the register again. Use compatible code that will not rerun the reset, or have an administrator deliberately establish the appropriate marker state after reviewing the restored database. Do not overwrite an active database or delete SQLite WAL files as a recovery shortcut. The installation instructions give the full sequence.

## Blank Opportunities import template

The [blank template](templates/opportunities_import.xlsx) is included in the application and served by **Import Excel → Download template**. A separate copy is supplied with the release downloads. Both copies are the same workbook.

The **Opportunities** worksheet has 100 prepared blank rows starting at row 8. Project Name and Region remain visible during horizontal scrolling, and the headings remain visible during vertical scrolling. It provides an NSW/VIC dropdown, Australian date formatting, date and numeric validation, and an **Instructions** worksheet. No example projects are included.

Its 15 columns are:

| Column | How to use it |
| --- | --- |
| Project Name | Required. Use one opportunity per row. |
| Region | Required. Choose NSW or VIC. |
| Closing Date | Optional real date, displayed as `dd/mm/yyyy`. Leave blank if unknown. |
| Builders | Enter each builder on a separate line in the cell. |
| Working Scope | Describe the included work and exclusions. |
| Location | Project address or location. |
| Category | Optional project category. |
| Budget | Total project budget or range as text, such as `5m-10m`. |
| Estimated value (AUD) | Numeric tender value, separate from the total project budget. |
| Distance (km) | Known numeric distance in kilometres. Leave blank if unknown. |
| Distance Origin | Leave blank for the regional default or enter another starting address. |
| Contact person | Project contact's name. |
| Email | Project contact's email address. |
| Added Date | Optional source-register date, displayed as `dd/mm/yyyy`. |
| Notes | Other project or contact information. |

Contact person and Email now map to opportunity fields on import and are included in normal exports. Invalid email addresses are reported in the preview.

When Distance Origin is blank, the importer uses:

| Region | Default distance origin |
| --- | --- |
| NSW | 63-79 Parramatta Rd Silverwater, NSW 2128 |
| VIC | CBD, Melbourne |

Distances remain entered or imported values. The workbook and application do not calculate road distances automatically. The template has no origin formulas, so these defaults do not depend on saved Excel formula results.

Save the completed workbook as `.xlsx`, then choose it or drag it into **Import Excel**. Review the preview and correct errors before applying. The existing limits of 15 MB and 10,000 actual opportunity rows remain. Leave unused rows blank and keep the column headings intact.

Imports add missing opportunities only. Existing app records are kept; changed duplicates are explicitly reported as skipped. Exported Opportunity IDs support stable matching, with region and normalized project name used otherwise. Approvals, assignments and editing permissions are managed in the website. Uploaded source status values cannot approve a project or bypass permissions.

## Deployment points

Use the actual Python interpreter configured for Passenger to install `requirements.txt` and run `tools/check_runtime.py`. The runtime check verifies Python 3.10 or newer, required packages including `tzdata`, SQLite JSON and UPSERT support, and NSW/VIC timezone data.

The workflow deliberately excludes `passenger_wsgi.py` from automatic synchronization because servers may have local Python settings in that file. **Merge the updated adapter into the server's adapter while preserving local interpreter and hosting configuration.** Updating other files alone does not install its new startup error handling.

Restart the existing cPanel/Passenger application after updating the code, adapter and dependencies. The supplied workflow requests restart through the application's `tmp/restart.txt`. cPanel documents this mechanism in its [Python WSGI application guide](https://docs.cpanel.net/knowledge-base/web-services/how-to-install-a-python-wsgi-application/#restart-the-application). Its [Application Manager guide](https://docs.cpanel.net/cpanel/software/application-manager/) covers application settings and Python log locations.

Preserve live databases, environment files, uploads, runtime folders and repository history when overlaying either ZIP. Built assets are included. Estimator schema 31 remains in use; the separate Tender database initializes its tables automatically.

Confirmation of the hosted authenticated issue still requires deployment, a normal signed-in Tender request, and inspection of any matching server error reference. No live deployment or opportunity deletion was performed while preparing this release.
