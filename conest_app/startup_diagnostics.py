"""Bounded, private startup tracebacks, independent of databases and host stderr.

Only the authenticated administrator endpoint may return these records. The
public startup response gets a reference and a Boolean, never this content.
Capture fails closed on platforms without POSIX ownership/no-follow primitives.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import tempfile
import time
import traceback
import uuid

try:
    import fcntl
except ImportError:  # Owner-only POSIX permissions cannot be promised here.
    fcntl = None

from . import __version__


APP_ROOT = Path(__file__).resolve().parents[1]
MAX_RECORDS = 32
MAX_RECORD_BYTES = 64 * 1024
MAX_AGE_SECONDS = 7 * 24 * 60 * 60
_REFERENCE = re.compile(r'[a-f0-9]{12}\Z')
_RECORD = re.compile(r'[a-f0-9]{12}\.json\Z')
_TEMP = re.compile(r'\.tmp-[a-f0-9]{12}-[a-f0-9]{12}\Z')
_TRUNCATED = '\n... [diagnostic text truncated] ...\n'
_CREDENTIAL = re.compile(
    r'''(?ix)(\b(?:password|passwd|pwd|secret|api[_-]?key|(?:(?:access|refresh|csrf)[_-]?)?token|session[_-]?(?:id|token)|authorization|cookie)\b["']?\s*[:=]\s*)'''
    r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;\}\]&]+)''')
_AUTHORIZATION = re.compile(r'(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+')


def _candidate_directories():
    """Stable across Passenger workers; deliberately not request-configurable."""
    digest = hashlib.sha256(os.fsencode(str(APP_ROOT))).hexdigest()[:20]
    # Application parents and home folders may also be public document roots.
    # Temp storage is deliberately short lived; the authenticated route locates it.
    candidates = [Path(folder) / ('conest-private-logs-' + str(os.geteuid())) / digest
                  for folder in (tempfile.gettempdir(), '/tmp', '/var/tmp')]
    return tuple(dict.fromkeys(candidates))


def _outside_web_roots(path):
    roots = [APP_ROOT]
    for name in ('DOCUMENT_ROOT', 'CONTEXT_DOCUMENT_ROOT'):
        if os.environ.get(name):
            roots.append(Path(os.path.abspath(os.environ[name])))
    # Shared hosting does not always forward DOCUMENT_ROOT to Passenger.
    roots.extend(parent for parent in APP_ROOT.parents
                 if parent.name.lower() in {'public_html', 'htdocs', 'httpdocs', 'wwwroot'})
    return not any(path == root or root in path.parents for root in roots)


@contextmanager
def _directory(path, create=False):
    """Open by directory descriptors, rejecting symlinks in every component.

    The final two components are our private namespace and application folder.
    Existing unsafe permissions are rejected, never changed to make them work.
    """
    if fcntl is None or not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'geteuid'):
        raise OSError('Private diagnostic storage is unsupported on this platform')
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or len(path.parts) < 4 or not _outside_web_roots(path):
        raise OSError('Unsafe diagnostic location')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    descriptor = os.open(path.anchor, flags)
    try:
        for index, name in enumerate(path.parts[1:], start=1):
            private = index >= len(path.parts) - 2
            if create and private:
                try:
                    os.mkdir(name, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(name, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if private and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
                raise OSError('Diagnostic directory must be private and owned by this account')
        yield descriptor
    finally:
        os.close(descriptor)


def _private_file(info):
    return (stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and not stat.S_IMODE(info.st_mode) & 0o077 and info.st_nlink == 1)


@contextmanager
def _write_lock(directory):
    flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    descriptor = os.open('.lock', flags, 0o600, dir_fd=directory)
    try:
        if not _private_file(os.fstat(descriptor)):
            raise OSError('Unsafe diagnostic lock')
        deadline = time.monotonic() + 0.5
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Diagnostic storage is busy')
                time.sleep(0.01)
        yield
    finally:
        os.close(descriptor)  # Also releases the process-safe advisory lock.


def _files(directory):
    result = []
    for name in os.listdir(directory):
        if _RECORD.fullmatch(name):
            try:
                info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if _private_file(info):
                    result.append((info.st_mtime_ns, name, info))
            except OSError:
                pass
    return sorted(result, reverse=True)


def _cleanup(directory, keep):
    """Best effort retention under the write lock; return remaining file count."""
    records = _files(directory)
    remaining = len(records)
    cutoff = time.time() - MAX_AGE_SECONDS
    for index, (_modified, name, info) in enumerate(records):
        if index >= keep or info.st_mtime < cutoff or info.st_size > MAX_RECORD_BYTES:
            try:
                os.unlink(name, dir_fd=directory)
                remaining -= 1
            except OSError:
                pass
    # A crashed writer may leave a temporary file; no other writer holds this lock.
    for name in os.listdir(directory):
        if _TEMP.fullmatch(name):
            try:
                if _private_file(os.stat(name, dir_fd=directory, follow_symlinks=False)):
                    os.unlink(name, dir_fd=directory)
            except OSError:
                pass
    return remaining


def _clip(value, limit):
    text = str(value)
    encoded = text.encode('utf-8', errors='replace')
    if len(encoded) <= limit:
        return text, False
    available = max(0, limit - len(_TRUNCATED.encode()))
    if not available:
        return _TRUNCATED[:limit], True
    first = available // 3
    return (encoded[:first].decode('utf-8', errors='ignore') + _TRUNCATED +
            encoded[-(available - first):].decode('utf-8', errors='ignore')), True


def _redact(text):
    # Only explicit credential syntax: ordinary database paths and error text stay.
    text = _AUTHORIZATION.sub(lambda match: match.group(1) + ' [redacted]', text)
    return _CREDENTIAL.sub(lambda match: match.group(1) + '[redacted]', text)


def _runtime():
    """Mirror only the path expressions; never import/init/connect the stores."""
    account_config = os.environ.get('CONEST_DB_PATH', '')
    tender_config = os.environ.get('CONEST_TENDERS_DB_PATH', '')
    account_path = tender_path = 'Unavailable'
    try:
        account_path = (Path(account_config.strip()).expanduser().resolve()
                        if account_config.strip() else APP_ROOT / 'data' / 'conest_catalog.db')
        tender_path = Path(tender_config or account_path.parent / 'tec_tenders.db').resolve()
    except (OSError, RuntimeError, ValueError):
        pass
    return {
        'python_executable': sys.executable, 'python_version': sys.version,
        'sqlite_version': sqlite3.sqlite_version, 'release': __version__, 'pid': os.getpid(),
        'configured_db_path': account_config, 'effective_db_path': str(account_path),
        'configured_tenders_db_path': tender_config, 'effective_tenders_db_path': str(tender_path),
    }


def _encode_record(exc, code, reference):
    formatted = ''.join(traceback.TracebackException.from_exception(exc, capture_locals=False).format(chain=True))
    try:
        message = str(exc)
    except Exception:
        message = '(exception message unavailable)'
    record = {
        'reference': reference, 'code': str(code)[:80],
        'created_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
        'exception_type': type(exc).__module__ + '.' + type(exc).__qualname__,
        'exception_message': message, 'traceback': formatted,
        'truncated': False, 'runtime': _runtime(),
    }
    fields = [(record, 'traceback'), (record, 'exception_message'), (record, 'exception_type')]
    fields.extend((record['runtime'], key) for key, value in record['runtime'].items() if isinstance(value, str))
    for target, key in fields:
        target[key] = _redact(target[key])
        target[key], trimmed = _clip(target[key], MAX_RECORD_BYTES // 2)
        record['truncated'] |= trimmed
    payload = json.dumps(record, ensure_ascii=False).encode('utf-8', errors='replace')
    while len(payload) > MAX_RECORD_BYTES:
        target, key = max(fields, key=lambda item: len(item[0][item[1]].encode('utf-8', errors='replace')))
        target[key], _ = _clip(target[key], len(target[key].encode('utf-8', errors='replace')) // 2)
        record['truncated'] = True
        payload = json.dumps(record, ensure_ascii=False).encode('utf-8', errors='replace')
    return payload


def record_failure(exc, code, reference) -> bool:
    """Capture the original cause; every storage/formatting failure is nonfatal."""
    if not isinstance(reference, str) or not _REFERENCE.fullmatch(reference):
        return False
    try:
        payload = _encode_record(exc, code, reference)
        candidates = tuple(_candidate_directories())[:3]
        # Keep the total bounded even when concurrent workers need fallbacks.
        limit = max(1, MAX_RECORDS // max(1, len(candidates)))
        for candidate in candidates:
            try:
                with _directory(candidate, create=True) as directory, _write_lock(directory):
                    name = reference + '.json'
                    try:
                        os.stat(name, dir_fd=directory, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        continue  # Do not overwrite an existing reference or follow a link.
                    if _cleanup(directory, limit - 1) >= limit:
                        continue
                    temporary = '.tmp-' + reference + '-' + uuid.uuid4().hex[:12]
                    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
                    descriptor = os.open(temporary, flags, 0o600, dir_fd=directory)
                    try:
                        with os.fdopen(descriptor, 'wb') as stream:
                            stream.write(payload)
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
                    finally:
                        try:
                            os.unlink(temporary, dir_fd=directory)
                        except OSError:
                            pass
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def read_failure(reference=None) -> dict | None:
    """Read one reference, or the newest retained record across safe fallbacks."""
    if reference is not None and (not isinstance(reference, str) or not _REFERENCE.fullmatch(reference)):
        return None
    newest = None
    try:
        for candidate in tuple(_candidate_directories())[:3]:
            try:
                with _directory(candidate) as directory:
                    for modified, name, info in _files(directory):
                        if reference is not None and name != reference + '.json':
                            continue
                        if info.st_size > MAX_RECORD_BYTES or info.st_mtime < time.time() - MAX_AGE_SECONDS:
                            continue
                        try:
                            flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
                            with os.fdopen(os.open(name, flags, dir_fd=directory), 'rb') as stream:
                                if not _private_file(os.fstat(stream.fileno())):
                                    continue
                                content = stream.read(MAX_RECORD_BYTES + 1)
                            if len(content) > MAX_RECORD_BYTES:
                                continue
                            record = json.loads(content)
                            if (not isinstance(record, dict) or record.get('reference') != name[:-5]
                                    or not isinstance(record.get('traceback'), str)
                                    or not isinstance(record.get('runtime'), dict)):
                                continue
                            if reference is not None:
                                return record
                            if newest is None or modified > newest[0]:
                                newest = (modified, record)
                        except (OSError, ValueError, TypeError):
                            continue
            except Exception:
                continue
    except Exception:
        pass
    return newest[1] if newest else None
