# TEC ConEst v1.20 — user and maintenance guide

TEC ConEst is a shared electrical estimating application. One office computer runs the Python server and holds the SQLite databases. Team members use a browser to connect. The database is the source of saved catalogue prices, accounts, projects and estimates; imported Excel originals are not required to run the application.

## 1. Start and upgrade

### First start
1. Extract the complete ZIP into a new folder on the host computer.
2. Install Python 3.10 or newer. Double-click `START_TEC_SERVER.bat` on Windows. The launcher creates a private Python environment and installs the required Excel and PDF libraries if missing; that first setup needs internet access.
3. Keep the server window open. The host uses `http://127.0.0.1:8080`. Other users enter the host's team URL printed in the window, for example `http://192.168.1.25:8080`.
4. Allow Python on the private network through Windows Firewall when prompted. Keep the host awake. Stop with Ctrl+C.
5. On Linux/macOS, use `sh run.sh` instead.

Use one server process and keep the database on the host's local disk. Users connect to the server, not directly to the database. Changing the host's IP address changes the address other users need. A reserved local IP is convenient. This package is intended for the office network; it does not include public hosting, HTTPS certificate management or a reverse proxy.

### Upgrade an existing installation
1. Create a backup from App settings → Database backups, or run `BACKUP_DATABASE.bat`.
2. Stop the old server. Retain the old folder and backup.
3. Extract this ZIP into a new folder.
4. Put your latest backup in the new folder as `data/conest_catalog.db`, replacing the bundled snapshot **before first start**. This preserves newer catalogue edits, users, passwords, notes and projects saved on your own computer.
5. From v1.19 onward, also retain your latest `data/lighting_prices.db`. Stop the server before copying it. For this first upgrade, use the included supplier database. Copy `data/lighting_backups` if you want its earlier import backups. Copy `data/backups` as well if you want earlier in-app backups available. The standalone backup utility uses a separate top-level `backups` folder.
6. Start the new server. Database migrations run automatically. Do not replace a running database by copying a file over it.

The included database is a shared snapshot, not a live copy of your computer. This v1.20 package uses your latest uploaded conest_catalog.db: **3,652 catalogue items, 24,256 catalogue components, 4 projects, 246 estimate items and 8 accounts**. Startup adds any missing earlier fields plus crew size and hours per day, while preserving the values already saved in your database. Existing accounts keep their passwords. The original eight active testing accounts bypass initial setup; newly created accounts still use the setup workflow.

## 2. Everyday use

### Home, teams and projects
The project board shows accessible projects, their status and deadlines. Use its search bar to locate a project. Team members can work on projects assigned to their team, and a project created by a user is shared with their team. Administrators can manage all projects, users, roles and teams. Newly created user projects appear for admin review. Completed projects from other teams are visible for reference; viewing permission does not automatically grant editing permission.

My profile contains personal details and team membership. Administrators can rename teams, change members, promote or demote users, and activate/deactivate accounts through management screens. The deadline calendar and homepage reminders help identify approaching and overdue submissions. The activity record attributes project changes to users.

### Build an estimate

1. Open a project and type an item title into the main search bar. Suggestions appear as you type. Select an item to review its build-up, then add the required Qty. **Zero is allowed**, so an item can remain in the estimate while its quantity is still undecided.
2. The round **search icon** at the lower right scrolls to and focuses that main search bar. The **↓ button** goes to the bottom of the estimate. Clearing the search text or pressing × removes the result and cancels pending searches.
3. **Find in estimate** searches the items already added, including their names, sizes, scopes and component descriptions. It changes only what is visible; the quoted total and Excel export still include the whole estimate. Clear this field to show the full list.
4. Items are grouped by scope. Use **+/− beside a scope** to hide/show that whole group. Use **+ beside an item** to show its components; components initially start collapsed. Typing a new live-estimate search reveals matching items. Collapse all still minimizes categories while that search is active.
5. Change the estimate name, Category, Qty or lighting Supply cost / unit directly on the line. Category suggestions show full names and allow pointer or keyboard selection. Custom categories are still allowed. Names and category text wrap to show long values. These changes save to the project without creating catalogue records.
6. Use **Copy item** for an independent copy immediately below the source. Drag the **⠿ grip** beside its title to reorder items **within the same scope**. To move between scopes, change Category. The order is saved and is used by Excel.
7. Expanded components have their own **+ copy** and **⠿ drag** controls. Copies appear immediately below the original; components can be moved within their own item. Copies preserve the displayed rates, sizes, units and factors. Copying or moving a component does not change its source catalogue item.
8. **Edit item / components** opens the full editor, including work type, assembly size, component descriptions, units, sizes, factors and prices. The editor also supports component copy and drag controls. Assembly and component sizes are shown in bold on the website. Component size has its own visible editor column; exported component descriptions use regular text and a separate Size / specification column.

The main Qty field is the single visible estimate quantity. Historical parenthetical take-off lengths/quantities are removed from presentation titles and from the text inserted into search when an item is selected. Useful specifications such as IP ratings and millimetre sizes are retained. This title cleanup does not rename raw catalogue records automatically. Catalogue Explorer searches by title; source codes, component descriptions and historical aliases do not determine catalogue title matches.

### Lighting supply and installation

Lighting and Emergency & Exit Lighting use the same pricing rules. The designated parent component (otherwise the first component) is the fitting supply allowance. Enter the supplier's price for **one fitting** in **Supply cost / unit**, before project mark-ups. The main Qty scales supply and installation together. Previously saved independent supply quantities are preserved until a quantity is edited, so an upgrade does not silently change a quotation.

