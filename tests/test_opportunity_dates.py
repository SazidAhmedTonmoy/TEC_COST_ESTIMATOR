"""v3.7.21 opportunity date-source and all-time reconciliation regressions."""
import json
from datetime import date
from unittest.mock import patch

from conest_app import opportunities as op, tenders
from conest_app.opportunity_analytics import summary
from test_opportunities import OpportunityTests


class DateReconciliationTests(OpportunityTests):
    def test_uploaded_vs_original_added_date_and_calendar_boundary(self):
        # A historic Added date must not silently become the workbook upload
        # date, and a source calendar date must not be timezone-shifted.
        with patch.object(tenders, 'timestamp', return_value='2026-11-07T12:00:00Z'):
            self.create(project='September item uploaded in November', addedDate='2026-09-30')
            self.create(project='Manual November creation with no Added date')
        november = summary(self.store, {'mode': 'month', 'month': '2026-11'}, self.admin)
        november_uploaded = summary(self.store, {
            'mode': 'month', 'month': '2026-11', 'dateBasis': 'uploaded'}, self.admin)
        september = summary(self.store, {
            'mode': 'month', 'month': '2026-09', 'dateBasis': 'added'}, self.admin)
        self.assertEqual(november['outcomes']['added'], 1)
        self.assertEqual(november_uploaded['outcomes']['added'], 2)
        self.assertEqual(november_uploaded['activeTotal'], 2)
        self.assertEqual(november_uploaded['outsidePeriod'], 0)
        self.assertEqual(november['outsidePeriod'], 1)
        self.assertEqual(september['outcomes']['added'], 1)
        # The old action-time counters stay based on upload/creation time.
        self.assertEqual(november['counts']['added'], 2)
        self.assertEqual(september['counts']['added'], 0)

    def test_all_time_matches_register_counts_and_quote_breakdown(self):
        with patch.object(tenders, 'timestamp', return_value='2026-11-07T12:00:00Z'):
            to_quote = self.create(project='Already quoted', addedDate='2025-04-12')
            awaiting_quote = self.create(project='Approved not quoted')
            rejected = self.create(project='Rejected')
            pending = self.create(project='Pending')
            expired = self.create(project='Expired', due='2025-01-01')
        with patch.object(tenders, 'timestamp', return_value='2026-11-08T12:00:00Z'):
            quoted_approval = op.decide(self.store, {
                'id': to_quote['id'], 'revision': to_quote['revision'],
                'decision': 'approved'}, self.member)['opportunity']
            op.decide(self.store, {'id': awaiting_quote['id'],
                                  'revision': awaiting_quote['revision'],
                                  'decision': 'approved'}, self.member)
            op.decide(self.store, {'id': rejected['id'],
                                  'revision': rejected['revision'],
                                  'decision': 'rejected'}, self.member)
            op.quote(self.store, {'id': quoted_approval['id'],
                                  'revision': quoted_approval['revision'],
                                  'value': 4500, 'note': '', 'quoteNo': 'R1',
                                  'submittedDate': '2026-11-08',
                                  'submittedByTeamId': self.team,
                                  'builders': ['Builder One']}, self.member)
        register = op.list_opportunities(self.store, {}, self.admin)
        all_time = summary(self.store, {'mode': 'all'}, self.admin, now=date(2026, 11, 10))
        outcomes = all_time['outcomes']
        self.assertEqual(outcomes['added'], register['counts']['all'])
        for key in ('pending', 'review', 'approved', 'rejected', 'expired'):
            self.assertEqual(outcomes[key], register['counts'][key], key)
        self.assertEqual(outcomes['approvedQuoted'], register['quoteCounts']['quoted'])
        self.assertEqual(outcomes['approvedNotQuoted'], register['quoteCounts']['needsQuote'])
        self.assertEqual(outcomes['added'], sum(outcomes[key] for key in
            ('approved', 'rejected', 'expired', 'pending', 'review')))
        self.assertEqual(outcomes['approved'], outcomes['approvedQuoted'] + outcomes['approvedNotQuoted'])
        self.assertEqual(sum(row['added'] for row in all_time['creators']), outcomes['added'])
        self.assertEqual(all_time['from'], None)
        self.assertEqual(all_time['to'], None)

    def test_migrated_and_missing_creation_dates_do_not_disappear_all_time(self):
        with patch.object(tenders, 'timestamp', return_value='2026-10-31T23:40:00Z'):
            historical = self.create(project='Migrated audit-backed opportunity')
            without_dates = self.create(project='Legacy with no known dates')
        with self.store.connect() as db:
            for item in (historical, without_dates):
                body = json.loads(db.execute('SELECT body FROM opportunities WHERE id=?',
                                             (item['id'],)).fetchone()['body'])
                body.pop('createdAt', None)
                db.execute('UPDATE opportunities SET body=? WHERE id=?',
                           (json.dumps(body), item['id']))
            db.execute('DELETE FROM opportunity_activity WHERE opportunity_id=?',
                       (without_dates['id'],))
        november = summary(self.store, {'mode': 'month', 'month': '2026-11'}, self.admin)
        self.assertEqual(november['outcomes']['added'], 1)
        self.assertEqual(november['missingDates'], 1)
        all_time = summary(self.store, {'mode': 'all'}, self.admin)
        self.assertEqual(all_time['outcomes']['added'], 2)
        self.assertEqual(sum(r['added'] for r in all_time['monthlyOutcomes']), 2)

    def test_reject_invalid_date_basis(self):
        with self.assertRaises(tenders.ValidationError):
            summary(self.store, {'mode': 'month', 'month': '2026-11',
                                 'dateBasis': 'deadline'}, self.admin)
