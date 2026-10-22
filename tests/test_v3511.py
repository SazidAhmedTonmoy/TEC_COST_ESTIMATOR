"""Release 3.5.11: shared login, safe static delivery and consolidated docs."""
import gzip
from http.server import ThreadingHTTPServer
import http.client
from pathlib import Path
import re
import threading
import unittest

from app import ConEstHandler, _accepts_gzip, _public_asset_bytes
from conest_app import __version__

ROOT=Path(__file__).resolve().parents[1]


class QuietHandler(ConEstHandler):
    def log_message(self,*args):
        return


class MobileReleaseTests(unittest.TestCase):
    def test_login_three_local_slides_and_shared_wording(self):
        html=(ROOT/'assets/index.html').read_text()
        self.assertIn('TEC ConEst · Tenders &amp; Estimating',html)
        self.assertEqual(len(re.findall(r'<div class="login-slide(?: |")',html)),3)
        self.assertNotIn('<span>ESTIMATOR</span>',html)
        self.assertIn('tenders and estimating workspace',html)
        for asset in ('login-blueprint.svg','login-blueprint-switchboard.svg','login-blueprint-buildings.svg','responsive-v3511.css','login-carousel.js'):
            self.assertTrue((ROOT/'assets'/asset).is_file(),asset)
        self.assertIn('INTERVAL = 3000',(ROOT/'assets/login-carousel.js').read_text())
        self.assertIn('prefers-reduced-motion',(ROOT/'assets/login-carousel.js').read_text())

    def test_mobile_source_and_served_tender_css(self):
        source=(ROOT/'tenders_frontend/src/mobile-v3511.css').read_bytes()
        dist=(ROOT/'tenders_web/assets/mobile-v3511.css').read_bytes()
        self.assertEqual(source,dist)
        self.assertIn('mobile-v3511.css',(ROOT/'tenders_frontend/src/main.tsx').read_text())
        self.assertIn('mobile-v3511.css',(ROOT/'tenders_web/index.html').read_text())
        self.assertIn('responsive-v3511.css',(ROOT/'assets/index.html').read_text())

    def test_version_and_single_document(self):
        self.assertGreaterEqual(tuple(int(n) for n in __version__.split('.')), (3,5,11))
        self.assertTrue((ROOT/'README.md').is_file())
        self.assertIn('Production deployment',(ROOT/'README.md').read_text())
        legacy=[p.name for p in ROOT.iterdir() if p.name.startswith(('QUALITY_REVIEW','CHANGED_FILES','UPDATE_INSTRUCTIONS','V3.5'))]
        self.assertFalse(legacy,legacy)
        self.assertFalse(list((ROOT/"opportunities_seed").glob("*.md")))
        self.assertFalse(list((ROOT/"opportunities_seed").glob("*.txt")))

    def test_gzip_negotiation(self):
        self.assertTrue(_accepts_gzip('gzip, deflate'))
        self.assertTrue(_accepts_gzip('br, gzip;q=0.2'))
        self.assertFalse(_accepts_gzip('gzip;q=0'))
        self.assertFalse(_accepts_gzip('gzip;q=0.0'))
        self.assertFalse(_accepts_gzip('br'))

    def test_cache_invalidates_on_mtime_and_size(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            file=Path(td)/'asset.js';file.write_bytes(b'a'*6000)
            initial=file.stat()
            encoded=_public_asset_bytes(str(file),initial.st_mtime_ns,initial.st_size,True)
            self.assertEqual(gzip.decompress(encoded),b'a'*6000)
            file.write_bytes(b'b'*5000)
            current=file.stat()
            updated=_public_asset_bytes(str(file),current.st_mtime_ns,current.st_size,True)
            self.assertEqual(gzip.decompress(updated),b'b'*5000)

    def test_static_assets_compress_but_exports_do_not(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        runner=threading.Thread(target=server.serve_forever,daemon=True);runner.start()
        try:
            for accepts in (None,'gzip','gzip;q=0'):
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
                headers={'Accept-Encoding':accepts} if accepts else {}
                connection.request('GET','/assets/responsive-v3511.css',headers=headers)
                response=connection.getresponse()
                raw=response.read()
                self.assertEqual(response.status,200)
                self.assertEqual(response.getheader('Vary'),'Accept-Encoding')
                if accepts=='gzip':
                    self.assertEqual(response.getheader('Content-Encoding'),'gzip')
                    self.assertEqual(gzip.decompress(raw),(ROOT/'assets/responsive-v3511.css').read_bytes())
                else:
                    self.assertIsNone(response.getheader('Content-Encoding'))
                    self.assertEqual(raw,(ROOT/'assets/responsive-v3511.css').read_bytes())
                connection.close()
        finally:
            server.shutdown();server.server_close();runner.join()
