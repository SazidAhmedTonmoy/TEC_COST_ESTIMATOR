"""Searchable instructions for the TEC Flow workspaces."""

from . import __version__

# Each stage pairs the instruction with the values a new user should recognise.
WALKTHROUGHS = {
    'first-estimate': [
        ('Find the fitting', 'From the Estimate page, enter “12 x downlight” in Search by item title and select Find. Check the Qty field shows 12, then review a matching fitting and its components.', [('Search', '12 x downlight'), ('Quantity', '12')]),
        ('Add the quantity', 'Add the reviewed fitting to this estimate. Give it the drawing reference D1 and check that the estimate line shows twelve fittings.', [('Reference', 'D1'), ('Estimate quantity', '12')]),
        ('Allocate by floor', 'In Breakdown, choose Active and add Ground floor and Level 1. Choose Multiple areas for D1. Enter eight on Ground floor and four on Level 1.', [('Ground floor', '8'), ('Level 1', '4'), ('Remaining', '0')]),
        ('Review and export', 'Return to the estimate and check D1 still totals twelve. Review the included price, save a revision and choose Export Excel. Check that the workbook includes both floor allocations.', [('D1 total', '12'), ('Ground floor + Level 1', '8 + 4')]),
    ],
    'first-follow-up': [
        ('Find the submission', 'In Tenders, open Project Chase-up. Search for the project, then open the row for the builder you actually quoted. A project can have several builder submissions.', [('Project', 'Example office fitout'), ('Builder', 'Example Construction'), ('TEC status', 'Open')]),
        ('Record the conversation', 'After speaking to the builder, add a chase-up entry with the contact, date and what they said. Save and check the newest history entry.', [('Contact', 'Alex'), ('Chase-up note', 'Pricing under review. Call next Wednesday.')]),
        ('Schedule the next call', 'Schedule a follow-up for the agreed date and time. Select the 14-day repeat option only if a fortnightly call was agreed. Open Calendar and select the date to check the entry.', [('Next contact', 'Wednesday, 10 am Sydney'), ('Repeat every 14 days', 'Off')]),
        ('Update the outcome', 'When the builder confirms they won the main contract, record their outcome as Awarded. Keep TEC status Open while the electrical subcontract is undecided. Find the project in Open-Awarded.', [('Builder outcome', 'Awarded'), ('TEC status', 'Open'), ('Register', 'Open-Awarded')]),
    ],
}

