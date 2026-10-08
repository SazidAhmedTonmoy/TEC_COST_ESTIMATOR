# TEC ConEst v3.3 — 8 October update

## Latest layout and chat patch

- View Contribution retains summary counts and activity charts. Removed the historical explanation panel, detailed recent activity list and long footnote; recorded data and attribution are unchanged.
- All five progress cards share one desktop row. Small screens can scroll the row horizontally.
- Help header buttons have equal dimensions. The Project/Normal button switches between workspace questions and general chat. Greetings no longer trigger catalog searches.
- The model selector below the composer uses the app's existing Gemini model list, with App default initially selected. General AI answers require the configured Gemini service and the existing explicit AI opt-in. Normal chat does not retrieve workspace records or include prior Project-mode messages in its AI context; saved memory and uploaded attachments remain available.
- Nine targeted tests and desktop/mobile browser checks passed. Model selection and context isolation were verified with a mocked AI provider; live provider availability was not tested.

## Previous patch — live values, contribution correction and Closed

- Rates and mark-ups save automatically after a 450 ms typing pause, recalculate totals and show saving/error feedback. Save now remains available. Sequential saves preserve edits made while a request is in flight; existing revision checks protect against conflicting edits.
- Tonmoy is credited with **two historical tender Excel uploads**, not 333 submissions worked on. Importing rows is not submission work. Future imports count as additional documents. The two undated historical uploads appear under All Time only; dated website contributions remain unchanged.
- Estimator progress now includes **Closed** after Submitted, for rejected or unsubmitted work. Closed projects remain visible and retain their estimate, but their values and hours are excluded from calendar totals. Closing removes review deadlines and schedule reminders. Project JSON import accepts Closed.
- Help uses a chat layout with Clear beside Close, an attachment button in the composer, and Settings for saved memory and attachments. Look in is removed; scope is always Auto. Enter sends and Shift+Enter adds a new line. Clear removes the conversation while retaining memory/files; Reset in Settings removes all three.

## Included changes

- **View Contribution** replaces View Performance. It defaults to **All Time**, with a specific month, specific year or custom inclusive date range. Date boundaries use Australia/Sydney.
- Three summary cards show Estimator projects, tender submissions contributed to, and documents uploaded. Action breakdowns and recent activity remain available.
- Historical tender imports are linked to the **Tonmoy** account and display **Md Sazid Ahmed Tonmoy**. Historical workbook chase-ups are linked to **Yunus** and display **Muhammad Yunus**. These are account IDs, not just display labels. Existing website authors and editors remain intact.
- Dated historical chase-ups contribute within their original chase dates. The two confirmed historical Excel uploads contribute to documents under All Time only. A tender submission is counted once per contributor even if they performed several actions.
- Document totals use retained catalogue workbooks, lighting upload/source records, project JSON import actions, completed tender Excel imports and Help attachments. The owner-confirmed historical tender file count is two. One workbook containing 333 submissions is not counted as 333 documents. Unchanged tender import checks count once when completed, not during preview.
- Estimate item search includes name, Ref., remarks, category, size and component descriptions, case-insensitively.
- Component Copy/Paste is saved per account and synchronized between tabs. A new copy replaces the previous one. It survives refresh, and a refresh icon sits beside Paste component. Other accounts cannot read the clipboard. Copied content is not added to an estimate until pasted and saved.

## Help assistant

Help is available in Estimator and Tenders and saves the latest 30 messages, an editable memory note and up to three extracted attachments to the signed-in account. Clear removes only the conversation; Reset in Settings also removes the note and extracted attachments. Historical upload counts remain as contribution records.

Supported attachments: text-based PDF (up to 100 pages), XLSX, DOCX, TXT, CSV, JSON and Markdown, up to 10 MB each. Extraction retains up to 60,000 characters per file; spreadsheets read up to 2,000 rows and 40 columns per sheet within that text limit. Scanned PDFs/images need OCR first. Original file bytes are not retained by Help.

Local lookups work without AI. **Use configured Gemini** explicitly enables AI assistance and sends the question, relevant retrieved information, memory and document excerpts to the configured Gemini service. It uses the existing App Settings key/model. A missing, disabled, busy or unavailable AI service falls back to local results. Replies are read-only and do not change estimates or tenders. Live Gemini connectivity was not tested; the opt-in and request construction were tested with a mocked provider.

## Deployment

1. Back up both live databases. Keep all live `.db`, `.db-wal` and `.db-shm` files excluded from Git.
2. Apply this changed-files ZIP over the previous v3.3 release, preserving paths, or deploy the full updated code ZIP. Neither archive includes databases. Both frontend builds are included.
3. Keep source and compiled assets together. This update includes new `conest_app/workspace_tools.py` and `assets/help_shared.css` files. Do not omit them.
4. Restart Passenger after deployment. Keep the existing v3.3 `passenger_wsgi.py`; it is included in the full package and unchanged in this patch.
5. `/api/health` should report release **3.3**, schema **31**. Automatic migration creates account-scoped workspace state and document-upload records, using the existing pre-upgrade backup process. The tender account-link correction and confirmed two-file attribution run on first Tender access.

The original supplied database was not modified. A temporary copy upgraded successfully, with unchanged existing record counts, valid integrity/foreign keys, and a pre-upgrade backup. To roll back, stop all workers and restore matching code and database backups; do not run older code against schema 31.

## Verification

26 targeted automated tests passed, covering contribution dates, author identity, edit conflicts, workbook import regression, authentication/CSRF, account isolation, saved Help data, upload counting and explicit AI opt-in. Browser checks passed for all four contribution period modes, Help upload/history across both apps, cross-tab clipboard replacement and refresh, case-insensitive reference/remarks search and mobile overflow. No live deployment or production concurrency benchmark was performed.

Latest browser verification: automatic rate/mark-up saving and totals, consecutive edits, Closed calendar exclusion, Auto scope, Enter/Shift+Enter, composer upload, memory retention after Clear, desktop and mobile layouts.

## Changed files

- README.md
- UPDATE_V3.3.md
- assets/app.c21ea600d619.js
- assets/help_chat.js
- assets/help_shared.css
- assets/index.html
- assets/performance.js
- assets/styles.48e084448ef9.css
- assets/styles.css
- conest_app/workspace_tools.py
- tenders_frontend/index.html
- tenders_web/index.html
- tests/test_v33_oct08c.py

Old fingerprinted assets no longer referenced (optional cleanup after deployment):

- assets/app.fe8aff0f6061.js
- assets/styles.f11371c84658.css
