import unittest,json,subprocess,sys
from pathlib import Path
from conest_app import __version__
from conest_app.auto_upgrade import CURRENT_SCHEMA
class DeploymentHealthTests(unittest.TestCase):
 def test_health_matches_checkout_and_rejects_stale_invalid(self):
  script=Path(__file__).resolve().parents[1]/'tools/check_deployment_health.py'
  good={'success':True,'status':'ok','release':__version__,'schema_version':CURRENT_SCHEMA}
  for data,code in [(json.dumps(good),0),(json.dumps({**good,'schema_version':CURRENT_SCHEMA-1}),1),(json.dumps({**good,'release':'old'}),1),('invalid response',1)]:
   p=subprocess.run([sys.executable,str(script)],input=data,text=True,capture_output=True)
   self.assertEqual(p.returncode,code,p.stderr)