SECTIONS = [
    ('start', 'Getting started', [
        ('first-estimate', 'Build your first estimate', [
            step[1] for step in WALKTHROUGHS['first-estimate']
        ], 'Start with an editable estimate. If this tender already has a linked estimate, open that project before adding fittings.'),
        ('first-follow-up', 'Follow up your first quotation', [
            step[1] for step in WALKTHROUGHS['first-follow-up']
        ], 'Start with a submitted quotation. A chase-up records a conversation. A scheduled follow-up puts the next call on your calendar.'),
        ('first-login', 'Sign in and choose a homepage', [
            'Sign in using your assigned account. If prompted, change the temporary password first.',
            'Choose Estimator or Tenders from the workspace switcher. Both use the same account.',
            'Open My Profile to choose your own preferred homepage; Auto follows your role/team default.',
        ], 'Your administrator manages accounts, team access and permissions.'),
        ('navigation', 'Find your way around', [
            'Use the sidebar to open the features in your current workspace.',
            'Use the Estimator / Tenders switcher to change workspace without signing out.',
            'Use search in the relevant register to find a project by name, builder or reference.',
            'Open Help and search for a task such as “allocate quantities” or “builder contacts”.',
        ], 'Opening a project should not force you to recreate a search or filter.'),
        ('account', 'My Profile, photo and security', [
            'Click your profile in the sidebar and edit your name, contact details and job title.',
            'Upload a profile photo or select initials. Choose My homepage.',
            'Enter the current password when changing your username or password, then save.',
        ], 'A password change signs out other sessions.'),
    ]),
    ('estimator', 'Estimator workspace', [
        ('estimate-home', 'Estimator Home and Project Board', [
            'Use Home for project status, assigned activity, deadlines and the Project Board.',
            'Search all accessible projects with the top search box, regardless of selected month or status.',
            'Open an estimate from its project card; use Details & actions for additional project operations.',
            'Administrators can review team activity with selectable week or month.',
        ], 'Closed estimates are not counted as submitted/completed estimates.'),
        ('new-project', 'Create and set up an estimate', [
            'Select New Project. Enter the project name, builders, team and submission deadline.',
            'Open the project, then set labour rate, working hours/day, crew size and mark-ups.',
            'Use Manage project & activity to update its brief, team assignments and workflow.',
        ], 'Changes to costing settings affect project calculations; check totals before exporting.'),
        ('project-progress', 'Project progress and deadlines', [
            'Use the Progress dropdown beside Estimate Setup guide.',
            'Choose Not started, In progress, In review, Submitted or Closed as appropriate.',
            'In review requires a review deadline. Submitted represents an estimate that has been submitted.',
        ], 'Closed may mean discarded work; it is not automatically a completed estimate.'),
        ('catalog-search', 'Add catalog items to an estimate', [
            'Search the reusable Catalog from the Estimate page.',
            'Inspect the item, specification, materials and labour build-up before adding it.',
            'Use Add to estimate, set the project quantity and adjust any project-only reference or price.',
        ], 'Changes to a project snapshot do not automatically change the master Catalog.'),
        ('estimate-lines', 'Edit estimate items and components', [
            'Expand the relevant category to show its estimate items.',
            'Edit quantity, reference, item description, remarks and project-only supply price as needed.',
            'Use Edit item to inspect component quantities, material prices and labour hours.',
            'Drag the dotted handle to reorder items or categories; use Expand All / Shrink All.',
        ], 'Fixed-quantity components do not scale with the parent quantity.'),
        ('estimate-colours', 'Yellow and red item highlights', [
            'Click the highlight marker beside an item once for yellow, twice for red, then again to clear.',
            'Highlights are stored with the estimate and can be viewed by other authorized users.',
            'Read-only viewers can see markers but cannot change them.',
        ], 'Highlight colours do not affect the estimated price.'),
        ('estimate-totals', 'Materials, labour and quoted total', [
            'Check project material mark-up, labour rate, labour-hour mark-up and final mark-up.',
            'Review material totals, labour hours, labour cost and included quoted total.',
            'Optional categories are excluded from the included quoted total.',
            'Use the crew plan for approximate person-days and working-days calculations.',
        ], 'The application estimates costs; verify supplier quotes and project-specific assumptions.'),
        ('breakdown', 'Activate and use Breakdown', [
            'Open Breakdown from an estimate and choose Active. It stays active until an editor switches it off.',
            'Add Area / Floor / Space names and choose Allocation or Structured View.',
            'Find items with Breakdown search by name, reference, remarks, category or area.',
            'Changes autosave. Use Undo / Redo if a distribution is incorrect.',
        ], 'When inactive, Breakdown sections are omitted from Excel and public share views.'),
        ('allocation', 'Allocate quantities to areas', [
            'Select Single area for an item assigned entirely to one area.',
            'Select Multiple areas to divide quantity between several spaces; enter quantities or distribute equally.',
            'Use a common-to-all-areas option only for items intended as a shared allowance.',
            'Check Remaining and the unallocated-only filter before finishing.',
        ], 'The breakdown divides the existing estimate quantity; it must not increase project totals.'),
        ('revisions', 'Save, view and compare revisions', [
            'Open Revisions in an estimate and save a snapshot at an appropriate milestone.',
            'Use View to inspect a saved snapshot without changing the live estimate.',
            'Use Compare to see differences against another revision or the working estimate.',
            'Restore a revision only when you intend to replace the working state.',
        ], 'Check the revision date, label and totals before restoring.'),
        ('notes-activity', 'Notes, contributors and activity', [
            'Use Add Note to record assumptions, clarifications and decisions.',
            'Use Manage project & activity to inspect the project journey, permissions and history.',
            'Read activity and revisions before changing an estimate another colleague is editing.',
        ], 'Edits and notes are attributed to the signed-in account.'),
        ('estimate-export', 'Export Excel and share an estimate', [
            'Review included and optional totals, references, remarks and active Breakdown allocations.',
            'Choose Export Excel to generate the estimate workbook.',
            'Use Share to generate a read-only project view according to its sharing settings.',
        ], 'Sharing or exporting does not give the recipient permission to edit the project.'),
    ]),
    ('catalog', 'Catalog, Light Price and imports', [
        ('catalog-library', 'Catalog Explorer', [
            'Open Catalog and search item titles, codes, components or categories.',
            'Inspect component material price, hours and installation type in the details panel.',
            'Add to estimate for a project snapshot, Edit catalog item for the reusable record, or Save as new version when appropriate.',
            'Use Source history to trace imported sheets and workbook occurrences.',
        ], 'Catalog prices may be historical; confirm current supplier pricing.'),
        ('light-price', 'Light Price library', [
            'Open Light Price and search by supplier, catalogue number, description, project or nickname.',
            'Inspect individual components, included/excluded items and connected unit cost.',
            'Use supplier quotations as pricing references, not automatically current offers.',
        ], 'Quoted supplier prices are generally AUD excluding GST.'),
        ('import-catalog', 'Import an estimating workbook', [
            'Open Import and select the workbook upload/preview tools.',
            'Check the detected sheet structure and warnings before committing an import.',
            'Review the import summary and source history afterward.',
        ], 'Avoid importing a live database file as a workbook.'),
        ('supplier-quotes', 'Import supplier lighting prices', [
            'Open Import → Add supplier prices.',
            'Check the quotation, review detected fittings and component pricing, then import selected records.',
            'Inspect changed or duplicate quotes before approving an update.',
        ], 'Scanned PDF quotations may need a text-readable copy or OCR before extraction.'),
    ]),
    ('tenders', 'Tender workspace', [
        ('tender-dashboard', 'Tender dashboard and pipeline', [
            'Use Dashboard for total projects, live submission pipeline, builder outcomes, pricing feedback and follow-ups.',
            'Open Project Chase-up for detailed filters and the complete submission register.',
            'Select a chart segment to view related submissions.',
        ], 'TEC Won and Builder Awarded are different outcomes.'),
        ('new-tender', 'Create and edit a tender', [
            'Select New tender, complete project, builder, deadline, region and quotation details.',
            'Save the submission and open it to add chase-up history or modify outcomes.',
            'Use editing menus rather than Delete for routine corrections.',
        ], 'Keep tender status, builder result and pricing feedback distinct.'),
        ('tender-filters', 'Multi-select filters, search and saved context', [
            'Open the Filters panel in Project Chase-up, Projects or Builders.',
            'Tick multiple options in Region, TEC status, Team, Builder outcome and other fields.',
            'Values within one field use OR; different fields combine using AND.',
            'Clear a field or use Clear filters to start over.',
        ], 'Filters should stay in place when opening a tender and returning to the register.'),
        ('contact-import', 'Import builder contacts from a screenshot', [
            'Open a new opportunity or edit an existing one. Under Builders, select Import screenshot.',
            'Paste a cropped contact list, drag the image into the paste area or select a file. If recognition is unavailable, use Paste or correct recognized text and Detect from text.',
            'Compare the proposed rows with your source. Check that each person sits under the right builder and that wrapped phone numbers and email addresses are complete.',
            'Select Add reviewed builders & contacts. Check the list in the opportunity form, then save the opportunity.',
        ], 'Adding the reviewed rows fills the form. Saving the opportunity commits them.'),
        ('builder-contacts', 'Shared builder contacts', [
            'Opportunities, Tender/Chase-up and Open-Awarded use one shared builder contact directory.',
            'Add contact person supports multiple people, each with up to 12 phone numbers and 12 email addresses. Contacts are optional and can be added later.',
            'Use a saved contact or type an existing full name, email or phone number and leave the field to autofill a unique match. Choose explicitly if more than one person matches.',
            'Tender and Open-Awarded share the same quotation contacts. The explicitly linked Opportunity keeps the same selected people for that builder.',
            'Editing a saved person updates that person wherever used. Removing a person from a project keeps them in the builder directory.',
            'In Builders, open a builder to see, add or edit all its contacts. Download all contacts exports the whole directory to Excel.',
            'All administrators and members assigned to that builder’s Opportunities or Estimator projects, including individual assignees, can select Delete and confirm removal from all current selections. Audit history remains available.',
        ], 'An unrelated project keeps its own selected people. Save the form to apply changes.'),
        ('open-awarded', 'Open-Awarded: awarded builder projects', [
            'Open Tenders → Open-Awarded. This view includes builder submissions where TEC status is Open and Builder outcome is Awarded; it is available to signed-in users.',
            'Use Cards to see the project and builder, submitted amount, awarded date, estimated start date, latest chase-up, project URL and awarded-project contacts. Dated awards sort newest first; missing dates sort last.',
            'Select Edit or Add contact. Record the actual award/start dates, optional manual project URL, and add up to 20 contact people; each person can have multiple phone numbers and email addresses.',
            'Use Add contact person, Add phone and Add email; confirm with Save details. These contacts are shared with Tender/Chase-up and the explicitly linked Opportunity.',
            'Choose Calendar for amber Awarded events and teal Estimated Start events. Today is marked in blue using the Sydney date. Select an event to see contact details in a panel below the calendar.',
            'Click a phone number to open your dialler or an email to open Outlook web compose. Use View project to open full Tender Details and chase-up history.',
            'If a Tender is linked to an Opportunity, its current project URL is displayed automatically; manually entered URLs override it. Unmatched or ambiguous records are not guessed.',
        ], 'Missing dates and contacts are displayed as missing, never inferred. Calendar events show only recorded dates; updates are checked against your access and the current record revision.'),
        ('chase-up', 'Project Chase-up and follow-up history', [
            'Open Project Chase-up and find a submission by project or builder.',
            'Record contacts, follow-up notes, dates and any promised next action.',
            'Schedule the next chase-up and review reminders when due.',
            'New recorded chase-ups appear in the notification bell. Missing receipts for the last 30 days of authenticated chase-ups are recovered automatically. Search by user name, project or message, or select Chase-ups; View chase-up opens its history.',
        ], 'Chase-up history retains its author; do not overwrite a colleague’s record to add a new contact.'),
        ('builders-projects', 'Projects and Builders registers', [
            'Use Projects for grouped project totals across builders.',
            'Every Project Chase-up sort keeps the same project’s builder submissions together; pagination keeps each project on one page.',
            'Use Builders to compare builders’ submissions, wins, values and contact counts. Open a builder to see all available contacts, or add/edit a person.',
            'Select Download all contacts to export the complete builder contact directory to Excel, including phone numbers and email addresses.',
            'Open a group to examine its connected quotations.',
        ], 'Project value may use the highest builder quote; builder submissions remain separate.'),
        ('tender-calendar', 'Calendar, deadlines and reminders', [
            'Open Calendar for upcoming submission deadlines, follow-ups and approved opportunities.',
            'Switch Month / Agenda where available and move to the required date.',
            'Use Reminders to review due and completed follow-ups.',
        ], 'Notifications may require browser permission; in-app reminders do not.'),
        ('tender-import', 'Import and export tender registers', [
            'Use Import Excel in Tenders to preview and merge new or changed submission rows.',
            'Check duplicate matches and merged builder records before proceeding.',
            'Use Export to download the currently selected register results.',
        ], 'Back up the live database before major imports.'),
        ('opportunities', 'Opportunities and approvals', [
            'Open Opportunities and add a project with its address, builder, deadline and scope.',
            'Choosing Closing deadline shows a nonblocking count of other projects with that date and a breakdown by assigned team names. Shared teams appear together; No team assigned means no team was selected. Deleted/retired records and the edited project are excluded; each Opportunity counts once.',
            'On a linked card, Open Linked Project opens the Estimator project, or the Tender project overview if no Estimator is linked. Open Project Chase-up remains a separate follow-up action; manage connections in View details.',
            'Under each builder, optionally add one or more contact people now or later. Choose a saved contact or enter an exact name, email or phone number to autofill matching details.',
            'Select Assign team in an unassigned card’s footer. It matches View details and uses the existing permissions and automatic approval rules. Assigned names then appear as text; change them through View details → Assign.',
            'Review incoming opportunities, assign an authorized team and approve or reject.',
            'Use Approved → Need to quote to find approved projects awaiting a quotation.',
        ], 'Opportunity approval is separate from submitting an electrical quotation.'),
        ('estimate-handoff', 'Create an estimate from an approved opportunity', [
            'Open an Approved opportunity and go to Project Journey → Estimator project.',
            'Choose Create Estimate if your assigned team has Estimator access, or link an existing estimate.',
            'Check the copied project brief, builder, deadline and team before pricing.',
        ], 'This operation is permission-checked and prevents duplicate links.'),
        ('quoted-outcomes', 'Record quotations and outcomes', [
            'In an Approved opportunity, choose Quoted or Not quoted as appropriate.',
            'Connect a quoted opportunity to the corresponding Tender project or Chase-up record.',
            'Update the builder’s actual award outcome separately from TEC’s quote result.',
        ], 'Do not treat builder award status as proof TEC won the work.'),
        ('analytics', 'Opportunity analytics', [
            'Open Opportunities → Analytics to view created, approved, pending quotation, rejected and expired counts.',
            'Select month, month-by-month, custom dates or All time.',
            'Use Original added date versus Upload/creation date when reconciling imported Excel opportunities.',
        ], 'All signed-in active users can view Analytics; counts use the selected date source.'),
    ]),
    ('admin', 'Teams, administration and safety', [
        ('users-teams', 'Accounts, teams and editing access', [
            'Administrators open Manage Users to add users, manage roles and team memberships.',
            'One account may belong to multiple teams. Team assignment controls access to relevant estimate editing.',
            'Each team can have its own default homepage and Estimator usage setting.',
        ], 'Do not share admin credentials. Viewer access and edit access are different.'),
        ('app-settings', 'Application defaults and backups', [
            'Administrators open App Settings to set the default currency, labour rate, mark-ups and crew size.',
            'Choose Save defaults. Open a new estimate and check its costing settings before adding items.',
            'Use database backup/restore controls carefully; restoring a backup replaces newer data.',
        ], 'Your application has separate Estimator and Tender SQLite databases; protect both.'),
        ('save-recovery', 'Saving, retry and recovery', [
            'Watch Saved / Saving / Unsaved status in Estimator and Breakdown.',
            'If a write fails, do not repeat it blindly: first verify whether the server saved the change.',
            'Use revisions, Undo/Redo or authorized backup recovery for mistakes.',
        ], 'When your connection is interrupted, keep the page open until you have verified the saved state.'),
    ]),
]


def guide_payload():
    return {'version': __version__, 'sections': [
        {'id': group, 'title': label, 'articles': [
            {'id': slug, 'title': title, 'steps': steps, 'note': note, 'walkthrough': WALKTHROUGHS.get(slug, [])}
            for slug, title, steps, note in articles
        ]} for group, label, articles in SECTIONS]}
