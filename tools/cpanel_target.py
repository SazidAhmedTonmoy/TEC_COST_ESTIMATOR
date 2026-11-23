"""Resolve one existing TEC Flow Passenger app before uploading or restarting.

May be piped to ``ssh ... python3 - --site-url URL --action inspect``. Only
cPanel's local read-only APIs and the selected app's Apache directives are
inspected. Database files, environment files and configuration contents are
never printed or changed.
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit


class TargetError(RuntimeError):
    pass


_DIRECTIVES = {
    'passengerapproot', 'passengerrestartdir', 'passengerstartupfile',
    'passengerpython',
}


def _account():
    account = pwd.getpwuid(os.geteuid())
    return account.pw_uid, Path(account.pw_dir).resolve(), account.pw_name


def _site(site_url):
    try:
        parsed = urlsplit(site_url)
        host = (parsed.hostname or '').lower().rstrip('.')
        parsed.port  # Reject malformed ports without printing the URL.
    except ValueError as exc:
        raise TargetError('CPANEL_SITE_URL is not a valid website URL.') from exc
    if (parsed.scheme not in ('http', 'https') or not host or
            not re.fullmatch(r'[a-z0-9.-]+', host) or '..' in host or
            parsed.username is not None or parsed.password is not None or
            parsed.query or parsed.fragment or parsed.path not in ('', '/')):
        raise TargetError('CPANEL_SITE_URL must be the website root URL, without credentials or query parameters.')
    return host


def _uapi(module, function, username, **parameters):
    fixed = Path('/usr/local/cpanel/bin/uapi')
    executable = str(fixed) if fixed.is_file() and os.access(fixed, os.X_OK) else shutil.which('uapi')
    if not executable:
        return None
    command = [executable, '--user=' + username, '--output=json', module, function]
    command.extend('{}={}'.format(key, value) for key, value in parameters.items())
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=20, check=False)
        if completed.returncode or len(completed.stdout) > 2 * 1024 * 1024:
            return None
        result = json.loads(completed.stdout).get('result')
        if not isinstance(result, dict) or result.get('status') != 1:
            return None
        return result.get('data')
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
        # UAPI output can include envvars and account information. Never expose it.
        return None


def _absolute(value, label):
    if (not isinstance(value, str) or not value or
            any(ord(char) < 32 for char in value) or '$' in value or '%{' in value or '~' in value):
        raise TargetError('{} must contain a literal filesystem path.'.format(label))
    path = Path(value)
    if not path.is_absolute():
        raise TargetError('{} must be an absolute path.'.format(label))
    return path.resolve()


def _owned_directory(path, home, uid, allow_home=False, must_exist=True):
    if path == Path('/') or (path == home and not allow_home) or home not in (path, *path.parents):
        raise TargetError('The application and restart directories must be specific folders inside the cPanel account home.')
    ancestor = path
    while not ancestor.exists() and ancestor != home:
        ancestor = ancestor.parent
    if not ancestor.is_dir() or ancestor.stat().st_uid != uid:
        raise TargetError('The selected folder is not owned by the current cPanel account.')
    if must_exist and not path.is_dir():
        raise TargetError('The configured application directory does not exist.')


def _config(path, home, uid):
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file() or path.stat().st_uid != uid:
        raise TargetError('Cannot safely inspect the selected .htaccess file.')
    _owned_directory(path.parent.resolve(), home, uid, allow_home=True)
    if path.stat().st_size > 1024 * 1024:
        raise TargetError('The selected .htaccess is too large to inspect safely.')
    found, scopes = {}, []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if stripped.startswith('<'):
            if stripped.startswith('</'):
                if scopes:
                    scopes.pop()
            else:
                # Passenger directives in other conditional/directory scopes
                # cannot be interpreted as unconditional hosting configuration.
                safe_scope = bool(re.fullmatch(
                    r'<IfModule\s+(?:mod_passenger\.c|passenger_module)\s*>',
                    stripped, re.IGNORECASE))
                scopes.append(safe_scope)
            continue
        directive = stripped.split(None, 1)[0].lower()
        if directive not in _DIRECTIVES:
            continue
        if scopes and not all(scopes):
            raise TargetError('Passenger directives use an unsupported conditional scope in .htaccess.')
        try:
            parts = shlex.split(stripped, comments=True)
        except ValueError as exc:
            raise TargetError('A Passenger directive has invalid quoting in .htaccess.') from exc
        if len(parts) != 2 or not parts[1] or any(ord(c) < 32 for c in parts[1]):
            raise TargetError('A Passenger directive must contain one literal path in .htaccess.')
        if any(token in parts[1] for token in ('$', '%{', '~')):
            raise TargetError('Dynamic Passenger paths cannot be resolved safely.')
        if directive in found and found[directive] != parts[1]:
            raise TargetError('Conflicting Passenger directives were found in .htaccess.')
        found[directive] = parts[1]
    return found


def _registered_root(data, host):
    if not isinstance(data, dict):
        return None
    matches = [entry for entry in data.values() if isinstance(entry, dict)
               and str(entry.get('domain', '')).lower().rstrip('.') == host
               and entry.get('base_uri') in ('', '/')
               and entry.get('enabled') in (1, '1')]
    if len(matches) > 1:
        raise TargetError('More than one enabled Passenger application matches CPANEL_SITE_URL.')
    return _absolute(matches[0].get('path'), 'The registered Passenger application root') if matches else None


def resolve_target(site_url, root=None):
    """Return a safe deployment target without making filesystem changes."""
    uid, home, username = _account()
    host = _site(site_url)
    explicit = _absolute(root, 'CPANEL_DEPLOY_PATH') if root else None
    registered = _registered_root(_uapi('PassengerApps', 'list_applications', username), host)
    domain_data = _uapi('DomainInfo', 'single_domain_data', username, domain=host)
    configs, document_root = [], None
    if isinstance(domain_data, dict) and domain_data.get('documentroot'):
        domain = domain_data.get('servername') or domain_data.get('domain')
        if domain and str(domain).lower().rstrip('.') != host:
            raise TargetError('cPanel returned domain metadata for a different website.')
        if domain:
            document_root = _absolute(domain_data['documentroot'], 'The domain document root')
            _owned_directory(document_root, home, uid, allow_home=True)
            config_path = document_root / '.htaccess'
            configs.append((config_path, _config(config_path, home, uid)))
    configured = None
    if configs and configs[0][1].get('passengerapproot'):
        configured = _absolute(configs[0][1]['passengerapproot'], 'PassengerAppRoot')
    roots = [path for path in (registered, configured, explicit) if path is not None]
    if not roots:
        raise TargetError('Cannot verify the Passenger application root. Set CPANEL_DEPLOY_PATH to the exact application root shown in cPanel.')
    if len(set(roots)) != 1:
        raise TargetError('CPANEL_DEPLOY_PATH and the website\'s Passenger application root do not match. No files were changed.')
    selected = roots[0]
    _owned_directory(selected, home, uid)
    if (selected / 'conest_app').is_symlink():
        raise TargetError('The selected application package must be inside the application root.')
    for relative in ('app.py', 'conest_app/__init__.py'):
        marker = selected / relative
        if marker.is_symlink() or not marker.is_file() or marker.stat().st_uid != uid:
            raise TargetError('The selected application root is not an existing TEC Flow installation.')
    root_config = selected / '.htaccess'
    if all(path != root_config for path, settings in configs):
        configs.append((root_config, _config(root_config, home, uid)))
    restart_dirs, startup_files, interpreters = set(), set(), set()
    for config_path, settings in configs:
        if settings.get('passengerapproot') and _absolute(settings['passengerapproot'], 'PassengerAppRoot') != selected:
            raise TargetError('PassengerAppRoot conflicts with the selected application root. No files were changed.')
        if settings.get('passengerrestartdir'):
            restart_dirs.add((selected / settings['passengerrestartdir']).resolve())
        if settings.get('passengerstartupfile'):
            startup_files.add((selected / settings['passengerstartupfile']).resolve())
        if settings.get('passengerpython'):
            # Retain a virtualenv's interpreter path even when it is a symlink.
            value = settings['passengerpython']
            if not Path(value).is_absolute():
                raise TargetError('PassengerPython must be an absolute interpreter path.')
            interpreters.add(os.path.abspath(value))
    if len(restart_dirs) > 1 or len(startup_files) > 1 or len(interpreters) > 1:
        raise TargetError('The domain and application Passenger configuration conflict. No files were changed.')
    startup = selected / 'passenger_wsgi.py'
    if startup_files and next(iter(startup_files)) != startup:
        raise TargetError('PassengerStartupFile is not passenger_wsgi.py; this deployment cannot safely update that custom startup file.')
    if startup.is_symlink() or (startup.exists() and (not startup.is_file() or startup.stat().st_uid != uid)):
        raise TargetError('The Passenger startup file must be a regular file owned by this cPanel account.')
    restart_dir = next(iter(restart_dirs), (selected / 'tmp').resolve())
    _owned_directory(restart_dir, home, uid, must_exist=False)
    restart_file = restart_dir / 'restart.txt'
    if restart_file.is_symlink() or (restart_file.exists() and (
            not restart_file.is_file() or restart_file.stat().st_uid != uid)):
        raise TargetError('The Passenger restart marker must be a regular file owned by this cPanel account.')
    output = {'root': str(selected), 'restart_dir': str(restart_dir),
              'detection': 'passenger_apps' if registered else 'domain_htaccess' if configured else 'explicit',
              'startup_file': str(startup)}
    present_configs = [str(path) for path, settings in configs if settings]
    if present_configs:
        output['config_path'] = present_configs[0]
        output['hosting_config_paths'] = present_configs
    if document_root is not None:
        output['document_root'] = str(document_root)
    if interpreters:
        output['passenger_python'] = next(iter(interpreters))
    return output


def rsync_filter_rules(target, managed_files):
    """Protect inspected host paths without hiding release-managed descendants.

    Run locally with the remote inspection result and the release manifest's
    file names. No local path is resolved against the remote filesystem.
    """
    def absolute(value):
        if (not isinstance(value, str) or not value or
                any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise TargetError('Invalid host path in the deployment target.')
        path = PurePosixPath(value)
        if not path.is_absolute() or '..' in path.parts or str(path) != value:
            raise TargetError('Host paths must be canonical absolute paths.')
        return path

    root = absolute(target.get('root'))
    if root == PurePosixPath('/'):
        raise TargetError('Cannot protect paths for an unscoped application root.')
    managed = set()
    for name in managed_files:
        if (not isinstance(name, str) or not name or
                any(ord(char) < 32 or ord(char) == 127 for char in name)):
            raise TargetError('Invalid managed path in the release manifest.')
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name or name == '.':
            raise TargetError('Invalid managed path in the release manifest.')
        managed.add(name)

    def relative(path):
        try:
            result = path.relative_to(root)
        except ValueError:
            return None
        return None if result == PurePosixPath('.') else result.as_posix()

    excluded, directories = set(), set()

    def directory(path):
        name = relative(path)
        while name:
            if name in managed:
                raise TargetError('A hosting directory overlaps a release-managed file: ' + name + '.')
            directories.add(name)
            path = path.parent
            name = relative(path)

    def host_file(path):
        name = relative(path)
        if name is None:
            return
        if name in managed or any(item.startswith(name + '/') for item in managed):
            raise TargetError('A hosting configuration or restart marker overlaps a release-managed file: ' + name + '.')
        excluded.add(name)
        directory(path.parent)

    host_file(root / '.htaccess')
    known_configs = target.get('hosting_config_paths', [])
    if not isinstance(known_configs, list):
        raise TargetError('Invalid hosting configuration paths in the deployment target.')
    known_configs = {absolute(value) for value in known_configs}
    if target.get('config_path'):
        known_configs.add(absolute(target['config_path']))
    for path in known_configs:
        host_file(path)
    if target.get('document_root'):
        document_root = absolute(target['document_root'])
        directory(document_root)
        config = document_root / '.htaccess'
        # assets/.htaccess is a managed security file. Preserve it as host
        # configuration only when inspection found actual Passenger directives.
        if relative(config) not in managed or config in known_configs:
            host_file(config)
    restart_dir = absolute(target.get('restart_dir'))
    directory(restart_dir)
    host_file(restart_dir / 'restart.txt')

    def pattern(name):
        # rsync interprets backslashes as escapes only in wildcard patterns.
        # Escape literal wildcard characters without broadening host protection.
        if any(char in name for char in '*?['):
            name = name.replace('\\', '\\\\')
            for char in '*?[':
                name = name.replace(char, '\\' + char)
        return '/' + name

    return (['- ' + pattern(name) for name in sorted(excluded)] +
            ['P ' + pattern(name) + '/' for name in sorted(directories)])


def restart_target(site_url, root):
    if not root:
        raise TargetError('Restart requires the application root verified before upload.')
    target = resolve_target(site_url, root)
    directory = Path(target['restart_dir'])
    missing, parent = [], directory
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for path in reversed(missing):
        try:
            path.mkdir(mode=0o755)
        except FileExistsError:
            pass
        else:
            # Apache's supervisor may use a different uid. Only new, empty
            # restart directories are made traversable; host permissions stay.
            path.chmod(0o755)
    marker = directory / 'restart.txt'
    flags = os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(str(marker), flags | os.O_CREAT | os.O_EXCL, 0o644)
        created = True
    except FileExistsError:
        descriptor = os.open(str(marker), flags)
        created = False
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid():
            raise TargetError('The Passenger restart marker is not a safe regular file.')
        if created:
            os.fchmod(descriptor, 0o644)
        now = time.time_ns()
        # Passenger can compare timestamps at whole-second resolution. Ensure
        # even an immediate retry changes the observed marker timestamp.
        modified = max(now, before.st_mtime_ns) + 1_000_000_000
        os.utime(descriptor, ns=(now, modified))
    finally:
        os.close(descriptor)
    target['restart_requested'] = True
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site-url', required=True)
    parser.add_argument('--root')
    parser.add_argument('--action', choices=('inspect', 'restart'), default='inspect')
    args = parser.parse_args(argv)
    try:
        result = (restart_target(args.site_url, args.root) if args.action == 'restart'
                  else resolve_target(args.site_url, args.root))
    except TargetError as exc:
        parser.exit(1, 'Deployment target: {}\n'.format(exc))
    except (OSError, RuntimeError):
        parser.exit(1, 'Deployment target: a required application file or folder could not be accessed safely.\n')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
