"""Check uploaded application bytes before installation or Passenger restart.

This utility uses only the standard library and never imports application code,
opens a database, or reads host configuration. Create the manifest after both
frontends are built, then send it to ``verify`` through standard input over SSH.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile


FORMAT = 1
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_FILES = 5000
STATIC_SUFFIXES = {'.html', '.css', '.js', '.mjs', '.json', '.map', '.svg', '.png',
                   '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.woff', '.woff2',
                   '.ttf', '.otf', '.wasm', '.txt', '.xml', '.webmanifest'}
REQUIRED_FILES = {
    'app.py', 'requirements.txt', 'conest_app/__init__.py',
    'conest_app/wsgi_runtime.py', 'assets/index.html', 'tenders_web/index.html',
    'tools/install_runtime.sh', 'tools/select_python.py', 'tools/check_runtime.py',
    'tools/install_security_rules.py', 'tools/install_wsgi_runtime.py',
    'tools/check_uploaded_release.py',
}
# Standalone deployment checker: keep this explicit allowlist aligned with
# conest_app/browser_ocr_assets.py. Do not generally allow .gz backups.
OCR_BUILD_FILES = {'tenders_web/assets/ocr-v6.0.1/' + name for name in (
    'tesseract.min.js', 'worker.min.js', 'tesseract-core-lstm.wasm.js',
    'tesseract-core-simd-lstm.wasm.js', 'tesseract-core-lstm.wasm',
    'tesseract-core-simd-lstm.wasm', 'eng.traineddata.gz', 'tesseract-LICENSE.txt',
    'core-LICENSE.txt', 'tesseract.min.js.LICENSE.txt', 'worker.min.js.LICENSE.txt', 'NOTICE.txt',
)}
OCR_SOURCE = 'conest_app/browser_ocr_assets.py'
VERSION_PATTERN = re.compile(r'[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}')


class ReleaseCheckError(ValueError):
    """A safe diagnostic that contains no file contents or host configuration."""


def allowed_path(name):
    if not isinstance(name, str) or not 1 <= len(name) <= 300:
        return False
    if name == 'assets/.htaccess':
        return True
    parts = PurePosixPath(name).parts
    if not parts or '/'.join(parts) != name:
        return False
    if any(not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@+-]*', part)
           or part == '__pycache__' for part in parts):
        return False
    if name in ('app.py', 'requirements.txt'):
        return True
    if len(parts) < 2:
        return False
    if name in OCR_BUILD_FILES:
        return True
    suffix = PurePosixPath(name).suffix.lower()
    if parts[0] == 'conest_app':
        return suffix == '.py'
    if parts[0] == 'tools':
        return len(parts) == 2 and suffix in ('.py', '.sh')
    return parts[0] in ('assets', 'tenders_web') and suffix in STATIC_SUFFIXES


def _root(path):
    try:
        root = Path(path).resolve(strict=True)
    except (OSError, RuntimeError):
        raise ReleaseCheckError('Application root is missing or unreadable.') from None
    if not root.is_dir():
        raise ReleaseCheckError('Application root is not a directory.')
    return root


def _safe_file(root, name):
    if not allowed_path(name):
        raise ReleaseCheckError('Manifest contains an unsafe or unsupported release path.')
    try:
        path = (root / name).resolve(strict=True)
        target = path.relative_to(root).as_posix()
    except FileNotFoundError:
        raise ReleaseCheckError('Missing release file: ' + name + '.') from None
    except (OSError, RuntimeError, ValueError):
        raise ReleaseCheckError('Unsafe release file target: ' + name + '.') from None
    # A harmless-looking asset symlink must not expose .env/data/private files,
    # even when its target is still inside the application directory.
    if not allowed_path(target) or not path.is_file():
        raise ReleaseCheckError('Unsafe release file target: ' + name + '.')
    return path


def _digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _release(root):
    path = _safe_file(root, 'conest_app/__init__.py')
    try:
        with path.open('rb') as stream:
            source = stream.read(65537)
        if len(source) > 65536:
            raise ValueError()
        tree = ast.parse(source, filename='conest_app/__init__.py')
        values = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == '__version__'
                    for target in node.targets):
                values.append(node.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == '__version__':
                values.append(node.value)
        if (len(values) != 1 or not isinstance(values[0], ast.Constant)
                or not isinstance(values[0].value, str)
                or not VERSION_PATTERN.fullmatch(values[0].value)):
            raise ValueError()
        return values[0].value
    except (SyntaxError, ValueError, UnicodeError, RecursionError):
        raise ReleaseCheckError('Application version must be one literal numeric version assignment.') from None


def create_manifest(root):
    root = _root(root)
    names = {'app.py', 'requirements.txt'}
    for folder in ('conest_app', 'assets', 'tenders_web', 'tools'):
        base = root / folder
        if base.is_symlink():
            raise ReleaseCheckError('Release directories must not be symbolic links.')
        if not base.exists():
            continue
        for current, directories, filenames in os.walk(base, followlinks=False):
            directories[:] = sorted(name for name in directories
                                     if not name.startswith('.') and name not in ('__pycache__', 'node_modules'))
            if any((Path(current) / name).is_symlink() for name in directories):
                raise ReleaseCheckError('Release directories must not be symbolic links.')
            if folder == 'tools':
                directories[:] = []
            for filename in filenames:
                name = (Path(current) / filename).relative_to(root).as_posix()
                if allowed_path(name):
                    names.add(name)
    required = REQUIRED_FILES | (OCR_BUILD_FILES if OCR_SOURCE in names else set())
    missing = required - names
    if missing:
        raise ReleaseCheckError('Build or source files are missing: ' + ', '.join(sorted(missing)) + '.')
    if len(names) > MAX_FILES:
        raise ReleaseCheckError('Release contains too many files for a manifest.')
    paths = {name: _safe_file(root, name) for name in sorted(names)}
    return {'format': FORMAT, 'release': _release(root),
            'files': {name: _digest(path) for name, path in paths.items()}}


def _validate_manifest(manifest):
    if (not isinstance(manifest, dict) or set(manifest) != {'format', 'release', 'files'}
            or type(manifest['format']) is not int or manifest['format'] != FORMAT
            or not isinstance(manifest['release'], str)
            or not VERSION_PATTERN.fullmatch(manifest['release'])
            or not isinstance(manifest['files'], dict)
            or not 1 <= len(manifest['files']) <= MAX_FILES):
        raise ReleaseCheckError('Invalid uploaded-release manifest.')
    for name, digest in manifest['files'].items():
        if not allowed_path(name):
            raise ReleaseCheckError('Manifest contains an unsafe or unsupported release path.')
        if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise ReleaseCheckError('Manifest contains an invalid file hash.')
    required = REQUIRED_FILES | (OCR_BUILD_FILES if OCR_SOURCE in manifest['files'] else set())
    if not required.issubset(manifest['files']):
        raise ReleaseCheckError('Manifest omits required release files.')


def verify_manifest(root, manifest):
    _validate_manifest(manifest)
    root = _root(root)
    problems = []
    for name, expected in sorted(manifest['files'].items()):
        try:
            if _digest(_safe_file(root, name)) != expected:
                problems.append('Changed release file: ' + name + '.')
        except ReleaseCheckError as exc:
            problems.append(str(exc))
    if problems:
        extra = ' Additional mismatches: ' + str(len(problems) - 8) + '.' if len(problems) > 8 else ''
        raise ReleaseCheckError('Uploaded files do not match release ' + manifest['release'] + '. '
                                + ' '.join(problems[:8]) + extra)
    actual = _release(root)
    if actual != manifest['release']:
        raise ReleaseCheckError('Uploaded version mismatch: expected ' + manifest['release']
                                + ', received ' + actual + '.')
    return actual, len(manifest['files'])


def write_manifest(root, output):
    root = _root(root)
    output = Path(output)
    if output.is_symlink():
        raise ReleaseCheckError('Manifest output must not be a symbolic link.')
    try:
        output = output.resolve()
    except (OSError, RuntimeError):
        raise ReleaseCheckError('Manifest output path is unavailable or unsafe.') from None
    if output == root or root in output.parents:
        raise ReleaseCheckError('Manifest output must be outside the application directory.')
    if output.suffix.lower() != '.json' or not output.parent.is_dir():
        raise ReleaseCheckError('Manifest output must be a JSON file in an existing external directory.')
    manifest = create_manifest(root)
    descriptor, temporary = tempfile.mkstemp(prefix='.tec-release-', dir=output.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(manifest, stream, sort_keys=True, indent=2)
            stream.write('\n')
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return manifest


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseCheckError('Duplicate manifest keys are not allowed.')
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create', help='Create a release manifest after building both frontends')
    create.add_argument('--root', type=Path, required=True)
    create.add_argument('--output', type=Path, required=True)
    verify = commands.add_parser('verify', help='Verify uploaded files against a manifest on stdin')
    verify.add_argument('--root', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'create':
            manifest = write_manifest(args.root, args.output)
            print('Created manifest for release ' + manifest['release'] + ' (' + str(len(manifest['files'])) + ' files).')
        else:
            raw = sys.stdin.buffer.read(MAX_MANIFEST_BYTES + 1)
            if len(raw) > MAX_MANIFEST_BYTES:
                raise ReleaseCheckError('Uploaded-release manifest exceeds the size limit.')
            try:
                manifest = json.loads(raw, object_pairs_hook=_unique_object)
            except (ValueError, UnicodeError, RecursionError):
                raise ReleaseCheckError('Uploaded-release manifest is not valid JSON.') from None
            release, count = verify_manifest(args.root, manifest)
            print('Uploaded release ' + release + ' verified (' + str(count) + ' files).')
    except ReleaseCheckError as exc:
        print('Upload verification failed: ' + str(exc), file=sys.stderr)
        return 1
    except OSError:
        print('Upload verification failed: a release file is unreadable or the manifest output is unavailable.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
