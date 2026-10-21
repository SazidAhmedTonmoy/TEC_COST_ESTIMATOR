# Opportunities start empty in v3.5.1

The packaged opportunity seed contains **zero records**. Earlier opportunity workbooks are no longer loaded at startup. Use the blank [Opportunities import template](../templates/opportunities_import.xlsx) to enter the new projects that should appear in the register.

The owner requested that the existing register be cleared before adding new data. When this release first initializes the active Tender database, it performs that reset once. This package has not already cleared the live website. The reset takes effect when the updated application or a worker opens that database. The deeper `/api/health?check=tenders` check also opens the store and can trigger the reset.

## What the reset does

For existing opportunity data, a verified SQLite safety backup is created in the active Tender database folder under:

```text
upgrade_backups/<database-stem>-before-opportunity-reset-v351-<timestamp>-<suffix>.db
```

The backup contains the pre-reset Tender database. Backup failure leaves the opportunity records in place.

The reset clears current and previously deleted opportunities, their matching keys, assignments and delegated editing access, the opportunity-specific builder directory, deadline-event keys, and opportunity notifications. It preserves Tender submissions, reminders and chase history, Estimator data, accounts and teams, region settings, and audit/contribution history.

A completion marker is committed with the reset. New opportunities and later imports survive subsequent starts. The packaged `seed.json` stays empty, and startup does not call the legacy workbook-seeding routine.

## Adding new records

The template contains an **Opportunities** worksheet with 100 blank entry rows and an **Instructions** worksheet. It includes no example projects. Project Name and Region are required. Enter multiple builders on separate lines, keep budget ranges separate from numeric tender values, and leave unknown dates or distances blank.

When Distance Origin is blank, NSW uses **63-79 Parramatta Rd Silverwater, NSW 2128**, and VIC uses **CBD, Melbourne**. Distances are entered or imported values; road distances are not calculated automatically.

Choose or drag the completed `.xlsx` file into Import Excel, review the preview, correct errors and apply. Imports add missing projects and keep existing app records. Changed duplicates are identified as skipped. Approval, assignment and editing permissions are managed in the app.

Original cells and source decisions from new uploads remain attached as source information. Uploaded approval/status values cannot approve an opportunity or bypass the workflow permissions.

For deployment and recovery, read [UPDATE_INSTRUCTIONS_V3.5.1.txt](../UPDATE_INSTRUCTIONS_V3.5.1.txt). A pre-reset backup lacks the completed reset marker; restoring it requires stopped workers and a deliberate plan to prevent the reset from running again.
