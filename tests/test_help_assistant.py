"""v3.7.27: guide, explicit assistant writes, permission checks, idempotence."""
import unittest
from unittest.mock import patch
from conest_app.database import connect
from support_http_access import Http232Tests


class HelpAssistantHTTPTests(unittest.TestCase):
    setUp=Http232Tests.setUp
    tearDown=Http232Tests.tearDown
    request=Http232Tests.request
    login_as=Http232Tests.login_as

    def test_guide_is_comprehensive_and_authenticated(self):
        status,payload=self.request('GET','/api/assistant/guide')
        self.assertEqual(status,200,payload)
        topics=[entry['id'] for group in payload['sections'] for entry in group['articles']]
        for name in ['breakdown','revisions','estimate-export','opportunities','analytics','chase-up','users-teams','assistant']:
            self.assertIn(name,topics)
        self.cookie='';self.csrf=''
        self.assertEqual(self.request('GET','/api/assistant/guide')[0],401)

    def test_note_requires_confirmation_and_is_idempotent(self):
        pid=self.data['project_id'];self.login_as('editor')
        before=self.request('GET',f'/api/projects/{pid}/notes')[1]['notes']
        status,response=self.request('POST','/api/assistant/chat',{
            'question':'Add note to this estimate: Confirm light fitting pricing before tender',
            'project_id':pid,'chatMode':'project','useAI':False})
        self.assertEqual(status,200,response)
        preview=response['actionPreview'];self.assertIn('Confirm light fitting pricing',preview['description'])
        self.assertEqual(len(self.request('GET',f'/api/projects/{pid}/notes')[1]['notes']),len(before))
        self.assertEqual(self.request('POST','/api/assistant/action',{'command':'confirm','token':preview['token']},csrf=False)[0],403)
        status,result=self.request('POST','/api/assistant/action',{'command':'confirm','token':preview['token']})
        self.assertEqual(status,200,result)
        after=self.request('GET',f'/api/projects/{pid}/notes')[1]['notes']
        self.assertEqual(len(after),len(before)+1)
        self.assertEqual(after[0]['body'],'Confirm light fitting pricing before tender')
        self.assertEqual(self.request('POST','/api/assistant/action',{'command':'confirm','token':preview['token']})[0],409)
        self.assertEqual(len(self.request('GET',f'/api/projects/{pid}/notes')[1]['notes']),len(after))

    def test_progress_preview_can_cancel_and_detect_revision_change(self):
        pid=self.data['project_id'];self.login_as('editor')
        status,preview=self.request('POST','/api/assistant/chat',{
            'question':'Set this project status to in progress','project_id':pid})
        self.assertEqual(status,200,preview)
        token=preview['actionPreview']['token']
        self.assertEqual(self.request('POST','/api/assistant/action',{'command':'cancel','token':token})[0],200)
        self.assertEqual(self.request('POST','/api/assistant/action',{'command':'confirm','token':token})[0],409)
        status,preview=self.request('POST','/api/assistant/chat',{
            'question':'Set this project status to in progress','project_id':pid})
        token=preview['actionPreview']['token']
        with connect() as c:
            c.execute('UPDATE projects SET revision=revision+1 WHERE id=?',(pid,))
        self.assertEqual(self.request('POST','/api/assistant/action',{'command':'confirm','token':token})[0],409)
        status,fresh=self.request('POST','/api/assistant/chat',{
            'question':'Set this project status to in progress','project_id':pid})
        self.assertEqual(status,200,fresh)
        status,done=self.request('POST','/api/assistant/action',{'command':'confirm','token':fresh['actionPreview']['token']})
        self.assertEqual(status,200,done)
        self.assertEqual(self.request('GET',f'/api/projects/{pid}')[1]['project']['status'],'in_progress')

    def test_manager_can_confirm_deadline_result_and_name(self):
        pid=self.data['project_id'];self.login_as('owner')
        for question,field,expected in [
            ('Set this project deadline to 2026-12-18','submission_deadline','2026-12-18'),
            ('Mark this project as won','award_status','won'),
            ('Rename this project to EstiDoc Demo Project','name','EstiDoc Demo Project'),
            ('Set this project status to in review until 2026-12-20','review_deadline','2026-12-20'),
        ]:
            status,pending=self.request('POST','/api/assistant/chat',{'question':question,'project_id':pid})
            self.assertEqual(status,200,pending)
            token=pending['actionPreview']['token']
            status,result=self.request('POST','/api/assistant/action',{'command':'confirm','token':token})
            self.assertEqual(status,200,result)
            value=self.request('GET',f'/api/projects/{pid}')[1]['project'][field]
            self.assertEqual(value,expected)

    def test_individual_editor_cannot_rename_or_change_deadline(self):
        pid=self.data['project_id'];self.login_as('editor')
        for question in ('Rename this project to Not Allowed','Set this project deadline to 2026-12-18'):
            status,result=self.request('POST','/api/assistant/chat',{'question':question,'project_id':pid})
            self.assertEqual(status,403,result)

    def test_view_only_user_cannot_preview_action(self):
        pid=self.data['project_id'];self.login_as('viewer')
        self.assertEqual(self.request('POST','/api/assistant/chat',{
            'question':'Add note to this estimate: Not authorized', 'project_id':pid})[0],403)
        with connect() as c:
            self.assertFalse(c.execute('SELECT 1 FROM project_notes WHERE project_id=? AND body=?',(pid,'Not authorized')).fetchone())

    def test_settings_are_individual_and_do_not_expose_pending_action(self):
        pid=self.data['project_id'];self.login_as('editor')
        self.assertEqual(self.request('POST','/api/assistant/memory',{'useAI':True})[0],200)
        self.assertEqual(self.request('GET','/api/assistant/memory')[1]['useAI'],True)
        self.request('POST','/api/assistant/chat',{'question':'Add note: Check builder scope', 'project_id':pid})
        memory=self.request('GET','/api/assistant/memory')[1]
        self.assertNotIn('pending_action',memory)
        self.request('POST','/api/assistant/memory',{'clearConversation':True})
        self.assertEqual(self.request('GET','/api/assistant/memory')[1]['useAI'],True)
        self.assertEqual(self.request('POST','/api/assistant/action',{'command':'confirm','token':'a'*32})[0],409)


if __name__=='__main__':unittest.main()
