import json
import subprocess
import sys
import unittest
from pathlib import Path

from conest_app import __version__
from conest_app.auto_upgrade import CURRENT_SCHEMA
from tools.check_deployment_health import matches


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/check_deployment_health.py'
CHECKS = {'tenders': 'ok', 'opportunities': 'ok', 'timezones': 'ok', 'sqlite': 'ok'}


class DeploymentHealthTests(unittest.TestCase):
    def healthy(self):
        return {'success': True, 'status': 'ok', 'release': __version__,
                'schema_version': CURRENT_SCHEMA, 'checks': dict(CHECKS)}

    def run_check(self, response, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], input=response,
                              text=True, capture_output=True)

    def test_health_matches_checkout_and_rejects_stale_invalid(self):
        good = self.healthy()
        self.assertTrue(matches(good))
        for data, code in [
            (json.dumps(good), 0),
            (json.dumps({**good, 'schema_version': CURRENT_SCHEMA - 1}), 1),
            (json.dumps({**good, 'release': 'old'}), 1),
            ('invalid response', 1),
        ]:
            with self.subTest(expected=code, data_type=data[:1]):
                result = self.run_check(data)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr, '')

    def test_production_gate_requires_tender_readiness(self):
        good = self.healthy()
        incomplete = {key: value for key, value in good.items() if key != 'checks'}
        for data, code in [
            (incomplete, 1),
            (good, 0),
            ({**good, 'checks': {**CHECKS, 'tenders': 'failed'}}, 1),
            ([], 1),
        ]:
            with self.subTest(expected=code, response_type=type(data).__name__):
                result = self.run_check(json.dumps(data), '--require-tenders')
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(matches(data, require_tenders=True), code == 0)

    def test_healthy_old_release_is_rejected_with_specific_diagnostic(self):
        response = {**self.healthy(), 'release': '3.8.6'}
        result = self.run_check(json.dumps(response), '--require-tenders', '--explain')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn(f'Release mismatch: expected {__version__}, received 3.8.6.', result.stderr)
        self.assertIn('upload destination', result.stderr)
        self.assertIn('restart the Passenger application', result.stderr)
        self.assertNotIn('Schema mismatch', result.stderr)
        self.assertNotIn('Required checks are not ready', result.stderr)

    def test_schema_mismatch_explains_expected_and_received(self):
        result = self.run_check(json.dumps({**self.healthy(), 'schema_version': CURRENT_SCHEMA - 1}),
                                '--require-tenders', '--explain')
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'Schema mismatch: expected {CURRENT_SCHEMA}, received {CURRENT_SCHEMA - 1}.', result.stderr)
        self.assertNotIn('Release mismatch', result.stderr)

    def test_non_json_and_non_object_responses_do_not_leak_body(self):
        for body in ('<html>private-test-credential /home/private/path</html>',
                     json.dumps(['private-test-credential'])):
            result = self.run_check(body, '--require-tenders', '--explain')
            self.assertEqual(result.returncode, 1)
            self.assertIn('Health response is not', result.stderr)
            self.assertNotIn('private-test-credential', result.stdout + result.stderr)
            self.assertNotIn('/home/private/path', result.stdout + result.stderr)
            self.assertNotIn('<html>', result.stdout + result.stderr)

    def test_json_diagnostics_only_echo_safe_fields_and_check_names(self):
        secret = 'private-test-credential'
        response = {**self.healthy(), 'status': secret, 'release': secret,
                    'schema_version': {'secret': secret}, 'error': secret,
                    'checks': {'tenders': secret, 'opportunities': 'ok', 'timezones': 'ok', 'sqlite': 'ok',
                               secret: secret}}
        result = self.run_check(json.dumps(response), '--require-tenders', '--explain')
        self.assertEqual(result.returncode, 1)
        self.assertIn('received missing or invalid', result.stderr)
        self.assertIn('Required checks are not ready: tenders.', result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_explain_does_not_add_output_or_change_success_gate(self):
        result = self.run_check(json.dumps(self.healthy()), '--require-tenders', '--explain')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout + result.stderr, '')


if __name__ == '__main__':
    unittest.main()
