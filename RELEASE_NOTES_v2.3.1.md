# TEC ConEst - internal release 2.3.1

## Quotation import

- Reworked text-based TLE PDF parsing to identify supported columns from their headings, support standard and compact tables, and handle numbered continuation rows. Unpriced values such as TBA are kept unpriced, not changed to zero.
- Added descriptive errors for empty/invalid files, unsupported or scanned layouts, encrypted PDFs, missing parser dependencies, hosting response failures and database contention. Unknown server failures receive a reference that can be matched to the server log.
- Changed the workflow to **Check quotation -> review -> Import selected**. The first check writes no supplier prices. Review cards show existing matches, quoted/parsed totals, extracted rows and unpriced/excluded-row warnings.
- Exact duplicates are skipped. Revised quotes and matching data under another reference are unchecked until explicitly selected. They become separate records, preserving existing prices, manual edits and photos.
- Comparison uses quotation reference/date and normalized line content, not only the uploaded filename. Temporary reviews are account-bound, expire in 30 minutes and can be cancelled. Database rechecks and import receipts protect against concurrent/repeated submissions.
- Removed the unsafe browser direct-import shortcut. An old cached interface is told to refresh and use the review flow.

## Account identity

- Added optional contact number to My profile and the administrator's user editor.
- Added a centered circular profile picture with upload, drag/drop, local preview, change and remove-to-initials controls. Save profile persists the changes.
- Added the small circular photo/initials beside the sidebar name, including mobile navigation.
- Profile pictures are authenticated, normalized, stripped of metadata and stored in the existing database. Account deletion also removes the private picture.
- Removed the visible version from the browser title and branding. Internal release/schema markers remain for support.

## Automatic database upgrades and deployment

- All public application database connections now prepare the required schema automatically, not only the command-line launcher. Internal schema is 24.
- Existing databases receive a verified, protected pre-upgrade snapshot before schema changes. Process/thread locking coordinates workers; current databases use a cached readiness check. Newer schemas are rejected rather than downgraded.
- Added contact/avatar storage and quotation fingerprint/review receipt data without replacing the database.
- Updated the supplied GitHub/cPanel workflow to install dependencies with the detected production interpreter, preserve runtime data/configuration, restart Passenger and verify the new release and database via its health endpoint.

See `UPGRADE_v2.3.1.md` for deployment and backup behavior and `TEST_REPORT_v2.3.1.md` for what was actually verified. The exact supplier PDF from the reported screenshot and the live hosted environment were not available for testing.
