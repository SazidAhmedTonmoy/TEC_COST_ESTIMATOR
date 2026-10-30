"""v3.7.15 usability changes: server-side quick filters and UX source contracts."""
from datetime import datetime, timedelta
from pathlib import Path
from unittest import TestCase
from zoneinfo import ZoneInfo
from conest_app import opportunities as op, tenders
from tests.test_opportunities import OpportunityTests

ROOT = Path(__file__).resolve().parents[1]


class Usability3715Tests(TestCase):
    setUp = OpportunityTests.setUp
    tearDown = OpportunityTests.tearDown
    create = OpportunityTests.create
    make_user = staticmethod(OpportunityTests.make_user)

    def test_due_soon_filters_all_pages_and_excludes_closed(self):
        today = datetime.now(ZoneInfo('Australia/Sydney')).date()
        due = lambda n: (today + timedelta(days=n)).isoformat()
        within = self.create(project='Due in two days', due=due(2))
        last_day = self.create(project='Due on day seven', due=due(6))
        self.create(project='Outside seven-day window', due=due(8))
        closed = self.create(project='Rejected inside window', due=due(3))
        op.decide(self.store, {'id': closed['id'], 'revision': closed['revision'], 'decision': 'rejected'}, self.admin)
        names = [row['project'] for row in op.list_opportunities(self.store, {'dueSoon':'7', 'sort':'due_asc'}, self.admin)['items']]
        self.assertEqual(names, ['Due in two days', 'Due on day seven'])
        self.assertEqual(len(names), 2)
        self.assertEqual(op.list_opportunities(self.store, {'dueSoon':'7', 'pageSize':1, 'page':2}, self.admin)['total'], 2)

    def test_document_availability_filter_and_validation(self):
        yes = self.create(project='Documents ready')
        no = self.create(project='Documents missing')
        op.set_documents_available(self.store, {'id':yes['id'], 'revision':yes['revision'], 'available':True}, self.admin)
        yes_rows = op.list_opportunities(self.store, {'documentsAvailable':'yes'}, self.admin)['items']
        no_rows = op.list_opportunities(self.store, {'documentsAvailable':'no'}, self.admin)['items']
        self.assertEqual([x['id'] for x in yes_rows], [yes['id']])
        self.assertEqual([x['id'] for x in no_rows], [no['id']])
        for params in ({'documentsAvailable':'bad'},{'dueSoon':'500'}):
            with self.assertRaises(tenders.ValidationError):
                op.list_opportunities(self.store, params, self.admin)


class UiSourceContracts3715(TestCase):
    def test_opportunity_detail_order_and_quick_filters(self):
        src=(ROOT/'tenders_frontend/src/components/opportunities.tsx').read_text()
        start=src.index('<dl className="op-facts">')
        tail=src[start:src.index('{selected.remarks&&',start)]
        positions=[tail.index('<h3>'+h+'</h3>') for h in ('Builders','Assigned teams and people','Link','Working scope')]
        self.assertEqual(positions,sorted(positions))
        for name in ('Need to quote','Already quoted','Due soon','My team','Documents available'):
            self.assertIn(name,src)
        self.assertIn("params.set('dueSoon','7')",src)
        self.assertIn("params.set('documentsAvailable','yes')",src)

    def test_agenda_and_schedule_controls(self):
        calendar=(ROOT/'tenders_frontend/src/components/opportunity-calendar.tsx').read_text()
        app=(ROOT/'tenders_frontend/src/components/tender-app.tsx').read_text()
        for text in ('Next 7 days','Next 30 days','Upcoming approved deadlines','calendar-agenda-day'):
            self.assertIn(text,calendar)
        for text in ('chaseCalendarLayout','Open chase-up','Schedule next follow-up','post(\'reminders\''):
            self.assertIn(text,app)
        self.assertIn('calendar-agenda-entry', (ROOT/'tenders_frontend/src/tender-v35.css').read_text())

    def test_reminder_endpoint_records_activity(self):
        src=(ROOT/'conest_app/tenders.py').read_text()
        self.assertIn("'Updated reminder' if identifier else 'Scheduled follow-up'",src)
