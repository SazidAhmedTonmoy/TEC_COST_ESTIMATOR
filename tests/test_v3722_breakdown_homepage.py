"""v3.7.22: opt-in Breakdown and multiple team homepage/access behaviour."""
import json
from pathlib import Path
import unittest
from openpyxl import load_workbook
import test_estimate_sections as fixtures
from conest_app import accounts,estimate_areas,projects,project_sharing,teams,workspace
from conest_app.database import connect
from conest_app.exporter import export_project


class BreakdownAndHomepageTests(unittest.TestCase):
    setUp=fixtures.EstimateSectionTests.setUp
    tearDown=fixtures.EstimateSectionTests.tearDown

    def test_breakdown_inactive_until_enabled_and_absent_from_exports(self):
        with connect() as conn:
            pid,_=fixtures.EstimateSectionTests.prepare(self,conn)
            actor=self.data['owner']
            before=projects.calculate_project(conn,pid)
            self.assertFalse(before['project']['breakdown_enabled'])
            self.assertNotIn('Structured breakdown',project_sharing.shared_html(before))
            with self.assertRaisesRegex(ValueError,'Activate Breakdown'):
                estimate_areas.save_breakdown(conn,pid,actor,{'expected_revision':before['project']['revision'],'areas':[],'rows':[]})
            path=export_project(conn,pid,Path(self.tmp.name)/'inactive.xlsx')
            wb=load_workbook(path);self.assertNotIn('AREA ALLOCATIONS',wb.sheetnames);self.assertNotIn('STRUCTURED BREAKDOWN',wb.sheetnames);wb.close()
            activated=estimate_areas.set_breakdown_enabled(conn,pid,actor,{'enabled':True,'expected_revision':before['project']['revision']})
            self.assertTrue(activated['project']['breakdown_enabled'])
            line=activated['lines'][0]
            rows=[{'id':l['id'],'expected_revision':l['revision'],'quantity':l['quantity'],
                   'allocations':[{'area':'Level 1','quantity':l['quantity']}] if l['id']==line['id'] else []}
                  for l in activated['lines']]
            saved=estimate_areas.save_breakdown(conn,pid,actor,{'expected_revision':activated['project']['revision'],
                                                                  'areas':['Level 1'],'rows':rows})
            self.assertEqual(saved['area_summary'][0]['area'],'Level 1')
            self.assertEqual(saved['lines'][0]['reference_name'],'D1')
            self.assertTrue(any(item.get('reference')=='D1' for area in saved['area_summary'] for category in area['categories'] for item in category['items']))
            path=export_project(conn,pid,Path(self.tmp.name)/'active.xlsx')
            wb=load_workbook(path);self.assertIn('AREA ALLOCATIONS',wb.sheetnames);self.assertIn('STRUCTURED BREAKDOWN',wb.sheetnames);wb.close()
            off=estimate_areas.set_breakdown_enabled(conn,pid,actor,{'enabled':False,'expected_revision':saved['project']['revision']})
            self.assertFalse(off['project']['breakdown_enabled'])
            self.assertEqual(json.loads(off['lines'][0]['area_allocations'])[0]['area'],'Level 1')
            self.assertNotIn('Area breakdown',project_sharing.shared_html(off))
            path=export_project(conn,pid,Path(self.tmp.name)/'off-again.xlsx')
            wb=load_workbook(path);self.assertNotIn('AREA ALLOCATIONS',wb.sheetnames);wb.close()
            on=estimate_areas.set_breakdown_enabled(conn,pid,actor,{'enabled':True,'expected_revision':off['project']['revision']})
            self.assertEqual(json.loads(on['lines'][0]['area_allocations'])[0]['area'],'Level 1')

    def test_multi_team_membership_permissions_and_homepage_overrides(self):
        with connect() as conn:
            member=self.data['editor'];other=self.data['viewer'];admin=self.data['admin']
            first=member['team_id'];second=other['team_id'];pid=self.data['project_id']
            self.assertEqual(teams.user_team_ids(conn,member['id']),[first])
            self.assertEqual(teams.effective_homepage(conn,admin['id'],'admin',[],None),'estimator')
            self.assertEqual(teams.effective_homepage(conn,other['id'],'user',[],None),'tenders')
            group=teams.save_team(conn,{'name':'Cross Team Test','uses_estimator':False,'default_homepage':'tenders',
                                        'member_ids':[member['id']]},admin)
            ids=teams.user_team_ids(conn,member['id'])
            self.assertIn(first,ids);self.assertIn(group['id'],ids)
            self.assertEqual(teams.team_default_homepage(conn,group['id'],group['name']),'tenders')
            conn.execute('DELETE FROM project_teams WHERE project_id=?',(pid,))
            conn.execute('INSERT INTO project_teams(project_id,team_id,assigned_by,assigned_at) VALUES(?,?,?,?)',
                         (pid,group['id'],admin['id'],'2026-11-12T00:00:00Z'))
            self.assertTrue(workspace.permissions(conn,workspace.get_project(conn,pid),member)['can_edit'])
            teams.save_team(conn,{'name':group['name'],'member_ids':[]},admin,group['id'])
            self.assertEqual(teams.user_team_ids(conn,member['id']),[first])
            self.assertFalse(workspace.permissions(conn,workspace.get_project(conn,pid),member)['can_edit'])
            teams.set_user_teams(conn,member['id'],[first,second],first)
            updated=accounts.edit_user(conn,member['id'],{'homepage':'tenders'},member)
            self.assertEqual(updated['team_ids'],sorted([first,second]))
            self.assertEqual(updated['homepage'],'tenders')
            updated=accounts.edit_user(conn,member['id'],{'homepage':'estimator'},member)
            self.assertEqual(updated['homepage'],'estimator')
            teams.set_user_teams(conn,member['id'],[])
            self.assertEqual(accounts.enriched_user(conn,conn.execute('SELECT * FROM users WHERE id=?',(member['id'],)).fetchone())['homepage'],'tenders')
            self.assertEqual(teams.user_team_ids(conn,member['id']),[])

if __name__=='__main__':unittest.main()
