import unittest
from unittest.mock import patch
import test_http_v231 as helpers
from conest_app import tenders

class ChatModesTests(unittest.TestCase):
 request=helpers.HttpPatchTests.request
 def setUp(self):tenders._store=None;helpers.HttpPatchTests.setUp(self)
 def tearDown(self):tenders._store=None;helpers.HttpPatchTests.tearDown(self)
 def test_normal_and_greeting_do_not_retrieve_records(self):
  with patch('conest_app.workspace_tools.help_chat.prepare_context',side_effect=AssertionError('Unexpected database lookup')),patch('conest_app.workspace_tools.tender_answer',side_effect=AssertionError('Unexpected tender lookup')):
   for mode,question in [('normal','tell me about tenders'),('project','hi')]:
    status,data=self.request('POST','/api/assistant/chat',{'question':question,'chatMode':mode})
    self.assertEqual(status,200,data);self.assertEqual(data['sources'],[])
    self.assertNotIn('matching records',data['answer'])
 def test_model_override_and_normal_context_isolation(self):
  self.request('POST','/api/assistant/chat',{'question':'last 5 tenders'})
  with patch('conest_app.workspace_tools.assistant._api_key',return_value='test'),patch('conest_app.workspace_tools.assistant._enabled',return_value=True),patch('conest_app.workspace_tools.assistant._gemini_generate',return_value='General answer') as generate:
   status,options=self.request('GET','/api/assistant/memory')
   model=options['models'][-1]
   status,data=self.request('POST','/api/assistant/chat',{'question':'Explain fractions','chatMode':'normal','useAI':True,'model':model})
   self.assertEqual(status,200,data);self.assertEqual(data['answer'],'General answer')
   self.assertEqual(generate.call_args.args[1],model)
   self.assertNotIn('last 5 tenders',generate.call_args.args[2])
  status,_=self.request('POST','/api/assistant/chat',{'question':'Hello','model':'invalid-model'})
  self.assertEqual(status,400)
