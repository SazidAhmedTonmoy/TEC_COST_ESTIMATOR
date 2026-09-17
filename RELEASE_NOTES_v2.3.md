# TEC ConEst v2.3 - Release notes

This release upgrades the supplied v2.2 application. It keeps the existing estimating workflow, shared main database, project snapshots and backup-retention setting.

## What changed

| Request | v2.3 behaviour |
| --- | --- |
| Calendar monthly totals | The selected month shows quoted estimate value, cost before overhead, project count, labour hours, item count, status counts, won/lost counts and values, and a project-by-project table. |
| Optional project result | Manage project has tick Won, cross Lost and Clear controls. Save project applies the choice. Leaving the result blank is valid; it does not change the workflow status. Results also appear on the project board and calendar. |
| Delete account | Admin > Manage users > Edit contains Delete account. Exact username confirmation is required. A signed-in admin cannot delete their own account; active-administrator safeguards are retained. |
| Compact project chooser | Choose a project displays the four most recently updated accessible projects in a scrollable list. Older projects remain available below. The popup also has a name/client search and keyboard navigation. |
| Project-only light reference | Lighting and Emergency & Exit Lighting lines have a Ref. field below Category. It uses the existing lower row on desktop. On small screens it stacks for readability. References are kept with the project, copies and saved tender revisions, not in the reusable catalogue. |
| Excel reference | CONNECTED COST DETAIL places the reference on the next line of the same Item / component cell: item name, then Ref: D1. The cell wraps; the row height is adjusted. |
| Explained lighting prices | Cards and expanded details use the same calculation. The details distinguish main-row rate, connected package total, primary divisor and package unit price. The row table explains quantities, rates, quoted totals, calculated totals, inclusions, differences and contributions per primary unit. |
| Editable lighting library | Edit light name, searchable nickname, notes, unit label, primary divisor, quote working labels and component descriptions, suppliers, catalogue numbers, quantities, rates, quoted totals and pricing status. Add components or exclude existing ones without destroying the source record. |
| Photos | Choose an image file, drag/drop it, or paste clipboard image data into the photo area. A light has one editable photo. Photos are normalized and stored in the main database, so they are included in normal database backups. |
| Supplier-price import position | Add supplier prices is now at the top of Light price check. Existing XLSX and TLE-PDF import support remains. |
| Inline details | Clicking a light expands its details immediately beneath that result rather than moving the user to the page bottom. Close collapses it. |
| Floating search | The round search control at the lower right of Light price check scrolls to and focuses that page's search field. |
| Sidebar order | Home > Calendar > Estimate > Catalog > Imports > Light price check > Manage users > My profile > App settings. Regular users see the same order with admin-only entries omitted. |

## How monthly figures are defined

The calendar uses submission deadlines: a project is included when its deadline falls in the selected month. Undated projects are excluded from these monthly sums. A separate count shows projects created during that month, regardless of their deadlines. All projects must be accessible to the signed-in user.

Figures are the current saved estimates, not a historical month-end snapshot. Quoted values exclude GST. The cost-before-overhead figure uses the application's existing direct-cost total, which already includes material markup plus labour. Different currencies are shown separately, not added together. Won and Lost are optional tender outcomes, not workflow statuses and not booked revenue.

## How the lighting calculation works

For each included component, explicitly choose one of:

- Quoted total: use the working quoted row total, even when it differs from quantity x unit rate.
- Qty x rate: calculate the row total from its quantity and unit rate, rounded to cents.

Package supply per primary unit = sum of the included selected row totals / primary quantity.

Example: 10 fittings have a quoted body total of $190.00, five drivers total $50.00, and freight totals $30.00. With all three rows included, the package is ($190 + $50 + $30) / 10 = $27.00 per fitting. The body's listed $20.00 rate is not the same as the connected package rate; the $10.00 body-total discrepancy is flagged. Choosing Qty x rate for the body makes the package $28.00. Excluding freight as well makes it $25.00.

Blank prices mean unpriced, not free. A zero is an explicit zero price. An included unpriced row, zero/missing divisor, or no included rows prevents a misleading complete unit price. Blank-type rows inherited from a previous primary row are flagged for review. Quoted totals and original imported source values remain visible, and edits are recorded in an audit history. Group-level quote labels do not rewrite other lights from the same original quote.

The calculated package covers included supply rows only: installation, project markups and GST are not silently added. Price-library edits do not automatically reprice saved estimates or overwrite reusable catalogue items.

## Reference field storage

A project must retain its reference when reopened. The value is therefore stored in the project-line part of the existing database, not in the shared catalogue or as a new catalogue record. No new catalogue item is created by typing a reference. References also survive copying a line/project, saving a tender revision and using the full estimate-item editor.

## Photo use

Open a light, choose Edit details / photo, then upload, drop or paste an image. For an image copied from a browser, use Copy image rather than Copy image address. Click the photo area and press Ctrl+V (Windows) or Cmd+V (Mac). Press Save light details to persist it. A preview alone is not a saved photo.

Accepted input: PNG, JPEG, WebP, GIF or BMP, up to 12 MB and 20 megapixels. Images are re-encoded, metadata is stripped and the longest side is limited to 1600 pixels; the stored image must be at most 4 MB. GIF input is stored as a still image. SVG files and remote image-address fetching are not supported. An image address or clipboard content without image data produces a helpful message rather than a false success. Only signed-in users can retrieve saved photos.

## Account deletion and retained work

Deletion removes the login and revokes its sessions. Projects, estimates, notes, revisions and activity remain, with the former author's name retained where needed. Projects owned by the deleted account transfer to the deleting admin; project-team assignments remain. Other users' note-read receipts are retained. Deleting an account is not a deletion of all personal attribution in historical work.

## Upgrade

Use UPGRADE_v2.3.md. The update-only ZIP deliberately contains no database. The full ZIP includes the exact database snapshot supplied with v2.2; do not copy it over a newer production database. No production deployment was performed while preparing this release.

## Validation

See TEST_REPORT_v2.3.md. The included automated test suite has 21 passing tests. UI checks used a controlled in-memory Chromium harness and a running local application API. They are not a claim of a completed deployment or certification of every browser/operating-system combination.
