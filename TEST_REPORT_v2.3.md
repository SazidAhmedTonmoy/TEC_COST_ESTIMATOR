# TEC ConEst v2.3 - Test report

## Automated regression suite

Command: python -m unittest discover -s tests -v

Result: 21 tests passed (7 retained release tests and 14 v2.3 tests).

Coverage includes existing fixed quantities, copying/exporting, backup retention and restore, deadline validation, access-limited help; idempotent migration; legacy note/read-receipt preservation and deleted-ID sequencing; optional outcomes and revision conflicts; project-only references, full item edits, line/project copies, tender snapshots and wrapped same-cell Excel export; shared card/detail price arithmetic, explicit total selection, exclusions, unpriced versus zero handling, decimal rounding, manual components, concurrent edit conflicts, immutable source data; image normalization and invalid input rejection; account deletion safeguards, session revocation and historical work retention.

All JavaScript asset files passed node --check. app.py and conest_app passed Python compile checks. Both startup launchers were updated to check Pillow. The Windows batch launcher itself was not executed on Windows in this Linux test environment.

## Migration of the supplied database

A fresh temporary copy of the exact supplied database was initialized twice. Integrity check: ok. Foreign-key violations: none. Before/after counts were identical:

| Table / record type | Preserved records |
| --- | ---: |
| Users | 8 |
| Projects | 4 |
| Estimate lines | 246 |
| Catalogue items | 3,652 |
| Lighting packages | 880 |
| Lighting component rows | 1,359 |
| Supplier quotes | 40 |
| Project notes | 1 |
| Note read receipts | 1 |

The full package's bundled database remains byte-for-byte identical to the uploaded one. Migration/UI tests used separate temporary database copies. Test users, passwords, photos, edits and QA projects are not included in either release package.

## Interface and API checks

A Chromium/Playwright harness rendered the actual HTML, CSS and JavaScript in memory. Browser API calls were bridged through Python to a running local app and a separate QA database. Managed Chromium policy prevented direct browser navigation to the local server; no browser policy was changed. These checks therefore exercise the UI and API, but do not constitute a normal-origin end-to-end deployment test.

Passed: admin navigation order; calendar summary and table; reference editing; four visible 58-pixel project options in a 232-pixel scroll area; older-project scrolling and search; optional Won save; inline price expansion; editable name/nickname and nickname search; selected price basis; photo upload/save and authenticated retrieval; search-button focus; disposable-account deletion. No JavaScript page errors were recorded.

Additional checks passed: dark desktop reference alignment with no supply/ref overlap; 414-pixel-wide estimate, calendar and light editor without document-level horizontal overflow; synthetic image-paste and file-drop event handlers followed by save; anonymous photo access blocked; missing CSRF token and invalid Origin blocked; normal-user navigation order and forbidden account deletion.

## Limits and deployment acceptance

No live cPanel deployment, Windows/Mac startup session, OS clipboard interaction with Google Images, high-concurrency load test or exhaustive browser compatibility test was performed. Clipboard handlers were checked with synthetic image events, not an actual external-site Copy image operation. Normal-origin cookies, hosting proxy behaviour and real clipboard permissions should be included in your deployment acceptance check. The image file-upload path is available when clipboard image data is unavailable.