**Supplier prices are saved with the project, not written back to the reusable catalogue.** They must be stored in the project database so reopening, project copies, backups and tender revisions retain the quotation. Editing the main supply field never creates a new catalogue item. Saving a new catalogue item from the estimate, or choosing to update its existing catalogue record, writes zero fitting supply prices into the reusable record while retaining the actual supplier prices in the project. Installation materials and labour are reusable. Other saved estimates keep their own snapshots.

The live estimate shows **Supply / unit** and **Install material / unit** separately. These calculated amounts include the project material mark-up. The first is the fitting supply allowance; the second is the remaining material build-up. Labour is shown separately. In categories without a separate fitting allowance, the material build-up appears under installation materials. The scope summary separates lighting supply cost from installation cost, with all labour included in installation.

Copying a fitting component preserves its current price and marks it as another fitting supply allowance, so it stays in the supply subtotal after reordering. The main supply-price field controls the original designated fitting; copied fitting prices can be edited in the component editor. When that build-up is saved to the catalogue from an estimate, all of these fitting supply prices are excluded. Existing imported catalogue prices are not erased as part of upgrading the database.

### Choose where an edit is saved

| Choice in the estimate editor | Result |
| --- | --- |
| **Save this estimate only** — default for an existing item | Saves the edited name, size, components, quantity and prices to this project. The original catalogue item and other estimates are unchanged. |
| **Update existing catalog item** | Updates the same catalogue ID for future use and saves the edit to this estimate. No new version is created. Fitting supply prices stay in the project. |
| **Save as a new catalog item** | Creates a separate reusable item and updates/adds the estimate line. Lighting fitting supply prices are zero in the catalogue and retained in the estimate. |

A completely new manual item created while estimating is saved for future use automatically. If a catalogue source has since been deleted, its saved estimate can still be edited; choose a new catalogue item only when you want to make it reusable again. Work types include Assembly, Supply only, Installation only, Supply & installation, Relocation, Demolition, and Relocation and Demolition. Work-type controls remain in the full editor. Supply-only excludes labour; installation-only excludes material in this editor, so choose Assembly or Supply & installation if you need materials and labour in the build-up.

### Copy a project

Use **Copy** on a project card or **Copy project** above its estimate, then enter the new project name. The copy retains the scope of work, client, currency, project rates, estimate quantities, fitting supply prices, item order and component snapshots. Every copied item/component receives a new ID so subsequent edits are independent.

The new project starts as **Not started**, with a new owner/creator and activity history. Set its new deadline in Manage project. User-created copies share automatically with the creator's current team and enter the admin's newly-added review queue. Admin-created copies can be assigned to teams through Manage project. Old assignments, submission/completion records, shared notes and tender revisions are not copied. A completed project from another team may be copied when you have permission to view it; that does not grant permission to edit the original.

### Rates and summaries
Rates and mark-ups are visible above the estimate. Material mark-up affects material; labour rate affects hourly labour; final mark-up applies to direct cost. Save project settings to apply edits. Fixed labour prices stay independent of the hourly rate.

The summary switches between By scope and By work type. Scope totals include separate lighting supply and installation lines. Work-type totals group complete estimate lines according to their saved classification. These are two views of the same estimate, not additional costs to add together. Parent scope rows and their child breakdowns likewise must not be added together twice.

### Catalogue editing and deletion
Catalogue Explorer contains saved details, versions, sources and pricing history. Users and administrators can create, import and edit catalogue items. Every saved item, including imported records, has **Edit catalog** to update that exact record in place. Select the exact record before editing or deleting it. Estimate search results also include **Delete**, so an incorrect catalogue item can be removed without leaving the estimate page.

**Delete catalog item** asks for confirmation and permanently deletes that selected catalogue record and its catalogue-owned components, source links, aliases and price history. It does not delete other saved versions. Existing estimates keep their snapshot descriptions, components and prices; their link to the deleted catalogue item is cleared. Saved tender revisions remain snapshots. Another equivalent saved version may still appear in search. Re-importing its original workbook can recreate a deleted item. Restore a database backup if you need to undo a deletion; restoring affects the whole database, including later changes.

### Imports and price history
Upload supported Excel layouts through Imports. Preview new items, changed prices, duplicates and parsing messages; choose what to import. Confirming an import creates a backup first. Unsupported layouts cannot be treated as successful imports. Source filenames, relevant quantities and pricing data are stored in the database. Low/high budget ranges are kept as distinct labelled options rather than averaged into an invented rate. Enter supplier and quote-date information where available for price history.

### Notes, collaboration and revisions
Add Note stores shared notes with the author's name. A small unread indicator is tracked separately for each user and clears when that user opens the notes. Members with the applicable project access can remove obsolete notes.

Presence information shows active project users. Revision numbers on project/line writes detect stale edits and ask for a refresh instead of silently overwriting another person's changes. The activity log records contributors. This is shared estimating, not simultaneous character-by-character document editing.

Save tender revisions such as Original, Revision 1 or Final Submission to preserve a quotation snapshot. Compare revisions and export their Excel files. The revision creator or an administrator can delete a revision. Deleting a revision does not delete the current working estimate.

