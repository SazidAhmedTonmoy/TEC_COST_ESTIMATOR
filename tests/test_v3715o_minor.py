"""Minor v3.7.15o changes must not disrupt opportunity decisions or calendar controls."""
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]

class MinorUiPatchTests(TestCase):
    def test_review_action_only_in_details_not_on_opportunity_cards(self):
        ui = (ROOT / "tenders_frontend/src/components/opportunities.tsx").read_text()
        cards = ui.split('className="op-cards"', 1)[1].split('<Sheet open={!!selectedId}', 1)[0]
        details = ui.split('<Sheet open={!!selectedId}', 1)[1]
        self.assertNotIn('Move to In Review', cards)
        self.assertNotIn('op-review-action', cards)
        self.assertIn("setDecision('review')", details)
        self.assertIn('>In Review</button>', details)
        self.assertIn("decision==='review'?'Move to In Review'", ui)

    def test_event_type_filter_in_agenda_toolbar_not_overlapping_panel(self):
        app = (ROOT / "tenders_frontend/src/components/tender-app.tsx").read_text()
        start = app.index("{view==='calendar'&&calendarMode==='chase'")
        end = app.index("{view==='reminders'&&", start)
        chase = app[start:end]
        self.assertTrue(chase.startswith("{view==='calendar'&&calendarMode==='chase'&&<div className=\"chase-calendar-layout\">"))
        self.assertEqual(chase.count('className="calendar-event-filter"'), 1)
        self.assertNotIn('className="calendar-agenda-filter"', chase)
        self.assertLess(chase.index('className="calendar-event-filter"'), chase.index("{chaseCalendarLayout==='month'&&<>"))
        self.assertLess(chase.index('className="calendar-event-filter"'), chase.index('className="panel opportunity-rolling-agenda"'))
        self.assertIn('</section>}</div>}', chase)
        self.assertIn('Next 7 days', chase)
        self.assertIn('Next 30 days', chase)

    def test_spacing_and_mobile_controls_present(self):
        style = (ROOT / "tenders_frontend/src/tender-v35.css").read_text()
        for selector in (
            '.chase-calendar-layout>.filter-row',
            '.chase-calendar-layout>.calendar-display-switch',
            '.chase-calendar-layout .calendar-event-filter',
            '.chase-calendar-layout .opportunity-rolling-agenda',
            '@media(max-width:767px)',
        ):
            self.assertIn(selector, style)
        self.assertNotIn('.calendar-agenda-filter{', style)
