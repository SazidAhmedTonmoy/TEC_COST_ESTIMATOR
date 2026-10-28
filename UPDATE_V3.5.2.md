# TEC ConEst — requested V3.5.2 update

Built on the recovered v3.7.1 delivery; existing features and the internal application/schema version are retained to avoid a downgrade.

Changes
- Opportunities defaults to Recently updated, including the API default.
- Native dropdowns use readable theme-matched backgrounds and text in light/dark mode.
- Register header shows latest matching opportunity, added/updated actor and local date/time, independent of the current page.
- Chase-up tables include sortable Submission date and Last follow-up date columns. Submission date uses actual submittedDate, not the deadline; missing dates display Not recorded. Chase-up notes remain separate.

Installation
Extract CHANGED_FILES into the application root, overwriting matching files; or use FULL as a complete code package. Restart Passenger/application workers and refresh the browser. No database is included or replaced. No schema migration is required for this patch. Prebuilt Tender assets are included; a server-side npm build is unnecessary.

Validation
Production frontend build and TypeScript checks passed. Regression suite and a focused activity filter/pagination test were run. Browser visual verification and live deployment were not performed.
