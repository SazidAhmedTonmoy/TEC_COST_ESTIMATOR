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

 def test_production_gate_requires_tender_readiness(self):
  script=Path(__file__).resolve().parents[1]/'tools/check_deployment_health.py'
  good={'success':True,'status':'ok','release':__version__,'schema_version':CURRENT_SCHEMA}
  checks={'tenders':'ok','opportunities':'ok','timezones':'ok','sqlite':'ok'}
  for data,code in [(good,1),({**good,'checks':checks},0),({**good,'checks':{**checks,'tenders':'failed'}},1),([],1)]:
   p=subprocess.run([sys.executable,str(script),'--require-tenders'],input=json.dumps(data),text=True,capture_output=True)
   self.assertEqual(p.returncode,code,p.stderr)
