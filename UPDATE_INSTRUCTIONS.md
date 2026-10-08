# TEC ConEst v3.3 — 8 October update

## Included changes

- **View Contribution** replaces View Performance. It defaults to **All Time**, with a specific month, specific year or custom inclusive date range. Date boundaries use Australia/Sydney.
- Three summary cards show Estimator projects, tender submissions contributed to, and documents uploaded. Action breakdowns and recent activity remain available.
- Historical tender imports are linked to the **Tonmoy** account and display **Md Sazid Ahmed Tonmoy**. Historical workbook chase-ups are linked to **Yunus** and display **Muhammad Yunus**. These are account IDs, not just display labels. Existing website authors and editors remain intact.
- Dated historical chase-ups contribute within their original chase dates. Undated historical imports contribute under All Time. A tender submission is counted once per contributor even if they performed several actions.
- Document totals use retained catalogue workbooks, lighting upload/source records, project JSON import actions, completed tender Excel imports and Help attachments. Unknown historical tender file counts are not fabricated. One workbook containing 333 submissions is not counted as 333 documents. Unchanged tender import checks count once when completed, not during preview.
- Estimate item search includes name, Ref., remarks, category, size and component descriptions, case-insensitively.
- Component Copy/Paste is saved per account and synchronized between tabs. A new copy replaces the previous one. It survives refresh, and a refresh icon sits beside Paste component. Other accounts cannot read the clipboard. Copied content is not added to an estimate until pasted and saved.

## Help assistant

Help is available in Estimator and Tenders and saves the latest 30 messages, an editable memory note and up to three extracted attachments to the signed-in account. A clear control removes the conversation, note and extracted attachments. Historical upload counts remain as contribution records.

Supported attachments: text-based PDF (up to 100 pages), XLSX, DOCX, TXT, CSV, JSON and Markdown, up to 10 MB each. Extraction retains up to 60,000 characters per file; spreadsheets read up to 2,000 rows and 40 columns per sheet within that text limit. Scanned PDFs/images need OCR first. Original file bytes are not retained by Help.

Local lookups work without AI. **Use configured Gemini** explicitly enables AI assistance and sends the question, relevant retrieved information, memory and document excerpts to the configured Gemini service. It uses the existing App Settings key/model. A missing, disabled, busy or unavailable AI service falls back to local results. Replies are read-only and do not change estimates or tenders. Live Gemini connectivity was not tested; the opt-in and request construction were tested with a mocked provider.

## Deployment

1. Back up both live databases. Keep all live `.db`, `.db-wal` and `.db-shm` files excluded from Git.
2. Apply this changed-files ZIP over the previous v3.3 release, preserving paths, or deploy the full updated code ZIP. Neither archive includes databases. Both frontend builds are included.
3. Keep source and compiled assets together. This update includes new `conest_app/workspace_tools.py` and `assets/help_shared.css` files. Do not omit them.
4. Restart Passenger after deployment. Keep the existing v3.3 `passenger_wsgi.py`; it is included in the full package and unchanged in this patch.
5. `/api/health` should report release **3.3**, schema **31**. Automatic migration creates account-scoped workspace state and document-upload records, using the existing pre-upgrade backup process. The tender account-link correction runs on first Tender access.

The original supplied database was not modified. A temporary copy upgraded successfully, with unchanged existing record counts, valid integrity/foreign keys, and a pre-upgrade backup. To roll back, stop all workers and restore matching code and database backups; do not run older code against schema 31.

## Verification

20 targeted automated tests passed, covering contribution dates, author identity, edit conflicts, workbook import regression, authentication/CSRF, account isolation, saved Help data, upload counting and explicit AI opt-in. Browser checks passed for all four contribution period modes, Help upload/history across both apps, cross-tab clipboard replacement and refresh, case-insensitive reference/remarks search and mobile overflow. No live deployment or production concurrency benchmark was performed.

## Changed files

- README.md
- UPDATE_V3.3.md
- app.py
- assets/app.4ff0c5cd3fa5.js
- assets/estimate_workspace.js
- assets/help_chat.js
- assets/help_shared.css
- assets/index.html
- assets/performance.js
- assets/project_transfer.js
- assets/workspace.js
- conest_app/auto_upgrade.py
- conest_app/help_chat.py
- conest_app/http_workspace.py
- conest_app/performance.py
- conest_app/tender_import.py
- conest_app/tenders.py
- conest_app/workspace_tools.py
- tenders_frontend/index.html
- tenders_web/index.html
- tests/test_catalog_rating.py
- tests/test_http_v231.py
- tests/test_http_v232.py
- tests/test_item_markups.py
- tests/test_review_workflow.py
- tests/test_v23.py
- tests/test_v231.py
- tests/test_v233.py
- tests/test_v235.py
- tests/test_v33.py
- tests/test_v33_oct08.py

Old fingerprinted assets no longer referenced (optional cleanup after deployment):

- assets/app.91603b738d0d.js
