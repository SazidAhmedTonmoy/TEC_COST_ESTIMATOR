# TEC ConEst v3.5

21 October 2026. Upgrade from the latest v3.4 package.

## Home

**New Project** now sits beside **Project JSON** on Home. It opens the existing estimate creation form and uses the Estimator’s teal theme. The actions wrap on mobile.

## Opportunities in Tenders

The new **Opportunities** navigation entry tracks potential projects separately from tender submissions and estimate values.

- Add a project name, Quote No., region, closing deadline, category, budget, location, distance, working scope and notes.
- Select multiple builders. Suggestions include existing tender builders and builders added to opportunities. Case, spacing and punctuation differences are normalised to avoid accidental duplicate builder names.
- New records start **Awaiting approval**. Separate views show **Approved**, **Rejected**, **Expired** and **Deleted** records.
- Search project names, builders, Quote No., working scope, category, notes, location and region without case sensitivity.
- Filter by region, assigned team, My team or Unassigned. The team selector shows a count for each team. Regions include NSW and VIC and accept additional region labels.
- Sort by newest created, earliest deadline or latest deadline. Blank deadlines sort last. The list shows 20 records per page.
- A details panel shows the complete scope, builders, project fields and activity history. Earlier history loads in pages of 50.

The supplied opportunity workbook informed the category, budget, distance, builder and notes fields. This update does not automatically insert workbook rows into your live database or reinterpret historical approval ticks as decisions by website users.

## Permissions and decisions

| Action | Who can do it |
| --- | --- |
| View and create opportunities | Active signed-in users |
| Edit project details | Creator, admin, or explicitly authorised people/teams |
| Assign or change the responsible team | Creator or admin |
| Grant or revoke editing access | Creator or admin |
| Delete or restore | Creator or admin |
| Approve an awaiting opportunity | Active members of an existing team |
| Reject an awaiting or approved opportunity | Team members, creator or admin |

Assignment and editing access are separate: assigning a team notifies its members but does not silently allow them to edit. Use **Edit access** in the form to grant that permission.

Approval follows the requested team-membership rule. An administrator without team membership can manage the opportunity but does not bypass approval. The approving person and their team are recorded. Rejection requires a reason.

Deletion moves the record into **Deleted**, retaining its history. Restoration returns it for approval, or to Expired if its deadline has already passed. To reopen an expired opportunity, the creator/admin sets a later deadline. A rejected opportunity can be explicitly reopened for approval.

## History and notifications

Creation, edits, permission changes, assignment, decisions, deletion, restoration, upcoming deadlines and expiry are recorded with actor and timestamp. System-generated events are labelled **System**. Edits record before/after values; deleted accounts do not erase actor-name snapshots.

The opportunity notification button beside the existing reminder bell opens an inbox for assignments, decisions, updates and deadline events affecting the creator, assigned team and authorised editors. The person performing a change does not receive a redundant notification of their own action. Notifications remain until marked read.

Awaiting and approved opportunities generate an upcoming-deadline event within three days of closing. After the closing date ends in **Australia/Sydney** time, they become Expired; approval history remains visible. Rejected and deleted records do not generate deadline reminders. Undated opportunities do not expire.

These are in-app notifications, not email or browser push messages. The inbox refreshes once per minute while Tenders is visible and when returning to the tab. Cron records deadlines while nobody has the website open; opening the app also reconciles missed checks.

## Deployment and database safety

1. Use the full ZIP for a complete code update, or overlay the changed-files ZIP onto the **latest v3.4 code**. Retain your production databases, uploads, environment configuration and secrets.
2. Follow the existing deployment process and restart Passenger. Visit Tenders once after deployment. The new opportunity tables and indexes are created additively in the existing tender database. Existing records are not replaced. Estimator schema remains **31**; the application release is **3.5**.
3. The existing deployment workflow runs `tools/install_backup_cron.sh`. That installer now also schedules opportunity deadline checks every five minutes. If deploying manually, visit `/api/health`, then run `sh tools/install_backup_cron.sh` in the deployed application directory using the normal production environment. If cron installation is unavailable, the installer prints the exact entries for cPanel Cron Jobs.
4. Existing catalog and Tenders backups continue at **00:10 server time**. Opportunities, their activity history and notification state are in the tender database and are included in that backup.
5. Verify Home → New Project; Tenders → Opportunities; assignment notifications in a second account; approval by a team member; and mobile navigation.

No production database files, deployment secrets, uploaded documents or dependency folders are included in these update ZIPs. A normal code deployment does not import the opportunity workbook.

## Performance and validation

- The Opportunities page is loaded on demand. It does not add all opportunity records to the tender bootstrap response.
- Server pagination, indexed deadline/team lookups, debounced searches and cancelled stale reads limit unnecessary work.
- Opportunity updates and read receipts do not invalidate the main tender-data cache.
- Changes are transactional. Expected revisions reject stale concurrent saves; duplicate clicks are blocked while saving. Mutations are never automatically retried after uncertain network failures.
- Permissions use current account/team data and are checked on the server, with the existing authentication and CSRF protections.
- Verified desktop/mobile layouts, light/dark themes, creation, builder selection, search, region filtering, separate-session team approval, and the notification inbox.
- Backend tests cover permissions, live team membership changes, cross-session revision conflicts, simultaneous edits, pagination, audit retention, deadlines and notification idempotency, alongside the existing regression suite.

This package has not been deployed to the live website.
