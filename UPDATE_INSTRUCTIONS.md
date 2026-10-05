# TEC ConEst v3.2 — Tender Excel update

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


Changed files

- README.md
- TENDERS_UPDATE.md
- app.py
- conest_app/__init__.py
- conest_app/tender_export.py
- conest_app/tender_export_visuals.py
- conest_app/tender_http.py
- conest_app/tender_import.py
- passenger_wsgi.py
- tenders_frontend/package-lock.json
- tenders_frontend/package.json
- tenders_frontend/src/components/tender-app.tsx
- tenders_frontend/src/components/tender-import.tsx
- tenders_frontend/src/globals.css
- tenders_web/assets/index-BeJFWl2X.css
- tenders_web/assets/index-BryQ1iqe.js
- tenders_web/index.html
- tests/test_http_v232.py
- tests/test_tender_import.py
- tests/test_tender_integration.py
