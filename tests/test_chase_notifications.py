"""New chase-up receipts and full-history, per-user notification search."""
import os
from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from conest_app import opportunities as op, tenders
from conest_app.database import connect


class ChaseNotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        env = patch.dict(os.environ, {'CONEST_DB_PATH':str(root/'catalog.db'),
                                      'CONEST_TENDERS_DB_PATH':str(root/'tenders.db')})
        env.start()
        self.addCleanup(env.stop)
        with connect() as db:
            self.author = self.person(db, 'Alex Example', True)
            self.reader = self.person(db, 'Jordan Example', True)
            self.inactive = self.person(db, 'Inactive Example', False)
        self.store = tenders.Store(root/'tenders.db')
        self.addCleanup(self.store.close)
        self.submission = self.store.save_submission({
            'project':'Notification test project', 'builder':'Example builder',
            'status':'Open','builderStatus':'In Progress','region':'NSW',
            'due':'2026-11-24','value':100,'author':self.author['name'],
            '_actor_id':self.author['id']})['id']
        # Remove time-based fixture effects; these tests exercise only recorded
        # events and inbox queries, not the independently tested due sweep.
        self.real_sweep = op.process_due
        sweep = patch.object(op, 'process_due')
        sweep.start(); self.addCleanup(sweep.stop)

    def person(self, db, name, active):
        moment = tenders.timestamp()
        uid = db.execute('''INSERT INTO users(username,name,password_hash,role,is_active,
            must_change_password,created_at,updated_at) VALUES(?,?,?,'user',?,0,?,?)''',
            ('notification-test-'+name,name,'test-only-hash',int(active),moment,moment)).lastrowid
        return {'id':uid,'name':name,'role':'user'}

    def record(self, note='Requested feedback', **extra):
        return self.store.add_chase({'submissionId':self.submission,'date':'2026-11-24',
            'note':note,'method':'Email','author':self.author['name'],
            '_actor_id':self.author['id'],**extra})

    def inbox(self, person=None, **filters):
        return op.notifications(self.store, {'kind':'chases',**filters}, person or self.reader)

    def test_new_receipts_per_active_user_read_independently_and_not_replayed(self):
        self.assertEqual(self.inbox()['total'],0)
        self.record()
        result=self.inbox(q='aLeX eXaMpLe')
        self.assertEqual(result['total'],1)
        self.assertEqual(result['unreadCount'],1)
        notice=result['items'][0]
        self.assertEqual(notice['submissionId'],self.submission)
        self.assertIn('Alex Example recorded a chase-up',notice['message'])
        self.assertIn('Example builder',notice['message'])
        self.assertIn('Requested feedback',notice['message'])
        self.assertEqual(self.inbox(self.author)['total'],1)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM tender_notifications WHERE kind='chase-recorded' AND user_id=?",(self.inactive['id'],)).fetchone()[0],0)
            event = db.execute('SELECT body FROM chases WHERE submission_id=?',(self.submission,)).fetchone()
            import json
            chase=json.loads(event[0]); submission=json.loads(db.execute('SELECT body FROM submissions WHERE id=?',(self.submission,)).fetchone()[0])
        with self.store.connect(write=True) as db:
            op.notify_recorded_chase(db, submission, chase, op.directory()[1])
        self.assertEqual(self.inbox()['total'],1)
        op.mark_read(self.store,{'ids':[notice['id']]},self.reader)
        self.assertTrue(self.inbox()['items'][0]['read'])
        self.assertFalse(self.inbox(self.author)['items'][0]['read'])
        self.assertEqual(self.inbox(q='no match')['unreadCount'],0)
        # Existing history with no authenticated actor is not sent as new mail.
        self.record('Historical update',_actor_id=None)
        self.assertEqual(self.inbox()['total'],1)

    def test_search_before_paging_and_literal_sql_input(self):
        self.record('Old target note')
        with self.store.connect() as db:
            # Put more than one page of newer notices before the old one.
            db.executemany('''INSERT INTO tender_notifications
                (id,user_id,kind,target_kind,target_id,title,message,due,created_at,event_key)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',[(f'new-{i}',self.reader['id'],'chase-recorded',
                'submission',self.submission,'Another project','Jordan Example recorded a chase-up','',
                '2099-01-01T00:00:00Z',f'new-event-{i}') for i in range(35)])
        self.assertEqual(self.inbox()['total'],36)
        self.assertNotIn('Alex Example',str(self.inbox()['items']))
        self.assertEqual(self.inbox(q='Alex Example')['total'],1)
        self.assertEqual(self.inbox(q='jordan',pageSize=10,page=4)['total'],35)
        self.assertEqual(len(self.inbox(q='jordan',pageSize=10,page=4)['items']),5)
        self.assertEqual(self.inbox(q="%' OR 1=1 --")['total'],0)
        self.assertEqual(self.inbox(q='_%')['total'],0)
        self.assertEqual(self.inbox(q='Jordan',person=self.author)['total'],0)
        self.assertEqual(self.inbox(kind='opportunities',q='Alex')['total'],0)
        self.assertEqual(self.inbox(kind='reminders',q='Alex')['total'],0)
        self.assertEqual(self.inbox(q='Alex')['unreadCount'],36)
        with self.assertRaises(tenders.ValidationError): self.inbox(kind='unknown')
        with self.assertRaises(tenders.ValidationError): self.inbox(q='x'*201)

    def test_recover_recent_pre_notification_history_and_keep_read_state(self):
        # Simulate a genuine authenticated entry recorded by v3.8.10.
        with patch.object(op,'notify_recorded_chase',return_value=None):
            self.record('Recent follow-up saved before release')
            self.record('Older archived follow-up')
            self.record('Another recent follow-up')
        self.record('Workbook-style legacy row',_actor_id=None)
        now=datetime.now(timezone.utc)
        previous=(now-timedelta(days=1)).isoformat()
        older=(now-timedelta(days=31)).isoformat()
        with self.store.connect(write=True) as db:
            db.execute("UPDATE tender_activity SET created_at=? WHERE action='Recorded chase-up'",(previous,))
            db.execute("UPDATE tender_activity SET created_at=? WHERE action='Recorded chase-up' AND json_extract(details,'$.chaseId') IN (SELECT id FROM chases WHERE json_extract(body,'$.note')=?)",(older,'Older archived follow-up'))
        self.assertEqual(self.inbox()['total'],0)
        self.real_sweep(self.store,force=True,now=now)
        result=self.inbox(q='alex example')
        self.assertEqual(result['total'],2)
        self.assertTrue(all(n['createdAt']==previous for n in result['items']))
        self.assertTrue(any('Recent follow-up saved before release' in n['message'] for n in result['items']))
        self.assertEqual(self.inbox(self.author)['total'],2)
        self.assertEqual(self.inbox(q='Older archived')['total'],0)
        self.assertEqual(self.inbox(q='Workbook-style')['total'],0)
        ids=[n['id'] for n in result['items']]
        op.mark_read(self.store,{'ids':ids},self.reader)
        self.real_sweep(self.store,force=True,now=now)
        again=self.inbox()
        self.assertEqual({n['id'] for n in again['items']},set(ids))
        self.assertTrue(all(n['read'] for n in again['items']))
        self.assertTrue(all(not n['read'] for n in self.inbox(self.author)['items']))

    def test_failed_write_rolls_back_history_and_notifications(self):
        with patch.object(op,'notify_recorded_chase',side_effect=RuntimeError('test transaction failure')):
            with self.assertRaises(RuntimeError): self.record()
        self.assertEqual(self.inbox()['total'],0)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM chases WHERE submission_id=?',(self.submission,)).fetchone()[0],0)
        self.record()
        self.assertEqual(self.inbox()['total'],1)


if __name__=='__main__':unittest.main()
