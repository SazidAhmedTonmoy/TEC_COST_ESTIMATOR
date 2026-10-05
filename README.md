# TEC ConEst — v3.2

TEC ConEst combines the Estimator and Tenders workspaces for electrical estimating and tender management.

**Release:** v3.2  
**Release date:** 5 October 2026

The last three updates are grouped under **v3.2**. This README updates the release documentation only; it does not change application code or database files.

## What's new

### Project JSON import and export

- Open **Project JSON** from the Home page.
- Export a selected project as a JSON file.
- Upload a compatible JSON file to create a new project.
- Download an example JSON file from the same window.
- Transfers include project settings, estimate items, quantities, component costs, labour allowances, fixed quantities, supply overrides, mark-up exclusions and remarks.
- Imported projects receive new IDs and belong to the importing user. Existing projects are not overwritten.
- User access assignments, shared catalogue links, activity history and saved revisions are not transferred.

### Copy and paste components

- Use **Copy** beside a component row in the item editor.
- Open another catalogue or estimate item in the same browser tab and select **Paste component**.
- Save the destination item using the appropriate save option.
- Copying another row replaces the previous clipboard contents.
- A **Copied: …** label identifies the selected component; **Clear** empties the clipboard.

### This month project view

- **This month** is the default Project Board filter on sign-in and refresh.
- Shows projects with submission deadlines in the current calendar month, using **Australia/Sydney** time.
- Includes all progress stages; search and sorting remain available.
- Select **All projects** to view projects outside the current month or without a deadline.

### Refreshed project transfer window

- Teal export and blue import cards.
- Clearer headings, tighter spacing and coordinated light/dark colours.
- Responsive layout for smaller screens.

### Blueprint split login

- Electrical blueprint artwork beside the sign-in form.
- Navy and teal styling with TEC ConEst branding.
- Password visibility control, clear error feedback and a signing-in state.
- Responsive desktop and mobile layouts.
- Lightweight local SVG artwork, a brief entrance animation and reduced-motion support.

## Existing workflow

Project progress remains **Not started → In progress → In review → Submitted**. In review supports its own review deadline; Submitted is the final stage. Existing estimating, tender management, permissions, remarks and catalogue rating features continue to apply.

## Data and deployment

- Database schema remains **29**; the v3.2 release grouping requires no new database migration.
- Keep production database files excluded from Git and deployment uploads.
- Do not replace the live database when applying application updates.
- Project JSON is an estimate-transfer format, not a complete database backup.
- This documentation-only update does not require an application restart.

## Validation completed with these updates

- Project JSON export/import preserved estimate totals in round-trip tests.
- Browser checks covered repeated copying, replacing, pasting and clearing components.
- Monthly filtering was checked against Sydney month boundaries.
- Login checks covered successful and rejected sign-in, password visibility, logout, mobile layout and reduced-motion behaviour.
