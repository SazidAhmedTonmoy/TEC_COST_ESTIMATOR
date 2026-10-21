"""Opportunity contributions stay distinct, attributed and visible after deletion."""
import unittest
from pathlib import Path
from conest_app import tenders
import test_http_v231 as helpers


class Contribution35Tests(unittest.TestCase):
    request=helpers.HttpPatchTests.request

    def setUp(self):
        tenders._store=None
        helpers.HttpPatchTests.setUp(self)

    def tearDown(self):
        tenders._store=None
        helpers.HttpPatchTests.tearDown(self)

    def test_actions_count_once_and_deletion_retains_user_history(self):
        status,created=self.request('POST','/api/tenders/opportunities/save',{
            'project':'Contribution workflow','region':'NSW','builders':['Example builder'],
            'due':'2099-01-01','workingScope':'Lighting and power'})
        self.assertEqual(status,200,created)
        item=created['opportunity']
        status,approved=self.request('POST','/api/tenders/opportunities/decision',{
            'id':item['id'],'revision':item['revision'],'decision':'approved'})
        self.assertEqual(status,200,approved)
        item=approved['opportunity']
        status,deleted=self.request('DELETE','/api/tenders/opportunities',{
            'id':item['id'],'revision':item['revision']})
        self.assertEqual(status,200,deleted)
        status,report=self.request('GET',f'/api/users/{self.user_id}/performance')
        self.assertEqual(status,200,report)
        self.assertEqual(report['opportunities']['projects'],1)
        self.assertEqual(report['opportunities']['total'],3)
        self.assertEqual({r['action'] for r in report['opportunities']['actions']},
                         {'Created opportunity','Approved opportunity','Deleted opportunity'})
        self.assertEqual(report['tenders']['total'],0)
        self.assertEqual(report['tenders']['submissions'],0)
        self.assertEqual(len([r for r in report['recent'] if r['app']=='Opportunities']),3)
        status,filtered=self.request('GET',f'/api/users/{self.user_id}/performance?since=2098-01-01&until=2099-01-01')
        self.assertEqual(status,200,filtered)
        self.assertEqual(filtered['opportunities']['total'],0)
        status,retained=self.request('GET','/api/tenders/opportunities/detail?id='+item['id'])
        self.assertEqual(status,200,retained)
        self.assertTrue(retained['opportunity']['deletedAt'])
        self.assertEqual(len(retained['activity']),3)

    def test_region_configuration_is_work_not_an_excel_upload(self):
        _,before=self.request('GET',f'/api/users/{self.user_id}/performance')
        status,result=self.request('POST','/api/tenders/opportunities/regions',{
            'code':'QLD','origin':'Brisbane CBD','timezone':'Australia/Brisbane'})
        self.assertEqual(status,200,result)
        _,after=self.request('GET',f'/api/users/{self.user_id}/performance')
        self.assertEqual(after['uploads'],before['uploads'])
        self.assertEqual(after['opportunities']['projects'],0)
        self.assertEqual(after['opportunities']['total'],1)
        self.assertEqual(after['opportunities']['actions'][0]['action'],'Updated opportunity region')
        self.assertEqual(after['tenders']['total'],before['tenders']['total'])


class DeadlineScheduleTests(unittest.TestCase):
    def test_cron_reinstall_keeps_backups_and_other_jobs(self):
        from tools.install_backup_cron import cron_line,deadline_cron_line,updated_crontab
        original='0 4 * * * /usr/local/bin/unrelated\n'
        backup,backup_tag=cron_line(Path('/tmp/TEC test'),'python3')
        deadline,deadline_tag=deadline_cron_line(Path('/tmp/TEC test'),'python3')
        result=updated_crontab(updated_crontab(original,backup,backup_tag),deadline,deadline_tag)
        again=updated_crontab(updated_crontab(result,backup,backup_tag),deadline,deadline_tag)
        self.assertEqual(result,again)
        self.assertTrue(result.startswith(original))
        self.assertIn('*/5 * * *',deadline)
        self.assertIn("'/tmp/TEC test/tools/process_opportunity_deadlines.py'",deadline)
        self.assertEqual(result.count(backup_tag),1)
        self.assertEqual(result.count(deadline_tag),1)