### Excel export
The workbook has COST ESTIMATE and CONNECTED COST DETAIL sheets. The first shows project assumptions, scope totals and a separate Work Type Cost Summary. The detail sheet contains parent assemblies and their component build-ups. Pale gold input cells can be edited. Parent quantities drive component quantities; unit prices, project mark-ups and labour rate feed connected formulas. Parent categories feed the scope summary, and column O work types feed the work-type summary. Excel recalculates when opened in a compatible spreadsheet application. Parent Material / unit cells show separate, formula-linked Supply and Install values on two lines, while component material cells remain numeric inputs. These parent display cells are not extra amounts to add to the total. Assembly sizes are included in parent titles, and component specifications are bold. Reordered items and components export in their saved order. Zero quantities produce zero totals without division errors.

The exported workbook is an independent file: edits made in Excel do not automatically sync back into the website. Keep revisions in the app when you want to preserve a submitted quotation there.

## 3. Pricing techniques, explained

- **Assembly normalization:** source component quantities are divided by the source assembly quantity to create per-unit component ratios. Adding an assembly scales those ratios by the estimate quantity.
- **Material:** quantity × component material rate × material factor × (1 + material mark-up). A direct fitting supply-price override uses the entered supplier unit price with factor 1, before project mark-ups.
- **Hourly labour:** quantity × unit hours × labour factor × project hourly rate.
- **Fixed labour:** quantity × fixed labour price × labour factor. This is a monetary allowance, not hours, and is unaffected by hourly-rate changes.
- **Quoted cost:** (material + labour) × (1 + final mark-up).
- **Independent snapshots:** adding a catalogue item copies its components into the project. Later catalogue editing/deletion cannot rewrite those saved component prices. Tender revisions preserve another snapshot as JSON.
- **Duplicate grouping:** assembly-level size plus normalized identity and component allowance comparisons group equivalent catalogue results. Different dimensions, units, work types or allowances can remain separate. Grouping is not the same as deleting source records.
- **Classification:** scope describes the electrical service (Lighting, Power, etc.); work type describes the operation (Installation, Relocation, etc.). Both summaries reconcile to the same estimate.
- **Connected workbook:** cell references, SUM/IF formulas, category helper rows and conditional formatting connect detail rows to summaries. Work-type dropdown validation guides edits. No source Excel template is needed at runtime.

## 4. Technology and architecture

| Technology | Purpose and why it is used |
| --- | --- |
| Python 3 | Runs the server and application logic locally. Most facilities come from Python's standard library. |
| ThreadingHTTPServer / HTTP handlers | Serves browser assets and JSON API requests, with separate request threads. No Flask or Django installation is required. |
| SQLite / Python sqlite3 | The main `.db` stores catalogue, accounts and projects. A separate `lighting_prices.db` stores supplier quote records and their connections. No separate database server is required. |
| SQLite WAL | Write-ahead logging lets readers continue while writes are committed. Foreign keys preserve relationships; a busy timeout handles brief contention. |
| Write lock and transactions | Serialize application writes in one process; each transaction commits its related changes together. |
| HTML and CSS | Define the screens, forms, responsive layout, tables, dialogs, focus states and visual styling. |
| Plain JavaScript | Updates browser views, fetches API data and handles editing/search. No React, npm build or front-end compilation is required. |
| Fetch / JSON | Browser requests and responses communicate structured application data to the Python server. |
| openpyxl | Reads supported `.xlsx` inputs and writes formatted formula-based exports. It does not run Microsoft Excel. |
| pdfplumber | Extracts text and table rows from supported TLE supplier quotation PDFs. Its required PDF-processing dependencies are installed by pip. It does not perform OCR. |
| SVG | The lightweight TEC initials mark used by the website and browser tab. It is a placeholder mark, not a separately supplied official logo. |
| Optional Gemini API | Can interpret/rerank title-matched candidates when configured. Local searching remains available without it. |
| Python venv / pip | Launchers isolate Python dependencies in `.venv` and install `requirements.txt`. |
| Git ignore rules | Keep local databases, credentials, generated files and environment folders out of routine source-control commits. GitHub hosting/synchronization is not built into the app. |

### Authentication and safe writes
Passwords are salted scrypt hashes, not readable passwords and not reversible encrypted passwords. Session tokens are random; only token hashes are stored in the database. Browser cookies use HttpOnly and SameSite, and authenticated writes check a CSRF token plus request/origin rules. Permissions are checked again inside the write connection to account for role changes or session revocation.

Sessions have no routine server expiry and survive closing the browser. The cookie is renewed during authenticated use; browsers impose their own retention limits. Sign-out, account deactivation, password changes, database restore or clearing cookies can end access. Persistent sign-in means users should sign out on shared devices. The database itself is **not encrypted**: project data and saved configuration are readable to someone who can access that file. Password hashing does not encrypt other database contents.

### Performance and update handling
Search uses bounded shared read caching. Database generation triggers invalidate cached catalogue results after catalogue changes. The browser debounces typing to avoid one request per keystroke and checks request versions so stale search responses do not replace newer results. Display values are escaped to prevent item text being treated as page markup. SQLite foreign-key cascades remove dependent catalogue records on deletion; SET NULL preserves project references safely.

The release checks include 20 simultaneous authenticated clients and stale-write detection. This is a test scenario, not a guarantee for every host or workload. Keep one server process running and monitor large imports on the host.

