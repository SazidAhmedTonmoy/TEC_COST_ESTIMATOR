# Opportunity source data for v3.5

The first application start after this update adds the missing records from the two supplied workbooks. The source rows are packaged in `seed.json`; a separate marker for each workbook prevents repeated starts from overwriting edits or restoring deleted opportunities.

| Supplied workbook | Worksheet | Actual opportunity rows | Source decisions |
| --- | --- | ---: | --- |
| Tender Opportunities NSW.xlsx | E1 | 7 | 7 awaiting a decision |
| Tender Opportunities VIC.xlsx | E1 | 47 | 1 approved, 11 not interested, 35 awaiting a decision |

Blank rows that contain only the Remaining Time formula and empty approval checkboxes are template rows and are not imported. The application calculates expiry from the closing date in the opportunity's region; it does not reuse the spreadsheet's cached Remaining Time result.

The source has no reliable approver identity or approval timestamp. The imported decisions are preserved as source information. The application's audit attributes the initial transfer to **Workbook import**, without crediting a current user for historical approval or rejection. Previously approved opportunities whose deadlines have passed appear in Expired and retain their original approved source status. Rejected opportunities remain in Rejected.

At 21 October 2026, the supplied dates produce 11 Awaiting approval records, 11 Rejected records, and 32 Expired records. These counts will change as closing dates pass or users update the opportunities.

## Preserved source meaning

- Budget values such as `5m-10m` are project budget ranges. They are preserved as text in **Budget** and are not converted into an electrical quotation value.
- Category, Added Date, Closing Date, named builders, Comments, and distance are copied from the supplied data. A separate Working Scope field starts blank because the workbooks have no dedicated scope column. Existing scope-related comments remain in Comments.
- NSW distances retain the supplied origin, **63-79 Parramatta Rd Silverwater, NSW 2128**. VIC distances retain **CBD, Melbourne**. Distances are source values; the application does not recalculate road distances.
- Original filenames, worksheet names, row numbers, populated cells, formula text, and any source hyperlinks are retained in each record's source data. The file hashes in `seed.json` identify the supplied source bytes.
- The NSW project title containing `179 Elizabeth Street, Sydney NSW 200` is preserved verbatim. The apparently incomplete postcode is not silently corrected.
- VIC row 17 says `Total 6 Builder` but names only three builders. Those three are imported, and the discrepancy is retained as a source warning.
- VIC row 30, **Office Warehouse in Tullamarine - Stage 1 Only**, has no named builder. Its builder list remains empty and a source warning records this omission.

## Later Excel imports

The Opportunities page accepts the supplied worksheet format and the application's exported Opportunities table. Preview reports new rows, existing records, changed records that will be skipped, invalid rows, and source warnings. Applying a preview adds missing projects only. Existing records, permissions, workflow decisions, and deleted records remain unchanged. Use the opportunity editor to update an existing record.

Exported Opportunity IDs provide stable matching even if a title has changed. Without an ID, matching uses the region and normalized project name. Ambiguous conflicting rows in the same workbook must be resolved before import. Files containing invalid rows are not partially applied. A new preview is required if opportunity data changes before application.

Historical decisions uploaded in a later workbook are retained as source information. They do not bypass the application's approval permissions: new records start Awaiting approval or Expired according to their closing date.
