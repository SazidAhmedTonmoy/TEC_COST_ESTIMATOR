# TEC ConEst v3.3

## What changed

- Project JSON transfer uses neutral surfaces, subtle borders and a small teal accent in both themes.
- Chase history has a pencil button for editing the date, contact method and note. The original author stays visible; the most recent editor and edit time appear below the entry. Previous values are retained in the database audit history. Conflicting edits return a refresh message rather than overwriting someone else's work.
- New website tenders record their creator and creation time. Excel records show their importer separately. Later imports record the latest importer without replacing first-import attribution.
- Existing Excel tenders are attributed to **Tonmoy**. Historical workbook chase-ups previously labelled Workbook are attributed to **Yunus**. Existing named website authors are preserved. Future Raw Data history has no author column, so it follows the supplied Yunus convention; the import dialog makes this explicit.
- Manage Users includes **View Performance** for administrators. Each person has This month / All time filters, Estimator projects and actions, tender submissions and actions, import row totals, activity breakdowns and the latest 30 actions across both applications.
- Historical Excel attribution is presented separately and excluded from website activity totals. Website tender activity tracking starts with v3.3. Existing Estimator history remains available. These counts do not measure hours worked or quality, and multiple people may contribute to the same project.
- Reports load only when requested. Actor/date indexes support filtering. Chase audit snapshots stay out of the bootstrap payload.

## Deployment

1. Back up the live Estimator and Tenders databases. Keep `.db`, `.db-wal` and `.db-shm` files excluded from Git and never replace live databases with a development copy.
2. Apply the changed-files ZIP over the latest v3.2 Excel-import-fix release, retaining all folder paths. Alternatively, use the full v3.3 code package. Neither ZIP contains a database.
3. Deploy the complete changed file set together, including `conest_app`, source files, `assets/index.html`, fingerprinted Estimator assets and the built `tenders_web` folder. Both frontend builds are already included.
4. Update `passenger_wsgi.py` manually if your existing Git deployment excludes it, then restart Passenger. All workers should use the same new code. No dependency change is needed.
5. The Estimator upgrades to schema **30**, adding an activity index, with the existing protected pre-upgrade snapshot. The Tenders store creates an activity table and performs its one-time attribution migration. An existing tender database gets a `.pre-v33.db` snapshot before this migration.
6. Check `/api/health` for release **3.3**, schema **30**. Sign in, open a tender, edit a chase-up, then use Manage Users → View Performance.

Do not downgrade code against schema 30. To roll back, stop all workers and restore matching code and both database backups together. The supplied user database was tested on a temporary copy; the original was not modified. Only the Estimator database was supplied, so actual live tender data was not directly inspected.

## Verification

- 19 targeted automated tests passed: import/export regression, shared authentication, CSRF, authorship, edit conflicts, administrator-only reporting and review-workflow migration.
- Browser checks passed for the transfer dialog, performance filters, mobile layout and chase edit/save attribution, with no JavaScript errors.
- The supplied database copy passed migration, record-count preservation, integrity and foreign-key checks.
- Both production frontend builds passed. Deployment itself was not performed. Python execution was validated locally on Python 3.12; no claim is made of a live cPanel run or a concurrency benchmark.