### Backups and migrations
Main-database daily backups are scheduled by the running server; there is no external scheduler when it is stopped. Imports and restores create protective backups. SQLite's backup API captures a consistent committed database, including WAL changes. Restore validates integrity and relationships and signs users out. Migrations inspect schema/one-time markers so restarts do not repeatedly reset accounts. The application keeps legacy tables/code needed for compatible databases even when an old screen has been removed.

### Profile, defaults and dark mode in v1.20

- The floating quoted total is larger and now includes total labour **hours** and **crew working days**. Days use the current project's crew size and hours/person/day. This is a labour planning equivalent, not a calendar completion date.
- Category quoted totals and up/down controls align on the right; category names and counts stay on the left. Small screens can wrap long headings.
- App settings has a balanced six-field grid including **Default hours / person / day** and **Default crew size**. Saving these defaults affects newly created projects only. Existing projects and project copies retain their own saved crew plan. Hours must be greater than zero and at most 24; crew size is a whole number from 1 to 5,000.
- My profile uses the same full width as Teams overview. **Email** is optional and editable; leave it blank to remove it. It is stored with the account, but does not change username-based login, send email, or provide password reset. Password & security is a distinct section with current/new/confirmation fields. Existing current-password checks remain in place for username/password changes.
- Click the TEC logo to return Home. Browser link behaviour is retained.
- Use **Dark mode / Light mode** above the sidebar navigation. The navy-and-teal dark palette covers forms, tables, search results, dialogs and profile panels. The theme follows the operating system initially, then remembers your explicit choice in that browser. Other browsers can choose independently. It does not alter exported Excel formatting or database contents.

Startup migration 16 adds an empty optional `users.email` column and missing default crew/hour settings. All original values in the uploaded database are preserved. Both bundled database files remain unchanged before startup; the main file is your newly supplied snapshot. If you make further local changes after uploading, retain your newer local database when upgrading.

### Estimate and Excel refinements in v1.19

- **Show / Hide** beside each password input reveals only what you are currently typing. Submitting the form hides it again. Saved passwords remain one-way hashes and cannot be retrieved as readable passwords.
- Every category heading includes its full **quoted total**, including project mark-ups. Filtering the live estimate does not reduce that total. A small **Quoted total** button appears at the top right after the main total scrolls off screen; clicking it returns to the main total.
- **Expand all** opens every category. **Collapse all** minimizes every category to its heading and total. Individual item component expansion is preserved independently. Each category still has its own +/− control.
- Project settings include **Crew size** (whole people, default 2) and **Hours / person / day** (default 8). Crew hours/day = crew size × hours/person/day. Person-days = total labour hours ÷ hours/person/day. Crew working days = total labour hours ÷ crew hours/day. Days are fractional planning equivalents, with no weekends, holidays or calendar scheduling. Fixed-price labour with no recorded hours does not add hours or days. Changing the crew plan does not change material or labour costs.
- Excel COST ESTIMATE uses those same project values in its labour/crew panel. Connected formulas update crew hours/day and working days when edited in Excel.
- CONNECTED COST DETAIL now has a separate **Size / specification** column C for parent items and components. Component description cells use regular font. Their existing source descriptions are preserved; sizes previously appended by the exporter are no longer appended there. Editable quantities, prices, category/work-type summaries and cell connections remain available.
- The component editor exposes **Size / specification** beside Description. Material/labour factors and notes remain under the expandable details. The compact live estimate rows still omit the inline size field.

Schema version 15 adds `projects.crew_size` and `projects.hours_per_day` without replacing existing project values. Project copies and new tender revisions retain the crew settings. Older revisions that lack these fields use the default 2-person, 8-hour plan when exported. The shipped main database remains the original snapshot; migrations run on startup.

### Light price check in v1.19

Open **Light price check** directly below Imports in the sidebar. Use the Supplier dropdown to filter connected groups containing that supplier, together with your search text. Supplier and Cat No are separate detail columns. The visible Add supplier prices panel is at the bottom of the page. Type any combination of supplier, description, catalogue number or project name; matching is case-insensitive, every search word must occur in the connected group's searchable data, and suggestions refresh without pressing Enter. Quote reference is searchable too. Results show 40 groups per page, with Previous/Next controls. Open a result to see the quantities, unit and line prices of all linked parts and freight, plus source quote, project, date and PDF page. Results support browser Back/Forward, refresh and opening in a new tab.

All displayed prices are **AUD excluding GST**. The internal Type field connects rows but is not shown in the website. Connections are local to each quote:

1. A non-empty Type starts a group or joins an existing group with the same type, including when it reappears later.
2. A blank Type joins the preceding type. Leading untyped rows have their own standalone group.
3. Where a separate Type cell is blank but the description contains a marker such as `Type PD01`, that marker supplies the type. This connects fittings and globes that the PDF places on different rows.
4. The first row of a group provides its primary quantity. The connected unit price is **sum of linked line totals ÷ primary quantity**. It is not the sum of the component unit rates. For example, one chandelier at $100 plus twelve globes at $5 gives $160 per chandelier. A zero or missing primary quantity has no calculated connected unit price. Missing component prices mark a group incomplete; its known line sum is explicitly a partial total.
5. Standalone commercial notes and unpriced note-only rows are excluded. Priced freight is retained even when its catalogue number says NOTE. Included zero-price equipment is retained. Original source-row metadata, including raw types and available GST/ETA values, remains in the separate database for traceability; commercial notes are not displayed as price results.

