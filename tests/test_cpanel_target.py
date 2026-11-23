"""Deployment discovery must never guess or restart a different application."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock


TOOL = Path(__file__).resolve().parents[1] / 'tools' / 'cpanel_target.py'
SPEC = importlib.util.spec_from_file_location('cpanel_target', TOOL)
target = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(target)


class CpanelTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.root = self.make_app('old-domain.example')
        self.docroot = self.home / 'public-domain'
        self.docroot.mkdir()
        self.site = 'https://tec-flow.example/'
        self.responses = {}
        self.account = mock.patch.object(target, '_account', return_value=(os.geteuid(), self.home, 'cpaneluser'))
        self.account.start()
        self.addCleanup(self.account.stop)
        self.api = mock.patch.object(target, '_uapi', side_effect=self.api_response)
        self.api.start()
        self.addCleanup(self.api.stop)

    def make_app(self, name):
        path = self.home / name
        path.mkdir()
        (path / 'conest_app').mkdir()
        (path / 'app.py').write_text('# Existing app\n')
        (path / 'conest_app' / '__init__.py').write_text('__version__ = "3.8.6"\n')
        (path / 'passenger_wsgi.py').write_text('# Existing host bootstrap\n')
        return path

    def api_response(self, module, function, username, **parameters):
        self.assertEqual(username, 'cpaneluser')
        if module == 'DomainInfo':
            self.assertEqual(function, 'single_domain_data')
            self.assertEqual(parameters, {'domain': 'tec-flow.example'})
        return self.responses.get(module)

    def registration(self, **changes):
        entry = {'domain': 'tec-flow.example', 'base_uri': '/', 'enabled': 1,
                 'path': str(self.root), 'envvars': {'SECRET': 'private-value'}}
        entry.update(changes)
        return entry

    def domain_config(self, source=None):
        self.responses['DomainInfo'] = {'servername': 'tec-flow.example', 'documentroot': str(self.docroot)}
        if source is None:
            source = 'PassengerAppRoot "{}"\n'.format(self.root)
        (self.docroot / '.htaccess').write_text(source)

    def snapshot(self):
        return {str(path.relative_to(self.home)): (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
                for path in self.home.rglob('*')}

    def test_registered_app_selects_actual_path_and_keeps_private_fields_private(self):
        self.responses['PassengerApps'] = {'TEC': self.registration()}
        result = target.resolve_target(self.site)
        self.assertEqual(result['root'], str(self.root))
        self.assertEqual(result['detection'], 'passenger_apps')
        self.assertNotIn('private-value', json.dumps(result))
        self.assertNotIn('envvars', json.dumps(result))

    def test_registration_match_is_exact_enabled_domain_and_root_uri(self):
        self.responses['PassengerApps'] = {
            'other-site': self.registration(domain='other.example'),
            'sub-app': self.registration(base_uri='/other'),
            'disabled': self.registration(enabled=0),
            'TEC': self.registration(),
        }
        self.assertEqual(target.resolve_target(self.site)['root'], str(self.root))

    def test_ambiguous_registrations_are_rejected(self):
        self.responses['PassengerApps'] = {'one': self.registration(), 'two': self.registration()}
        with self.assertRaisesRegex(target.TargetError, 'More than one'):
            target.resolve_target(self.site, str(self.root))

    def test_authoritative_sources_must_agree(self):
        self.responses['PassengerApps'] = {'TEC': self.registration()}
        other = self.make_app('different-app')
        self.domain_config('PassengerAppRoot "{}"\n'.format(other))
        with self.assertRaisesRegex(target.TargetError, 'do not match'):
            target.resolve_target(self.site)

    def test_document_root_passenger_directives_resolve_custom_paths(self):
        self.domain_config('<IfModule mod_passenger.c>\n'
                           'PassengerAppRoot "{}"\n'
                           'PassengerRestartDir "../restart-area/tec"\n'
                           'PassengerStartupFile passenger_wsgi.py\n'
                           'PassengerPython "/home/cpaneluser/virtualenv/tec/bin/python"\n'
                           '</IfModule>\n'.format(self.root))
        result = target.resolve_target(self.site, '')
        self.assertEqual(result['root'], str(self.root))
        self.assertEqual(result['restart_dir'], str(self.home / 'restart-area/tec'))
        self.assertEqual(result['detection'], 'domain_htaccess')
        self.assertEqual(result['passenger_python'], '/home/cpaneluser/virtualenv/tec/bin/python')
        self.assertEqual(result['document_root'], str(self.docroot))
        self.assertEqual(result['hosting_config_paths'], [str(self.docroot / '.htaccess')])

    def test_inspect_makes_no_changes_even_when_restart_folder_is_missing(self):
        self.domain_config()
        before = self.snapshot()
        target.resolve_target(self.site)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / 'tmp').exists())

    def test_explicit_fallback_is_allowed_for_an_existing_app(self):
        result = target.resolve_target(self.site, str(self.root))
        self.assertEqual(result['detection'], 'explicit')
        self.assertEqual(result['restart_dir'], str(self.root / 'tmp'))
        self.assertNotIn('passenger_python', result)

    def test_document_root_is_not_assumed_to_be_application_root(self):
        self.responses['DomainInfo'] = {'servername': 'tec-flow.example', 'documentroot': str(self.root)}
        with self.assertRaisesRegex(target.TargetError, 'Set CPANEL_DEPLOY_PATH'):
            target.resolve_target(self.site)

    def test_missing_discovery_requires_explicit_root(self):
        with self.assertRaisesRegex(target.TargetError, 'Set CPANEL_DEPLOY_PATH'):
            target.resolve_target(self.site, '')

    def test_wrong_root_cannot_modify_or_restart_either_application(self):
        self.domain_config()
        other = self.make_app('wrong-app')
        before = self.snapshot()
        with self.assertRaisesRegex(target.TargetError, 'do not match'):
            target.restart_target(self.site, str(other))
        self.assertEqual(self.snapshot(), before)

    def test_restart_revalidates_and_touches_only_the_configured_marker(self):
        restart = self.home / 'restart-area' / 'tec'
        self.domain_config('PassengerAppRoot "{}"\nPassengerRestartDir "{}"\n'.format(self.root, restart))
        result = target.restart_target(self.site, str(self.root))
        self.assertTrue(result['restart_requested'])
        marker = restart / 'restart.txt'
        self.assertTrue(marker.is_file())
        self.assertFalse((self.root / 'tmp').exists())
        marker.write_text('Keep existing marker contents.')
        before = int(marker.stat().st_mtime)
        target.restart_target(self.site, str(self.root))
        self.assertGreater(int(marker.stat().st_mtime), before)
        self.assertEqual(marker.read_text(), 'Keep existing marker contents.')

    def test_restart_with_explicit_fallback_uses_app_tmp(self):
        target.restart_target(self.site, str(self.root))
        self.assertTrue((self.root / 'tmp' / 'restart.txt').is_file())

    def test_new_restart_marker_is_readable_by_apache_without_changing_host_permissions(self):
        previous_umask = os.umask(0o077)
        try:
            target.restart_target(self.site, str(self.root))
        finally:
            os.umask(previous_umask)
        directory = self.root / 'tmp'
        marker = directory / 'restart.txt'
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o644)
        directory.chmod(0o750)
        marker.chmod(0o640)
        target.restart_target(self.site, str(self.root))
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o750)
        self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o640)

    def test_restart_requires_the_previously_verified_root(self):
        self.domain_config()
        before = self.snapshot()
        with self.assertRaisesRegex(target.TargetError, 'requires'):
            target.restart_target(self.site, None)
        self.assertEqual(self.snapshot(), before)

    def test_domain_identity_mismatch_is_rejected(self):
        self.responses['DomainInfo'] = {'servername': 'other.example', 'documentroot': str(self.root)}
        with self.assertRaisesRegex(target.TargetError, 'different website'):
            target.resolve_target(self.site, str(self.root))

    def test_conflicting_root_config_is_rejected(self):
        self.domain_config('PassengerAppRoot "{}"\nPassengerRestartDir first\n'.format(self.root))
        (self.root / '.htaccess').write_text('PassengerRestartDir second\n')
        with self.assertRaisesRegex(target.TargetError, 'configuration conflict'):
            target.resolve_target(self.site)

    def test_ambiguous_conditional_or_dynamic_directives_are_rejected(self):
        for source in (
                'PassengerAppRoot "{}"\nPassengerAppRoot "{}"\n'.format(self.root, self.home / 'other'),
                '<If "condition">\nPassengerAppRoot "{}"\n</If>\n'.format(self.root),
                'PassengerAppRoot "${SECRET}"\n',
                'PassengerAppRoot "unterminated\n'):
            with self.subTest(source=source):
                self.domain_config(source)
                with self.assertRaises(target.TargetError):
                    target.resolve_target(self.site, str(self.root))

    def test_unsafe_roots_are_rejected(self):
        for root in ('/', str(self.home), str(self.home.parent), 'relative'):
            with self.subTest(root=root), self.assertRaises(target.TargetError):
                target.resolve_target(self.site, root)

    def test_missing_app_markers_are_rejected(self):
        (self.root / 'conest_app' / '__init__.py').unlink()
        with self.assertRaisesRegex(target.TargetError, 'not an existing TEC Flow'):
            target.resolve_target(self.site, str(self.root))

    def test_custom_or_symlink_startup_is_rejected_without_writes(self):
        (self.root / '.htaccess').write_text('PassengerStartupFile custom.py\n')
        before = self.snapshot()
        with self.assertRaisesRegex(target.TargetError, 'custom startup'):
            target.restart_target(self.site, str(self.root))
        self.assertEqual(self.snapshot(), before)
        (self.root / '.htaccess').unlink()
        startup = self.root / 'passenger_wsgi.py'
        startup.unlink()
        startup.symlink_to(self.root / 'app.py')
        with self.assertRaisesRegex(target.TargetError, 'startup file'):
            target.resolve_target(self.site, str(self.root))

    def test_symlink_restart_marker_is_rejected_without_touching_target(self):
        (self.root / 'tmp').mkdir()
        victim = self.home / 'unrelated.txt'
        victim.write_text('Unchanged')
        (self.root / 'tmp' / 'restart.txt').symlink_to(victim)
        modified = victim.stat().st_mtime_ns
        with self.assertRaisesRegex(target.TargetError, 'restart marker'):
            target.restart_target(self.site, str(self.root))
        self.assertEqual(victim.stat().st_mtime_ns, modified)
        self.assertEqual(victim.read_text(), 'Unchanged')

    def test_default_restart_directory_cannot_escape_account_home(self):
        (self.root / 'tmp').symlink_to(self.home.parent, target_is_directory=True)
        with self.assertRaisesRegex(target.TargetError, 'inside the cPanel account home'):
            target.resolve_target(self.site, str(self.root))

    def test_invalid_website_urls_are_rejected(self):
        for site in ('https://user:secret@tec-flow.example/', 'https://tec-flow.example/subapp',
                     'https://tec-flow.example/?secret=value', 'file:///tmp/app', 'https://tec-flow.example:bad'):
            with self.subTest(site=site), self.assertRaises(target.TargetError):
                target.resolve_target(site, str(self.root))

    def test_source_can_run_without_file_global_and_only_emits_safe_json(self):
        namespace = {'__name__': 'piped_helper'}
        exec(compile(TOOL.read_text(), '<stdin>', 'exec'), namespace)
        self.assertNotIn('__file__', namespace)
        namespace['_account'] = lambda: (os.geteuid(), self.home, 'cpaneluser')
        namespace['_uapi'] = lambda *args, **kwargs: None
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(namespace['main'](['--site-url', self.site, '--root', str(self.root), '--action', 'inspect']), 0)
        self.assertEqual(json.loads(output.getvalue())['root'], str(self.root))


class LocalUapiTests(unittest.TestCase):
    def call(self, stdout, returncode=0):
        completed = subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=b'PRIVATE_ERROR_VALUE')
        with mock.patch.object(Path, 'is_file', return_value=False), \
                mock.patch.object(target.shutil, 'which', return_value='/safe/uapi'), \
                mock.patch.object(target.subprocess, 'run', return_value=completed) as run:
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                result = target._uapi('DomainInfo', 'single_domain_data', 'account', domain='tec-flow.example')
            self.assertEqual(output.getvalue(), '')
            self.assertEqual(run.call_args[0][0], ['/safe/uapi', '--user=account', '--output=json',
                                                 'DomainInfo', 'single_domain_data', 'domain=tec-flow.example'])
            self.assertNotIn('shell', run.call_args[1])
            return result

    def test_valid_uapi_response_is_parsed_privately(self):
        data = {'servername': 'tec-flow.example', 'documentroot': '/home/account/public_html'}
        self.assertEqual(self.call(json.dumps({'result': {'status': 1, 'data': data}}).encode()), data)

    def test_invalid_or_failed_uapi_response_is_unavailable_without_disclosure(self):
        for payload in (b'PRIVATE_ERROR_VALUE', b'[]', b'{"result": null}',
                        b'{"result": {"status": 0, "errors": ["PRIVATE_ERROR_VALUE"]}}'):
            with self.subTest(payload=payload):
                self.assertIsNone(self.call(payload))
        self.assertIsNone(self.call(b'{"result": {"status": 1, "data": {}}}', returncode=1))


class RsyncProtectionTests(unittest.TestCase):
    def setUp(self):
        self.root = '/home/account/application'
        self.target = {'root': self.root, 'restart_dir': self.root + '/custom-restart',
                       'document_root': self.root + '/public',
                       'hosting_config_paths': [self.root + '/public/.htaccess']}
        self.managed = ['app.py', 'conest_app/__init__.py', 'assets/.htaccess', 'assets/index.html']

    def test_nested_documentroot_and_custom_restart_are_protected(self):
        rules = target.rsync_filter_rules(self.target, self.managed)
        self.assertEqual(rules, ['- /.htaccess', '- /custom-restart/restart.txt', '- /public/.htaccess',
                                 'P /custom-restart/', 'P /public/'])
        self.assertNotIn('- /assets/.htaccess', rules)

    def test_managed_descendants_remain_transferable(self):
        self.managed.append('public/current.js')
        rules = target.rsync_filter_rules(self.target, self.managed)
        self.assertIn('P /public/', rules)
        self.assertNotIn('- /public/', rules)
        self.assertFalse(any('current.js' in rule for rule in rules))

    def test_empty_nested_directories_and_their_parents_are_protected(self):
        self.target['document_root'] = self.root + '/web/public'
        self.target['hosting_config_paths'] = []
        self.target['restart_dir'] = self.root + '/run/passenger'
        rules = target.rsync_filter_rules(self.target, self.managed)
        self.assertIn('P /web/', rules)
        self.assertIn('P /web/public/', rules)
        self.assertIn('P /run/', rules)
        self.assertIn('P /run/passenger/', rules)

    def test_paths_outside_application_are_not_added_to_transfer_filters(self):
        self.target['document_root'] = '/home/account/public_html'
        self.target['hosting_config_paths'] = ['/home/account/public_html/.htaccess']
        self.target['restart_dir'] = '/home/account/restart-area'
        self.assertEqual(target.rsync_filter_rules(self.target, self.managed), ['- /.htaccess'])

    def test_root_documentroot_or_restart_does_not_protect_entire_release(self):
        self.target['document_root'] = self.root
        self.target['hosting_config_paths'] = [self.root + '/.htaccess']
        self.target['restart_dir'] = self.root
        self.assertEqual(target.rsync_filter_rules(self.target, self.managed), ['- /.htaccess', '- /restart.txt'])

    def test_managed_assets_security_rules_are_not_hidden(self):
        self.target['document_root'] = self.root + '/assets'
        self.target['hosting_config_paths'] = []
        rules = target.rsync_filter_rules(self.target, self.managed)
        self.assertIn('P /assets/', rules)
        self.assertNotIn('- /assets/.htaccess', rules)

    def test_actual_passenger_config_at_managed_assets_file_is_rejected(self):
        self.target['document_root'] = self.root + '/assets'
        self.target['hosting_config_paths'] = [self.root + '/assets/.htaccess']
        with self.assertRaisesRegex(target.TargetError, 'overlaps a release-managed file'):
            target.rsync_filter_rules(self.target, self.managed)

    def test_restart_marker_or_directory_overlapping_managed_file_is_rejected(self):
        with self.assertRaisesRegex(target.TargetError, 'overlaps a release-managed file'):
            target.rsync_filter_rules(self.target, self.managed + ['custom-restart/restart.txt'])
        self.target['restart_dir'] = self.root + '/app.py'
        with self.assertRaisesRegex(target.TargetError, 'directory overlaps'):
            target.rsync_filter_rules(self.target, self.managed)

    def test_literal_globs_and_backslashes_are_escaped_in_anchored_rules(self):
        self.target['document_root'] = self.root + '/public [copy]*?'
        self.target['hosting_config_paths'] = []
        self.target['restart_dir'] = self.root + r'/run\area'
        rules = target.rsync_filter_rules(self.target, self.managed)
        self.assertIn(r'- /public \[copy]\*\?/.htaccess', rules)
        self.assertIn(r'P /public \[copy]\*\?/', rules)
        self.assertIn(r'P /run\area/', rules)
        self.target['restart_dir'] = self.root + r'/run\area*'
        self.assertIn(r'P /run\\area\*/', target.rsync_filter_rules(self.target, self.managed))

    def test_noncanonical_paths_or_filter_injection_are_rejected(self):
        for value in ('/home/account/application/../outside', '/home/account/application/x\n- /***', 'relative'):
            with self.subTest(value=value):
                self.target['document_root'] = value
                with self.assertRaises(target.TargetError):
                    target.rsync_filter_rules(self.target, self.managed)


if __name__ == '__main__':
    unittest.main()
