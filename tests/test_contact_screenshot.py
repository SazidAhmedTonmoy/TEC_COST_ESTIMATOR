"""Screenshot import is private, bounded and preview-only."""
import base64
import io
import subprocess
import unittest
from unittest.mock import patch
from PIL import Image
from conest_app import contact_screenshot as scan
from conest_app.tenders import ValidationError

TEXT = '''Builder
Example Constructions
(NSW)
0450 111 222
Alex Example
alex@example.com
Second Construction Group
0426 333 444
Sam Sample
sam@example.com
'''

class ContactScreenshotTests(unittest.TestCase):
    def image(self):
        out = io.BytesIO()
        Image.new('RGB', (120, 100), 'white').save(out, 'PNG')
        return base64.b64encode(out.getvalue()).decode()

    def test_sample_layout_and_wrapped_region(self):
        rows = scan.parse_contact_text(TEXT)['rows']
        self.assertEqual(rows, [
            {'builder':'Example Constructions (NSW)','name':'Alex Example','phones':['0450 111 222'],'emails':['alex@example.com']},
            {'builder':'Second Construction Group','name':'Sam Sample','phones':['0426 333 444'],'emails':['sam@example.com']},
        ])

    def test_known_company_multiple_people_and_international_phone(self):
        text = 'SpecialCo\nFirst Person\n+61 400 111 222\na@example.com\nSecond Person\n02 9000 1234\nb@example.com'
        rows = scan.parse_contact_text(text,['SpecialCo'])['rows']
        self.assertEqual([r['builder'] for r in rows],['SpecialCo','SpecialCo'])
        self.assertEqual([r['name'] for r in rows],['First Person','Second Person'])
        self.assertEqual(rows[0]['phones'],['+61 400 111 222'])

    def test_text_fallback_never_calls_ocr(self):
        with patch.object(scan.subprocess,'run') as run:
            self.assertEqual(len(scan.recognize({'text':TEXT})['rows']),2)
            run.assert_not_called()

    def test_local_image_recognition_passes_only_png_bytes_and_no_shell(self):
        with patch.object(scan.shutil,'which',return_value='/usr/bin/tesseract'),patch.object(scan.subprocess,'run',return_value=subprocess.CompletedProcess([],0,TEXT.encode())) as run:
            result=scan.recognize({'content':self.image()})
            self.assertEqual(len(result['rows']),2)
            args,kwargs=run.call_args
            self.assertEqual(args[0][:3],['/usr/bin/tesseract','stdin','stdout'])
            self.assertTrue(kwargs['input'].startswith(b'\x89PNG'))
            self.assertFalse(kwargs.get('shell',False))
            self.assertEqual(kwargs['timeout'],18)

    def test_unavailable_ocr_is_actionable(self):
        with patch.object(scan.shutil,'which',return_value=None):
            with self.assertRaises(ValidationError) as caught:
                scan.recognize({'content':self.image()})
            self.assertEqual(caught.exception.status,503)
            self.assertIn('Tesseract',str(caught.exception))

    def test_invalid_image_and_timeout_release_slot(self):
        with patch.object(scan.shutil,'which',return_value='/usr/bin/tesseract'):
            with self.assertRaises(ValidationError):scan.recognize({'content':base64.b64encode(b'not an image').decode()})
            with patch.object(scan.subprocess,'run',side_effect=subprocess.TimeoutExpired('tesseract',18)):
                with self.assertRaises(ValidationError) as caught:scan.recognize({'content':self.image()})
                self.assertEqual(caught.exception.status,503)
            self.assertTrue(scan._SLOTS.acquire(blocking=False))
            scan._SLOTS.release()

    def test_invalid_payload_is_rejected(self):
        for payload in ({'text':None},{'text':'a'*(scan.MAX_TEXT+1)},{'content':'not base64!'}, {'knownBuilders':[{ 'name':'bad'}],'text':TEXT}):
            with self.subTest(payload=type(payload)):
                with self.assertRaises(ValidationError):scan.recognize(payload)

    def test_image_dimensions_are_bounded(self):
        with patch.object(scan,'MAX_PIXELS',100):
            with self.assertRaises(ValidationError):scan._prepare_image(base64.b64decode(self.image()))

class ContactScreenshotHttpTests(unittest.TestCase):
    from support_http import HttpPatchTests as _Helpers
    request = _Helpers.request

    def setUp(self):
        from conest_app import tenders
        tenders.close_store()
        self._Helpers.setUp(self)

    def tearDown(self):
        from conest_app import tenders
        tenders.close_store()
        self._Helpers.tearDown(self)

    def test_preview_requires_login_and_csrf_and_only_save_adds_contacts(self):
        path = '/api/tenders/opportunities/contact-screenshot'
        status, before = self.request('GET', '/api/tenders/builder-contacts')
        self.assertEqual(status, 200)
        status, _ = self.request('POST', path, {'text':TEXT}, csrf=False)
        self.assertEqual(status, 403)
        cookie = self.cookie
        self.cookie = ''
        status, _ = self.request('POST', path, {'text':TEXT})
        self.assertEqual(status, 401)
        self.cookie = cookie
        status, preview = self.request('POST', path, {'text':TEXT})
        self.assertEqual(status, 200, preview)
        self.assertEqual(len(preview['rows']), 2)
        status, after = self.request('GET', '/api/tenders/builder-contacts')
        self.assertEqual(status, 200)
        self.assertEqual(before['builders'], after['builders'])
        groups = [{'builder':r['builder'], 'contacts':[{key:r[key] for key in ('name','phones','emails')}]} for r in preview['rows']]
        status, result = self.request('POST','/api/tenders/opportunities/save',{
            'project':'Screenshot import preview test', 'region':'NSW', 'due':'2099-12-01',
            'builders':[g['builder'] for g in groups], 'builderContacts':groups})
        self.assertEqual(status, 200, result)
        self.assertEqual(len(result['opportunity']['builderContacts']),2)
        status, after_save = self.request('GET', '/api/tenders/builder-contacts')
        self.assertEqual(status, 200)
        contact = next(g['contacts'][0] for g in after_save['builders'] if g['builder']=='Example Constructions (NSW)')
        self.assertEqual(contact['name'],'Alex Example')


if __name__=='__main__':unittest.main()