The supplied database contains **40 quotes, 880 connected groups and 1,359 priced/included rows** from the provided workbook. The two sample PDFs already exist in those records and are skipped as duplicates. All original imported line totals are retained. Quote `740-100213-CE` has a source header total of $362,930.94 while its individual lines sum to $362,930.93; the importer preserves the one-cent discrepancy rather than inventing a balancing item.

Use **Add supplier prices** to upload the connected `.xlsx` workbook format or a text-based TLE quote `.pdf` matching the samples. Workbook import reads the **All Items** sheet once, not the repeated project-specific tabs. Optional Project Index totals are kept for reference. PDF parsing recognises the 12-column item table and quote metadata across repeated pages. Scanned PDFs, other supplier layouts and arbitrary spreadsheets are not supported by this importer; it reports an error instead of guessing. Uploads are limited to 30 MB and PDFs to 100 pages.

Identical quote reference/date/content is skipped even when the same quote is uploaded once as XLSX and once as PDF. Changed content is retained as another quotation record rather than overwriting previous prices. Import parses first, then writes the whole batch transactionally under a write lock. Before an import adds records to an existing database, a consistent backup is saved in `data/lighting_backups`.

**Light prices remain separate from the main catalogue and projects.** Importing a supplier quote does not change any estimate. Review a connected price, then enter the required price in the estimate's Supply cost / unit field. The Help assistant can retrieve up to four supplier groups and provide links to check them. With AI enabled, those selected supplier facts are sent to the configured provider along with the question; without AI, matching prices and links are still available through the built-in guide.

**Backup both databases.** App settings, daily backups, restore and `BACKUP_DATABASE.bat` cover `conest_catalog.db` only. Stop the server before copying `lighting_prices.db`; its download button has been removed from the price screen. Restoring the main database does not restore or overwrite supplier prices. To restore supplier prices, stop the server, keep the current file as a backup and replace `data/lighting_prices.db` with your selected supplier backup before restarting. The optional `CONEST_LIGHT_PRICES_DB` environment variable changes its location; otherwise it is beside the active main database, including when `CONEST_DB_PATH` is configured.

### Compact estimating, category order and help in v1.18

The inline Size / specification field has been removed from live estimate rows. Size is still available in **Edit item / components** and in the catalogue editor. Category sits beside the title; supplier price, component count and Edit/Copy actions form a compact lower row. Long titles and categories wrap. Controls highlight on hover and keyboard focus; animation is disabled when your device prefers reduced motion. The guide above the table explains direct edits, expansion and dragging.

To move a whole category, drag its dotted handle onto another category (or one of its rows). Drop on the upper half to place it before the target, or on the lower half to place it after. A teal line indicates the drop position. Alternatively use the category **↑ / ↓** buttons; these also work by keyboard or touch. Its items move together, retaining their internal order and prices. Category collapse remains separate. Your saved order appears in the scope summary, Excel and project copies. Existing projects retain their usual scope order until you move a category. New categories are appended after your ordered categories. Renaming an item’s Category still moves that item into the named group.

The database upgrade adds `projects.scope_order` (a JSON array of category names) and advances schema version to 14 on startup. The reorder API validates a complete list of category names and item IDs, uses the existing project revision check, and records the action in project activity. The calculation sorts by saved category order, then by the usual scope order for new categories and the saved item order. No catalogue records or prices are modified by category moves. The bundled database is unchanged from v1.17_Fixed; migration happens when the app starts. Keep your current `data/conest_catalog.db` if you have made newer local edits.

**Help chat:** the Help button at the lower left opens a read-only assistant. Choose a suggested question or type your own, then press Ask. It explains the app, finds selected catalogue matches, and can discuss the project currently open on Estimate. Use the source links to check records. Each question is answered independently; repeat an item name for a follow-up. The chat is temporary and clears on sign-out. It does not create, edit or delete records.

Admins enable AI and configure/test the existing Gemini key in App settings. Help uses that same provider/model and honours the AI-enabled setting. The server sends the question, built-in guide, catalogue count, up to five selected catalogue matches, up to four supplier-price groups from the separate database and, if applicable, the authorised current project's totals and up to thirty selected estimate items. It never sends account/password tables or the full database. The key stays on the server. The dialog explains this data sharing before a question is sent. Answers show whether they used AI or the built-in fallback; no key, a disabled setting, provider errors or a busy AI service fall back to local guidance. Source matches are a limited selection, not an exhaustive count of matching items. Check rates in the linked record before relying on an answer.

`conest_app/help_chat.py` prepares permission-checked data using fixed read-only queries, releases the read transaction before calling Gemini, and limits concurrent AI calls to three. There is no AI-generated SQL or action execution. Questions are limited to 1,000 characters. Provider errors return a generic fallback rather than credentials or raw request details. `assets/help_chat.js` displays all answers as plain text, allows only local catalogue/project/supplier-price source URLs, and ignores pending replies after an account change. This release tests provider success/failure using mocked responses; a live Gemini response requires a working configured key and network access on your server.

### Navigation and small fixes in v1.17_Fixed

Each page now has an address such as `/#/home`, `/#/calendar`, `/#/estimate/7` or `/#/catalog/42`. Back and Forward follow the pages you visited; refreshing restores the current page and selected project or catalogue item. The examples use sample IDs: copy the actual address from your browser. Sidebar links, project Open estimate links and catalogue item links can be right-clicked to open in a new tab, or Ctrl-clicked (Cmd-clicked on macOS). Each tab has its own page selection; normal project permissions and concurrent-edit protections still apply.

