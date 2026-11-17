"""Versioned, searchable in-product documentation for TEC EstiDoc.

Each article is ordinary application documentation, never an instruction to an LLM.
The same records supply the Help panel and grounded AI how-to context.
"""

SECTIONS = [
    ('start', 'Getting started', [
        ('first-login', 'Sign in and choose a homepage', [
            'Sign in using your assigned account. If prompted, change the temporary password first.',
            'Choose Estimator or Tenders from the workspace switcher. Both use the same account.',
            'Open My Profile to choose your own preferred homepage; Auto follows your role/team default.',
        ], 'Your administrator manages accounts, team access and permissions.'),
        ('navigation', 'Find your way around', [
            'Use the sidebar to open the features in your current workspace.',
            'Use the Estimator / Tenders switcher to change workspace without signing out.',
            'Use search in the relevant register to find a project by name, builder or reference.',
            'Use Help → User Guide for step-by-step instructions or Help → AI Assistant for a question.',
        ], 'Opening a project should not force you to recreate a search or filter.'),
        ('account', 'My Profile, photo and security', [
            'Click your profile in the sidebar and edit your name, contact details and job title.',
            'Upload a profile photo or select initials. Choose My homepage.',
            'Enter the current password when changing your username or password, then save.',
        ], 'A password change signs out other sessions. Do not share passwords with Help.'),
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
        ('chase-up', 'Project Chase-up and follow-up history', [
            'Open Project Chase-up and find a submission by project or builder.',
            'Record contacts, follow-up notes, dates and any promised next action.',
            'Schedule the next chase-up and review reminders when due.',
        ], 'Chase-up history retains its author; do not overwrite a colleague’s record to add a new contact.'),
        ('builders-projects', 'Projects and Builders registers', [
            'Use Projects for grouped project totals across builders.',
            'Use Builders to compare builders’ submissions, wins and values.',
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
        ('app-settings', 'Settings, AI configuration and backups', [
            'Administrators open App Settings to configure supported application options and Gemini access.',
            'Confirm integrations before submitting private workspace records or documents to an external AI provider.',
            'Use database backup/restore controls carefully; restoring a backup replaces newer data.',
        ], 'Your application has separate Estimator and Tender SQLite databases; protect both.'),
        ('assistant', 'AI Assistant, documents and confirmed actions', [
            'Open ? Help → AI Assistant to ask about an estimate, project, catalog item or tender.',
            'Use the attachment button to supply a text PDF, spreadsheet, DOCX or text file.',
            'Enable configured Gemini in Help Settings if you want AI-powered analysis using supplied context.',
            'For supported write tasks, such as adding a note, updating project progress, changing a deadline, recording Won/Lost or renaming a project, review the preview and select Confirm.',
        ], 'The assistant cannot arbitrarily access external systems, ignore user permissions or execute unknown operations. Actions require approval.'),
        ('save-recovery', 'Saving, retry and recovery', [
            'Watch Saved / Saving / Unsaved status in Estimator and Breakdown.',
            'If a write fails, do not repeat it blindly: first verify whether the server saved the change.',
            'Use revisions, Undo/Redo or authorized backup recovery for mistakes.',
        ], 'When your connection is interrupted, keep the page open until you have verified the saved state.'),
    ]),
]


def guide_payload():
    return {'version': '3.7.27', 'sections': [
        {'id': group, 'title': label, 'articles': [
            {'id': slug, 'title': title, 'steps': steps, 'note': note}
            for slug, title, steps, note in articles
        ]} for group, label, articles in SECTIONS]}


def guide_text(question='', max_articles=10):
    """Retrieve only relevant guide entries so prompts stay bounded."""
    import re
    words = [w for w in re.findall(r'[a-z0-9]+', question.casefold()) if len(w)>3 and w not in {'about','from','with','show','make','what','where','when','which','please','help','this','that'}]
    ranks = []
    for group, label, articles in SECTIONS:
        for slug, title, steps, note in articles:
            body = f'{title} {label} ' + ' '.join(steps) + ' ' + note
            score = sum(4 if w in title.casefold() else 2 if w in label.casefold() else 1 if w in body.casefold() else 0 for w in words)
            ranks.append((score, title, steps, note))
    ranks.sort(key=lambda x: x[0], reverse=True)
    chosen = ranks[:max_articles] if words else ranks[:5]
    return '\n\n'.join(f'{title}:\n' + '\n'.join(f'{i+1}. {step}' for i,step in enumerate(steps)) + f'\nNote: {note}' for _,title,steps,note in chosen)
