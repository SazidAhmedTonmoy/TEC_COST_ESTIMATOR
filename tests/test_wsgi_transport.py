import gzip,unittest
from passenger_wsgi import prepare_response,accepts_gzip,_request_bytes

class TransportTests(unittest.TestCase):
 def test_compression_negotiation_and_exact_length(self):
  raw=b'{"project":"'+b'example '*40000+b'"}'
  headers=[('Content-Type','application/json; charset=utf-8'),('Content-Length','3'),('Cache-Control','no-store')]
  for accepted,compress in [('gzip, deflate, br',True),('gzip;q=0, *;q=1',False),('',False),('br',False)]:
   out,body=prepare_response({'REQUEST_METHOD':'GET','PATH_INFO':'/api/projects/11','HTTP_ACCEPT_ENCODING':accepted},200,headers,raw)
   out=dict(out);self.assertEqual(int(out['Content-Length']),len(body));self.assertEqual(out['Cache-Control'],'no-store')
   self.assertEqual(gzip.decompress(body) if compress else body,raw)
   self.assertEqual(out.get('Content-Encoding'), 'gzip' if compress else None)
  for path in ['/api/auth/session','/api/settings']:
   out,body=prepare_response({'PATH_INFO':path,'HTTP_ACCEPT_ENCODING':'gzip'},200,headers,raw)
   self.assertEqual(body,raw)
 def test_transport_headers_and_empty_responses(self):
  headers=[('Connection','keep-alive, X-Hop'),('Keep-Alive','timeout=5'),('X-Hop','private'),('Transfer-Encoding','chunked'),('Status','200 OK'),('Set-Cookie','a=1'),('Set-Cookie','b=2'),('Content-Length','999')]
  out,body=prepare_response({},200,headers,b'ok')
  self.assertEqual(out,[('Set-Cookie','a=1'),('Set-Cookie','b=2'),('Content-Length','2')])
  out,body=prepare_response({},204,headers,b'invalid');self.assertEqual(body,b'');self.assertNotIn('Content-Length',dict(out))
 def test_internal_request_has_single_connection_header(self):
  raw=_request_bytes({'REQUEST_METHOD':'GET','HTTP_CONNECTION':'keep-alive, X-Hop','HTTP_X_HOP':'x','HTTP_TE':'trailers','PATH_INFO':'/'})
  self.assertEqual(raw.count(b'Connection:'),1);self.assertNotIn(b'X-Hop:',raw)