The part after `#` is processed by `assets/navigation.js`, so the Python server needs no additional page routes. Native anchors provide normal browser behaviour; `history.pushState` records programmatic navigation, and `hashchange` restores browser navigation. Request counters prevent an older project or catalogue response from replacing a newer selection. Invalid or unavailable selections return to their safe page; login and account setup still apply. Unsaved field changes, open dialogs and temporary search filters are not saved by the address—save an edit before refreshing.

In v1.17_Fixed, every live estimate row had a **Size / specification** field (removed from the row in v1.18; use Edit item / components instead). Enter or clear its value, then leave the field to save. This changes only that estimate snapshot and is included in its Excel export. Use the full catalogue editor to change the reusable catalogue size. Existing prices, names, catalogue sizes and other estimates remain independent. Size accepts up to 250 characters and uses the existing revision checks to detect conflicting edits.

Estimate-search **Delete** is now a bordered button alongside **Edit & add**; confirmation and preservation of existing estimates remain in place. Scope headings are left-aligned, with a larger 38-pixel collapse button and clearer item count. All previous features remain available.

### Copying, ordering and new fields in v1.17

The database schema moves from version 12 to 13. `catalog_items.assembly_size` stores an optional item size and `project_lines.size_snapshot` captures it when added. `catalog_components.is_supply_copy` and `project_line_components.is_supply_copy` identify copied fitting supply rows. Existing records receive empty sizes and a zero flag, preserving their previous meaning. Initialization checks for each column so repeating the upgrade is safe.

Copy actions insert new IDs while copying independent snapshots. Component ordering temporarily vacates the old order numbers before assigning new ones, keeping SQLite's unique line-order constraint valid. Reorder requests must contain every current ID exactly once; missing, repeated, foreign and stale IDs are rejected. Project and line revision checks, authentication, CSRF checks and live team permissions also apply to the new actions. Activity records identify the person who copied or reordered an estimate.

The interface uses native HTML drag-and-drop events, delegated button/input events and a small in-memory state for expanded scopes and the live filter. Desktop mouse dragging is the supported drag interaction. Reordering is saved only through the checked server APIs. Sizes and user-provided text are HTML-escaped. Plain JavaScript, CSS and the existing Python/openpyxl stack are retained; no Node build step is required. That release added no runtime dependency; v1.19 adds pdfplumber for supplier PDFs.

### Configuration options

| Setting | Meaning |
| --- | --- |
| `--host` / `CONEST_HOST` | Listening address; default `0.0.0.0` accepts local-network connections. |
| `--port` / `CONEST_PORT` | Listening port; default `8080`. |
| `--no-browser` | Starts the server without automatically opening a browser. |
| `CONEST_DB_PATH` | Optional alternate SQLite database path; otherwise uses `data/conest_catalog.db`. |
| `CONEST_COOKIE_SECURE=1` | Adds the Secure cookie flag for an HTTPS deployment. Do not set this for ordinary local HTTP access. |
| `CONEST_LLM_ENABLED` | Overrides whether optional model assistance is enabled. |
| `CONEST_LLM_MODEL` | Optional model choice; an explicitly supplied setting/override may take precedence. |
| `GEMINI_API_KEY` | Optional key from the environment; a saved app key takes precedence. |

These are operating-system environment variables or command-line arguments. The package does not depend on a `.env` loader. Configure ordinary project prices through the website, not environment variables.

### What happens when you save an estimate field
The browser sends a PATCH request with the changed value, session cookie, CSRF token and expected record revision. The handler verifies sign-in and project access, then rechecks those permissions under the write lock. The project module validates the value, updates the snapshot and increments its revision. An attributed activity entry is recorded through the route, the transaction commits, and the recalculated project is returned for rendering. A conflicting stale revision is rejected rather than silently replacing a newer edit.

## 5. Every file in this ZIP

There are 50 runtime files. Directory paths below are relative to the extracted application folder. No source workbooks, test suites or development audit reports are required in the delivery ZIP.

