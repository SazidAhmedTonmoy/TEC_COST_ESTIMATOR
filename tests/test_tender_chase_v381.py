"""v3.8.1 chase-up workflow: first-Wednesday, recurrence, closure and permissions."""
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from conest_app import tenders
from conest_app.database import connect


class Chase381Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.env = patch.dict(os.environ, {
            'CONEST_DB_PATH': str(root / 'catalog.db'),
            'CONEST_TENDERS_DB_PATH': str(root / 'tenders.db'),
        })
        self.env.start()
        self.clock = patch('conest_app.tenders.sydney_today',return_value=date(2026,11,18))
        self.clock.start()
        with connect() as db:
            self.admin = dict(db.execute("SELECT id,name,role FROM users WHERE role='admin' LIMIT 1").fetchone())
        self.store = tenders.Store(root / 'tenders.db')

    def tearDown(self):
        self.store.close()
        self.clock.stop()
        self.env.stop()
        self.folder.cleanup()

    def add(self, project='381 Project', builder='381 Builder', submitted=None, status='Open', builder_status='In Progress'):
        payload = {'project':project, 'builder':builder, 'value':1000,
                   'status':status,'builderStatus':builder_status,'region':'NSW',
                   'due':'2026-11-05','_actor_id':self.admin['id'],'author':self.admin['name']}
        if submitted is not None:payload['submittedDate']=submitted
        result=self.store.save_submission(payload)
        return self.store.delta(result['id'])['submission']

    def test_first_wednesday_is_strictly_after_fourteen_full_days(self):
        self.assertEqual(tenders.first_chase_wednesday('2026-11-04'),'2026-11-25T09:00')
        self.assertEqual(tenders.first_chase_wednesday('2026-11-01'),'2026-11-18T09:00')
        self.assertEqual(tenders.first_chase_wednesday('2026-11-18'),'2026-12-09T09:00')

    def test_auto_first_chase_already_has_14_day_continuity(self):
        s=self.add(submitted='2026-11-04')
        reminders=self.store.delta(s['id'])['reminders']
        self.assertEqual(len(reminders),1)
        self.assertTrue(reminders[0]['automatic'])
        self.assertTrue(reminders[0]['repeatEvery14Days'])
        self.assertEqual(reminders[0]['due'],'2026-11-25T09:00')
        self.assertEqual(reminders[0]['firstDue'],'2026-11-25T09:00')
        self.assertEqual(reminders[0]['createdBy'],self.admin['id'])
        # Daily sweep advances one interval even if nobody clicks "Done".
        self.store.ensure_followups(force=True,today=date(2026,11,26))
        self.assertEqual(self.store.delta(s['id'])['reminders'][0]['due'],'2026-12-09T09:00')
        self.store.ensure_followups(force=True,today=date(2026,12,11))
        self.assertEqual(self.store.delta(s['id'])['reminders'][0]['due'],'2026-12-23T09:00')

    def test_recently_submitted_has_no_schedule_until_day_fourteen(self):
        s=self.add(submitted='2026-11-08')
        self.assertEqual(self.store.delta(s['id'])['reminders'],[])
        self.store.ensure_followups(force=True,today=date(2026,11,21))
        self.assertEqual(self.store.delta(s['id'])['reminders'],[])
        self.store.ensure_followups(force=True,today=date(2026,11,22))
        upcoming=self.store.delta(s['id'])['reminders']
        self.assertEqual(len(upcoming),1)
        self.assertEqual(upcoming[0]['due'],'2026-11-25T09:00')
        self.assertTrue(upcoming[0]['repeatEvery14Days'])

    def test_deadline_and_created_timestamp_are_not_assumed_submission(self):
        s=self.add(submitted=None)
        self.assertTrue(s['due'])
        self.assertTrue(s['createdAt'])
        self.store.ensure_followups(force=True,today=date(2026,12,20))
        self.assertEqual(self.store.delta(s['id'])['reminders'],[])

    def test_closed_on_unsuccessful_and_other_builders_are_independent(self):
        first=self.add(project='Same project',builder='Contractor A',submitted='2026-11-03')
        second=self.add(project='Same project',builder='Contractor B',submitted='2026-11-03')
        self.assertEqual(len(self.store.delta(first['id'])['reminders']),1)
        first=self.store.delta(first['id'])['submission']
        self.store.save_submission({**first,'builderStatus':'Unsuccessful',
                                     '_actor_id':self.admin['id'],'author':self.admin['name']})
        updated=self.store.delta(first['id'])
        self.assertEqual(updated['submission']['status'],'Close')
        self.assertTrue(all(r['done'] and r['cancelled'] for r in updated['reminders']))
        self.assertEqual(self.store.delta(second['id'])['submission']['status'],'Open')
        self.assertEqual(len([r for r in self.store.delta(second['id'])['reminders'] if not r['done']]),1)
        with self.assertRaises(tenders.ValidationError):
            self.store.save_reminder({'submissionId':first['id'],'due':'2026-12-02T09:00'})
        with self.assertRaises(tenders.ValidationError):
            self.store.add_chase({'submissionId':first['id'],'note':'Do not chase', 'date':'2026-11-18'})

    def test_unsuccessful_cannot_be_manually_reopened_without_changing_outcome(self):
        s=self.add(builder_status='Unsuccessful')
        self.assertEqual(s['status'],'Close')
        result=self.store.save_submission({**s,'status':'Open',
                                           '_actor_id':self.admin['id'],'author':self.admin['name']})
        self.assertEqual(self.store.delta(result['id'])['submission']['status'],'Close')

    def test_lost_cancels_and_blocks_new_schedules(self):
        s=self.add(submitted='2026-11-04')
        self.assertEqual(len(self.store.delta(s['id'])['reminders']),1)
        self.store.save_submission({**s,'status':'Lost',
                                    '_actor_id':self.admin['id'],'author':self.admin['name']})
        records=self.store.delta(s['id'])['reminders']
        self.assertTrue(all(r['cancelled'] for r in records))
        with self.assertRaises(tenders.ValidationError):
            self.store.save_reminder({'submissionId':s['id'],'due':'2026-12-01T09:00'})

    def test_manual_recurring_updates_on_completion(self):
        s=self.add()
        self.store.save_reminder({'submissionId':s['id'],'due':'2026-11-18T09:00',
                                  'repeatEvery14Days':True,'note':'Follow up',
                                  '_actor_id':self.admin['id'],'author':self.admin['name']})
        self.store.ensure_followups(force=True,today=date(2026,11,19))
        record=self.store.delta(s['id'])['reminders'][0]
        self.assertEqual(record['due'],'2026-12-02T09:00')
        self.store.save_reminder({'id':record['id'],'done':True,
                                  '_actor_id':self.admin['id'],'author':self.admin['name']})
        upcoming=self.store.delta(s['id'])['reminders'][0]
        self.assertEqual(upcoming['due'],'2026-12-16T09:00')
        self.assertFalse(upcoming['done'])
        self.assertEqual(upcoming['completedCount'],1)

    def test_manual_followup_replaces_automatic_schedule(self):
        s=self.add(submitted='2026-11-03')
        automatic=self.store.delta(s['id'])['reminders'][0]
        self.store.save_reminder({'submissionId':s['id'],'due':'2026-11-30T15:00',
                                  'note':'Chosen followup','repeatEvery14Days':False,
                                  '_actor_id':self.admin['id'],'author':self.admin['name']})
        schedules=self.store.delta(s['id'])['reminders']
        self.assertEqual(len([r for r in schedules if not r['done']]),1)
        self.assertTrue(next(r for r in schedules if r['id']==automatic['id'])['cancelled'])

    def test_author_or_admin_may_delete_schedule_but_others_cannot(self):
        s=self.add(submitted='2026-11-01')
        automatic=self.store.delta(s['id'])['reminders'][0]
        with self.assertRaises(tenders.ValidationError) as err:
            self.store.delete_reminder({'id':automatic['id'],'revision':0},
                                        {'id':self.admin['id']+1000,'name':'Other','role':'user'})
        self.assertEqual(err.exception.status,403)
        with self.assertRaises(tenders.ValidationError) as err:
            self.store.delete_reminder({'id':automatic['id'],'revision':999},self.admin)
        self.assertEqual(err.exception.status,409)
        self.store.delete_reminder({'id':automatic['id'],'revision':0},
                                    {'id':self.admin['id'],'name':self.admin['name'],'role':'user'})
        self.store.ensure_followups(force=True,today=date(2026,11,19))
        self.assertEqual(self.store.delta(s['id'])['reminders'],[])
        self.assertTrue(self.store.delta(s['id'])['submission']['autoFirstChaseCancelled'])
        self.store.save_reminder({'submissionId':s['id'],'due':'2026-12-02T09:00',
                                  '_actor_id':self.admin['id']+99,'author':'Other author'})
        reminder=self.store.delta(s['id'])['reminders'][0]
        self.store.delete_reminder({'id':reminder['id'],'revision':0},self.admin)
        self.assertEqual(self.store.delta(s['id'])['reminders'],[])

    def test_existing_live_seed_without_dates_does_not_generate_new_schedules(self):
        self.store.ensure_followups(force=True,today=date(2026,11,18))
        with self.store.connect() as db:
            legacy=db.execute("SELECT COUNT(*) FROM submissions WHERE json_extract(body, '$.submittedDate') IS NULL").fetchone()[0]
            self.assertGreater(legacy,100)
            auto=db.execute("SELECT COUNT(*) FROM reminders WHERE json_extract(body, '$.automatic')=1").fetchone()[0]
            self.assertEqual(auto,0)


if __name__=='__main__':unittest.main()
