"""Browser OCR resources, deployment checks and the private contact parser."""
import gzip
import http.client
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from app import ConEstHandler
from conest_app import tender_http
from conest_app.browser_ocr_assets import OCR_PREFIX, OCR_MIME
from tools import check_uploaded_release as checker


class QuietHandler(ConEstHandler):
    def log_message(self, *args):
        pass


class BrowserOCRAssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.asset_dir = self.root / 'tenders_web/assets/ocr-v6.0.1'
        self.asset_dir.mkdir(parents=True)
        self.model = gzip.compress(b'test model data' * 200)
        (self.asset_dir / 'eng.traineddata.gz').write_bytes(self.model)
        (self.asset_dir / 'worker.min.js').write_text('/* worker fixture */')
        (self.asset_dir / 'tesseract-core-lstm.wasm').write_bytes(b'\x00asm')
        (self.root / 'tenders_web/index.html').write_text('<html></html>')
        self.patch = patch.object(tender_http, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.shutdown)

    def request(self, path):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request('GET', path, headers={'Accept-Encoding':'gzip'})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_worker_has_scoped_wasm_policy_and_main_page_does_not(self):
        status, headers, _ = self.request(OCR_PREFIX + 'worker.min.js')
        self.assertEqual(status, 200)
        self.assertIn("'wasm-unsafe-eval'", headers['Content-Security-Policy'])
        self.assertNotIn("'unsafe-eval'", headers['Content-Security-Policy'])
        self.assertIn("connect-src 'self'", headers['Content-Security-Policy'])
        status, headers, _ = self.request('/tenders/calendar')
        self.assertEqual(status, 200)
        self.assertNotIn("'wasm-unsafe-eval'", headers['Content-Security-Policy'])

    def test_model_is_same_origin_gzip_file_not_transport_encoded(self):
        status, headers, body = self.request(OCR_PREFIX + 'eng.traineddata.gz')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/gzip')
        self.assertNotIn('Content-Encoding', headers)
        self.assertEqual(body, self.model)
        self.assertIn('immutable', headers['Cache-Control'])
        status, headers, _ = self.request(OCR_PREFIX + 'tesseract-core-lstm.wasm')
        self.assertEqual((status, headers['Content-Type']), (200, 'application/wasm'))

    def test_missing_and_unsafe_asset_paths_are_rejected(self):
        (self.asset_dir / 'private.db').write_bytes(b'private')
        for name in ('private.db', '../index.html', '%2e%2e/index.html', 'missing.js', 'tesseract.min.js'):
            with self.subTest(name=name):
                self.assertEqual(self.request(OCR_PREFIX + name)[0], 404)

    def test_deploy_manifest_requires_all_ocr_files_when_feature_is_present(self):
        root = self.root / 'manifest-test'
        root.mkdir()
        def write(name, text='test asset'):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        for name in checker.REQUIRED_FILES:
            write(name)
        write('conest_app/__init__.py', '__version__ = "3.8.10"')
        write(checker.OCR_SOURCE)
        self.assertEqual(checker.OCR_BUILD_FILES, {'tenders_web/assets/ocr-v6.0.1/' + name for name in OCR_MIME})
        with self.assertRaisesRegex(checker.ReleaseCheckError, 'eng.traineddata.gz'):
            checker.create_manifest(root)
        for name in checker.OCR_BUILD_FILES:
            write(name)
        manifest = checker.create_manifest(root)
        self.assertTrue(checker.OCR_BUILD_FILES.issubset(manifest['files']))
        self.assertFalse(checker.allowed_path('tenders_web/assets/ocr-v6.0.1/catalog.db.gz'))
        del manifest['files']['tenders_web/assets/ocr-v6.0.1/eng.traineddata.gz']
        with self.assertRaisesRegex(checker.ReleaseCheckError, 'omits required'):
            checker.verify_manifest(root, manifest)


if __name__ == '__main__':
    unittest.main()