| File | Responsibility |
| --- | --- |
| `README.md` | This usage, architecture, maintenance and release guide. |
| `app.py` | Server entry point, main API routes, request/error handling, import/export integration and server lifecycle. |
| `requirements.txt` | Supported openpyxl and pdfplumber dependency ranges for installation. |
| `START_TEC_SERVER.bat` | Windows environment setup and server launcher; displays local/team access details. |
| `BACKUP_DATABASE.bat` | Windows entry point for the standalone database backup utility. |
| `run.sh` | Linux/macOS virtual-environment setup and server launcher. |
| `.gitignore` | Rules excluding local/private/generated files from normal Git tracking; it does not prevent the app reading those files locally. |
| `data/conest_catalog.db` | Bundled SQLite snapshot: catalogue, components, accounts, teams, projects, settings and related application records. Replace with your latest backup when upgrading. |
| `data/lighting_prices.db` | Separate supplier-price database: quotes, connected groups, priced/included lines and internal source metadata. Preserve this file on future upgrades too. |
| `assets/estimate_extras.js` | Password visibility, crew-day displays, the floating estimate total and bulk component expansion/collapse. |
| `assets/light_prices.js` | Supplier search, paginated quote cards, connected component details and file uploads. |
| `conest_app/light_prices.py` | Separate database schema, workbook/PDF parsing, internal type connections, quantity-aware linked prices, duplicate detection and pre-import backups. |
| `tools/backup_database.py` | Creates a consistent database copy in the top-level `backups` folder. |
| `assets/theme.js` | Applies system or saved light/dark preference before painting the page; handles the accessible sidebar toggle and browser-local persistence. |
| `assets/theme.css` | Navy dark surfaces, teal accents, readable controls, tables, dialogs, status colours and focus states. Static CSS overrides; no runtime dependency. |
| `assets/index.html` | Main page, navigation, forms, tables and dialogs. |
| `assets/help_chat.js` | Help dialog, questions, plain-text replies, local source links and session-safe response handling. |
| `conest_app/help_chat.py` | Built-in guidance, bounded catalogue/project retrieval, project access checks, optional Gemini answers and local fallback. |
| `assets/navigation.js` | Hash-based page addresses, deep-link startup, browser history and stale-navigation protection. Native links support opening pages/projects/catalogue items in a new tab. |
| `assets/estimate_workspace.js` | Scope collapse, live-estimate search, navigation, copy/project-copy actions and drag event handling. Loaded after the main UI scripts. |
| `assets/app.js` | Estimator, catalogue, manual item editor, settings, search and import interactions. |
| `assets/styles.css` | Base appearance, estimating layout, responsive rules and component styles. |
| `assets/workspace.js` | Login, board, profile, teams, user/project administration, activity, notes and calendar interactions. |
| `assets/workspace.css` | Workspace, management, profile and board styling. |
| `assets/productivity.js` | Revisions, price history, backup controls, import preview, presence and reminders. |
| `assets/tec-mark.svg` | TEC initials branding and favicon asset. |
| `conest_app/__init__.py` | Python package identity/version. |
| `conest_app/accounts.py` | Password hashing/verification, sessions, account validation, sign-in throttling and public user records. |
| `conest_app/assistant.py` | Quantity/query interpretation and optional Gemini integration with local fallback. |
| `conest_app/backups.py` | In-app backup listing, creation, validation, restoration and daily-backup logic. |
| `conest_app/catalog.py` | Catalogue queries, details, duplicate presentation, manual creation/editing and selected-version deletion. |
| `conest_app/component_master.py` | Parser for recognized component-pricing master workbook layouts. |
| `conest_app/database.py` | SQLite paths/connections, schema creation/migration, settings, write lock and catalogue index refresh. |
| `conest_app/estimate_tools.py` | Transactional project/item/component copying and order validation, preserving independent snapshots and checking revisions. |
| `conest_app/estimate_options.py` | Display-title cleanup, lighting fitting identification, estimate supply/size fields, fitting-copy flags and persistent-session migration. |
| `conest_app/exporter.py` | Styled, connected two-sheet Excel estimate generation and export naming. |
| `conest_app/http_productivity.py` | API routing for revisions, presence, backups, pricing history and import preview. |
| `conest_app/http_workspace.py` | Authentication/CSRF checks, request permission checks and workspace API routes. |
| `conest_app/import_preview.py` | Temporary parsed previews, duplicate/price comparison and importing selected preview rows. |
| `conest_app/importer.py` | Core workbook layout detection, parsing, normalization and catalogue/source insertion. |
| `conest_app/initial_roster.py` | Initial testing roster definitions and precomputed password hashes; supports initial account provisioning. |
| `conest_app/productivity.py` | Revision snapshots/comparison, price-history records, presence and deadline data; includes legacy check support retained for compatibility. |
| `conest_app/project_notes.py` | Shared note storage and per-user unread/read state. |
| `conest_app/projects.py` | Project and estimate-line operations, snapshots, cost calculations, scope/work summaries and line options. |
| `conest_app/range_importer.py` | Recognized low/high budget workbook parser; preserves both pricing alternatives. |
| `conest_app/read_cache.py` | Bounded thread-safe catalogue read cache and generation triggers. |
| `conest_app/taxonomy.py` | Scope and work-type definitions, normalization, quality/specification and grouping helpers. |
| `conest_app/teams.py` | Team membership/management and team-aware project sharing support. |
| `conest_app/utils.py` | Text cleanup, safe filenames, timestamps, hashing and numeric helpers. |
| `conest_app/workspace.py` | Project access, activity, statuses, optimistic revision checks and board visibility. |

### Files and folders created while running

- `.venv`: installed Python environment; recreated by the launcher if needed.
- `__pycache__`: Python bytecode cache; safe to regenerate.
- `data/conest_catalog.db-wal` and `-shm`: live SQLite transaction/coordination files. Do not delete them while the server is running or copy only the main `.db` during active writes. Use the backup function.
- `data/lighting_backups`: consistent supplier database snapshots taken before imports that add records; duplicate-only imports do not create another backup. These are separate from main-database backups.
- `data/backups`: in-app main-database backups and metadata; retain according to your recovery needs.
- `backups`: copies made by the standalone backup script.
- `data/import_previews`: temporary preview data; preview tokens expire after 24 hours.
- Uploaded/exported files may be created during imports/exports. Their content is separate from the bundled runtime files. Keep original supplier workbooks separately if needed for future reference.

## 6. Release history and current changes

Earlier milestones are summarized from the supplied project history; intermediate versions are grouped where that history does not establish an exact version-to-feature mapping.

| Release / milestone | Changes |
| --- | --- |
| v1.3 | Manual supply, installation, relocation and demolition pricing; hourly/fixed labour; editable units/components and reusable catalogue versions. |
| v1.4 | Project deletion, floating search, duplicate result grouping, live scope breakdown, Data.xlsx assemblies and connected Excel calculations. |
| v1.5 | TEC ConEst branding, saved API-key Show/Hide, aligned project/export controls, separate connected-detail Excel tab and simplified summaries. |
| v1.6 | Duplicate matching ignoring codes, removal of visible Code/Phase fields, wrapping category editor and refreshed website/Excel presentation. A repaired ZIP was also supplied. |
| Team/productivity releases through v1.12 | Login and roles, user/team administration, shared projects, board/status review, profile teams, calendar, shared notes/unread indicators, contribution activity, tender revisions/deletion, backup/restore, import preview, price history, presence and deadlines. Extra board filters and submission-check controls were subsequently removed; management alignment and horizontal team presentation were refined. |
| v1.13 | Removed historical Quality Control panel; slim runtime ZIP without already-imported Excel copies; existing testing accounts directly active while future accounts retain setup. |
| v1.14 | Collapsed estimate details, estimate-only fitting supply price/quantity, lighting supply/installation summary, cleaned display titles, live title-only catalogue search and persistent sessions. |
| v1.15 | Linked lighting quantities, switchable work-type summary, combined Relocation and Demolition type, Excel work-type summary, cancel-search behavior and expanded rates controls. |
| **v1.20** | Uses the newly uploaded database; enlarges the floating total with hours/days, aligns scope totals/actions, adds new-project crew defaults, full-width profile with optional email and a password section, TEC home link, and persistent light/dark themes. |
| **v1.19_Fixed** | Bulk controls now minimize/expand categories; adds a supplier filter, separate Supplier/Cat No detail columns, a clearer bottom upload panel, removes the database download button, and moves Light price check below Imports. Both database files are unchanged. |
| **v1.19** | Adds password Show/Hide; separate Excel/editor size columns and regular component descriptions; floating quoted total and category totals; configurable crew/day planning; Expand all / Collapse all; separate supplier-price search/database with connected XLSX/PDF imports, duplicate detection, backup download and Help integration. |
| **v1.18** | Removes inline size from estimate rows; compacts title/category/supply controls; adds draggable whole categories and up/down controls with persistent Excel/copy order; adds optional read-only Help chat using the existing Gemini setting with a built-in fallback. |
| **v1.17_Fixed** | Adds page/project/catalogue addresses, Back/Forward and refresh restoration, native new-tab links, inline estimate size editing, matching Delete buttons and larger left-aligned scope headings. No database migration or bundled data changes. |
| **v1.17** | Uses the latest uploaded database. Adds main-search navigation and bottom navigation; in-place edits for imported and manual catalogue items; deletion from estimate search; estimate-only save mode; project-specific fitting prices; split material rates; scope collapse; zero quantities; search within estimates; clean selected titles; assembly size; item/component copying and dragging; project copying; compact controls and this updated guide. |
| **v1.16** | Removes inline work-type selector and duplicate supply quantity. Keeps plain Supply cost / unit without a yellow box. Initially moved classification to Item options; this fixed release removes the extra control. Refines visual hierarchy, rates panel, buttons and row spacing. Adds authenticated selected-version catalogue deletion while preserving estimate snapshots. Expands this guide to explain all delivered files, technology, techniques and release milestones. |

Features remain available even when controls move. The v1.17 migration preserves the uploaded catalogue dataset, existing accounts and saved estimate totals.

## 7. Troubleshooting and maintenance

- **Cannot connect from another computer:** verify the host is running, both machines can reach the same network, the IP/port are correct, and the private-network firewall allows Python. `127.0.0.1` always means the computer currently using that address.
- **Port 8080 is in use:** stop the other server or inspect `python app.py --help` for supported launch options. Do not run multiple processes against the same working database as a scaling shortcut.
- **Changes appear missing after upgrade:** stop and check that your current database backup replaced the bundled snapshot before first launch. Do not overwrite your old working folder.
- **Deleted item still appears:** another version may have equivalent data. Check the source/version details before deleting anything else.
- **Search result is out of date:** refresh the page after another user's catalogue changes; catalogue reads are invalidated on database changes, but an already-open detail panel is not a live subscription.
- **Excel totals do not display immediately:** open with automatic calculation enabled in a compatible spreadsheet program. openpyxl writes formulas; it is not a calculation engine.
- **Forgotten password:** ask an administrator to use the user-management workflow. Do not edit password hashes manually.
- **Python/dependency error:** confirm Python is installed and initial dependency installation can reach the package service. Launch from the supplied script rather than double-clicking a Python module.
- **Before significant imports or maintenance:** retain a known-good backup. Database restoration replaces current data, so coordinate it with the team.

Tests are kept in the development workspace, not shipped as runtime requirements. They cover pricing, imports, permissions, snapshots, sessions, search cancellation, workbook formula structure, concurrent requests and deletion preservation. Visual layout should also be reviewed on your actual browser/window sizes. No claim is made that every browser or Excel implementation behaves identically.

### v1.16_Fixed — minor interface fixes
- Equal-width columns in the desktop Rates and mark-ups panel.
- Removed the extra Item options button/dialog. Work type remains in the component editor.
- Category suggestions appear while focusing/typing in the wrapping category field. Choose an existing category or type a custom one.
- No database or calculation changes.

### v1.16_Fixed2 — category suggestion correction
Corrected an inherited expand-button width/height rule that cramped category choices. Suggestions show full wrapping names in a scrollable list with all categories available. Typing places matching categories first. Pointer selection saves before focus can leave the editor; keyboard activation remains supported. No database or pricing changes.
