"""Authenticated encryption for server secrets and portable database snapshots.

Live SQLite databases deliberately keep their existing format. Protect their
storage with the host's encrypted volume; this module protects saved API keys
and exported backups without requiring a native SQLite extension.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import errno
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
SECRET_PREFIX = "tecflow:aesgcm:v1:"
FILE_MAGIC = b"TECFLOW-AES256GCM\x01"
KEY_ID_SETTING = "data_protection_key_id"
CHUNK_SIZE = 1024 * 1024


class ProtectionError(RuntimeError):
    """Protection cannot proceed safely; never fall back to plaintext."""


def _database(database=None) -> Path:
    if database is not None:
        return Path(database).expanduser().resolve()
    from .database import database_path
    return database_path().resolve()


def connection_database_path(conn: sqlite3.Connection) -> Path:
    for row in conn.execute("PRAGMA database_list"):
        if row[1] == "main" and row[2]:
            return Path(row[2]).resolve()
    return _database()


def private_directory(path: Path) -> Path:
    path = Path(path)
    if path.is_symlink():
        raise ProtectionError("Private storage must not be a symbolic link.")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(path, 0o700)
    return path


def private_file(path: Path) -> None:
    path = Path(path)
    if path.is_symlink():
        raise ProtectionError("Private storage must not be a symbolic link.")
    if os.name != "nt":
        os.chmod(path, 0o600)


@contextmanager
def _new_private_file(path: Path):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(path), flags, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        yield handle
        handle.flush()
        os.fsync(handle.fileno())


def _outside_webroot(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    roots = [ROOT]
    document_root = os.environ.get("DOCUMENT_ROOT", "").strip()
    if document_root:
        roots.append(Path(document_root).expanduser().resolve())
    for root in roots:
        if resolved == root or root in resolved.parents:
            raise ProtectionError("The encryption key file must be outside the website directory.")
    return resolved


def key_file_path(database=None) -> Path | None:
    raw = os.environ.get("CONEST_ENCRYPTION_KEY", "").strip()
    configured = os.environ.get("CONEST_ENCRYPTION_KEY_FILE", "").strip()
    if raw and configured:
        raise ProtectionError("Configure either an encryption key or its key file, not both.")
    if raw:
        return None
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            raise ProtectionError("The encryption key file must use an absolute path.")
        if candidate.is_symlink():
            raise ProtectionError("The encryption key file must not be a symbolic link.")
        return _outside_webroot(candidate)
    identity = hashlib.sha256(str(_database(database)).encode("utf-8")).hexdigest()[:24]
    return _outside_webroot(Path.home() / ".tec-flow" / "keys" / (identity + ".key"))


def _decode_key(value: bytes | str) -> bytes:
    try:
        raw = value.encode("ascii") if isinstance(value, str) else value
        key = base64.b64decode(raw.strip(), altchars=b"-_", validate=True)
    except (UnicodeError, ValueError) as exc:
        raise ProtectionError("The encryption key must be a valid base64-encoded 32-byte key.") from exc
    if len(key) != 32:
        raise ProtectionError("The encryption key must be a valid base64-encoded 32-byte key.")
    return key


def _read_key_file(path: Path) -> bytes:
    try:
        descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except (FileNotFoundError, OSError) as exc:
        raise ProtectionError("The encryption key file is missing or unreadable. Restore the original key before continuing.") from exc
    with os.fdopen(descriptor, "rb") as handle:
        details = os.fstat(handle.fileno())
        if not stat.S_ISREG(details.st_mode) or details.st_size > 256:
            raise ProtectionError("The encryption key file is invalid.")
        if os.name != "nt" and (details.st_mode & 0o077 or details.st_uid != os.geteuid()):
            raise ProtectionError("The encryption key file must be owned by the service account with permissions 0600.")
        return _decode_key(handle.read(257))


def _create_key_file(path: Path) -> None:
    # Publish a fully written key with a no-replace operation. Two fresh workers
    # must never read a half-written key or replace each other's key.
    private_directory(path.parent)
    if not os.environ.get("CONEST_ENCRYPTION_KEY_FILE", "").strip():
        private_directory(path.parent.parent)
    descriptor, pending_name = tempfile.mkstemp(prefix=".key-", dir=path.parent)
    pending = Path(pending_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(pending, path)
            _sync_directory(path.parent)
        except FileExistsError:
            pass
    finally:
        pending.unlink(missing_ok=True)


def _marker_path(database=None) -> Path:
    return _database(database).with_name("." + _database(database).name + ".protection.json")


def _read_marker(path: Path) -> str | None:
    if path.is_symlink():
        raise ProtectionError("The encryption protection marker is invalid.")
    try:
        marker = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ProtectionError("The encryption protection marker is invalid.") from exc
    identity = marker.get("key_id") if isinstance(marker, dict) else None
    if not isinstance(marker, dict) or marker.get("version") != 1 or not isinstance(identity, str) or len(identity) != 64 or any(char not in '0123456789abcdef' for char in identity):
        raise ProtectionError("The encryption protection marker is invalid.")
    return identity


def key_identifier(key: bytes) -> str:
    return hashlib.sha256(b"TEC Flow protection key v1\0" + key).hexdigest()


def _sync_directory(path: Path) -> None:
    if os.name == 'nt':
        return
    descriptor = os.open(str(path), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EBADF):
                raise
    finally:
        os.close(descriptor)


def _publish_marker(path: Path, identity: str) -> None:
    descriptor, pending_name = tempfile.mkstemp(prefix='.protection-', dir=path.parent)
    pending = Path(pending_name)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(json.dumps({'version': 1, 'key_id': identity}).encode('utf-8'))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(pending, path)
            _sync_directory(path.parent)
        except FileExistsError:
            if not hmac.compare_digest(_read_marker(path) or '', identity):
                raise ProtectionError('The configured encryption key does not match this installation.')
    finally:
        pending.unlink(missing_ok=True)


def _database_key_id(database=None) -> str | None:
    """The DB fingerprint also survives accidentally losing the sidecar marker."""
    path = _database(database)
    if not path.is_file() or path.stat().st_size == 0:
        return None
    connection = sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True, timeout=30)
    try:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'").fetchone():
            return None
        row = connection.execute('SELECT value FROM settings WHERE key=?', (KEY_ID_SETTING,)).fetchone()
        return str(row[0]) if row and row[0] else None
    finally:
        connection.close()


def load_key(*, database=None, create: bool = False) -> bytes:
    marker_path = _marker_path(database)
    marker_id = _read_marker(marker_path)
    recorded = marker_id or _database_key_id(database)
    path = key_file_path(database)
    raw = os.environ.get("CONEST_ENCRYPTION_KEY", "").strip()
    if path is None:
        key = _decode_key(raw)
    else:
        if not path.exists():
            # Explicitly configured files must be provisioned by the operator.
            # A recorded fingerprint prevents silently replacing a lost key.
            if not create or recorded or os.environ.get("CONEST_ENCRYPTION_KEY_FILE", "").strip():
                raise ProtectionError("The encryption key file is missing. Restore the original key before continuing.")
            _create_key_file(path)
        key = _read_key_file(path)
    identity = key_identifier(key)
    if recorded and not hmac.compare_digest(recorded, identity):
        raise ProtectionError("The configured encryption key does not match this installation. Restore the original key.")
    if create and not marker_id:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        _publish_marker(marker_path, identity)
    return key


def protect_secret(value: str, *, setting: str, database=None) -> str:
    if not value:
        return ""
    key = load_key(database=database, create=True)
    nonce = os.urandom(12)
    data = AESGCM(key).encrypt(nonce, value.encode("utf-8"), ("TEC Flow setting:" + setting).encode("ascii"))
    return SECRET_PREFIX + base64.urlsafe_b64encode(nonce + data).decode("ascii")


def unprotect_secret(value: str, *, setting: str, database=None) -> str:
    if value.startswith('tecflow:') and not value.startswith(SECRET_PREFIX):
        raise ProtectionError('The saved credential uses an unsupported encryption format.')
    if not value or not value.startswith(SECRET_PREFIX):
        # Legacy plaintext is accepted only for compatibility during migration.
        return value
    try:
        data = base64.b64decode(value[len(SECRET_PREFIX):].encode("ascii"), altchars=b"-_", validate=True)
        if len(data) < 28:
            raise ValueError("truncated")
        key = load_key(database=database)
        clear = AESGCM(key).decrypt(data[:12], data[12:], ("TEC Flow setting:" + setting).encode("ascii"))
        return clear.decode("utf-8")
    except (InvalidTag, UnicodeError, ValueError) as exc:
        raise ProtectionError("The saved credential could not be authenticated. Check the original encryption key.") from exc


def protect_database_settings(conn: sqlite3.Connection) -> bool:
    """Migrate saved credentials once; caller owns the transaction/commit."""
    database = connection_database_path(conn)
    row = conn.execute("SELECT value FROM settings WHERE key=?", (KEY_ID_SETTING,)).fetchone()
    recorded = str(row[0]) if row else ""
    key = load_key(database=database, create=not bool(recorded))
    identity = key_identifier(key)
    if recorded and not hmac.compare_digest(recorded, identity):
        raise ProtectionError("The configured encryption key does not match this database. Restore the original key.")
    secret = conn.execute("SELECT value FROM settings WHERE key='gemini_api_key'").fetchone()
    changed = False
    if secret and secret[0]:
        if str(secret[0]).startswith(SECRET_PREFIX):
            unprotect_secret(str(secret[0]), setting="gemini_api_key", database=database)
        else:
            conn.execute("PRAGMA secure_delete=ON")
            encrypted = protect_secret(str(secret[0]), setting="gemini_api_key", database=database)
            conn.execute("UPDATE settings SET value=? WHERE key='gemini_api_key'", (encrypted,))
            changed = True
    if not recorded:
        from .utils import utc_now
        conn.execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)", (KEY_ID_SETTING, identity, utc_now()))
    return changed


def _header(purpose: str, key: bytes, nonce: bytes) -> bytes:
    encoded = purpose.encode("ascii")
    if not encoded or len(encoded) > 64:
        raise ValueError("Invalid encryption purpose")
    return FILE_MAGIC + bytes.fromhex(key_identifier(key))[:16] + nonce + bytes([len(encoded)]) + encoded


def _read_header(handle: BinaryIO, purpose: str) -> tuple[bytes, bytes, bytes]:
    fixed_size = len(FILE_MAGIC) + 16 + 12 + 1
    fixed = handle.read(fixed_size)
    if len(fixed) != fixed_size or not fixed.startswith(FILE_MAGIC) or not 1 <= fixed[-1] <= 64:
        raise ProtectionError("This is not a supported encrypted TEC Flow backup.")
    encoded = handle.read(fixed[-1])
    if encoded != purpose.encode("ascii"):
        raise ProtectionError("This encrypted backup belongs to a different database type.")
    offset = len(FILE_MAGIC)
    return fixed + encoded, fixed[offset:offset + 16], fixed[offset + 16:offset + 28]


def encrypt_file(source: Path, destination: Path, *, purpose: str, database=None) -> dict:
    """Stream an authenticated encrypted copy; never overwrite the source."""
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or source.is_symlink():
        raise ValueError("Choose a different output file and a regular source file.")
    key = load_key(database=database, create=True)
    nonce = os.urandom(12)
    header = _header(purpose, key, nonce)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    created = False
    try:
        with source.open("rb") as incoming, _new_private_file(destination) as outgoing:
            created = True
            outgoing.write(header)
            while chunk := incoming.read(CHUNK_SIZE):
                outgoing.write(encryptor.update(chunk))
            outgoing.write(encryptor.finalize())
            outgoing.write(encryptor.tag)
        verify_encrypted_file(destination, purpose=purpose, database=database)
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return {"encrypted": True, "encryption": "AES-256-GCM", "key_id": key_identifier(key)}


def _decrypt(source: Path, outgoing: BinaryIO | None, *, purpose: str, database=None) -> dict:
    key = load_key(database=database)
    with Path(source).open("rb") as incoming:
        header, identity, nonce = _read_header(incoming, purpose)
        if not hmac.compare_digest(identity, bytes.fromhex(key_identifier(key))[:16]):
            raise ProtectionError("This backup requires its original encryption key.")
        size = os.fstat(incoming.fileno()).st_size
        remaining = size - len(header) - 16
        if remaining < 0:
            raise ProtectionError("The encrypted backup is incomplete.")
        incoming.seek(-16, os.SEEK_END)
        tag = incoming.read(16)
        incoming.seek(len(header))
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(header)
        try:
            while remaining:
                chunk = incoming.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    raise ProtectionError("The encrypted backup is incomplete.")
                remaining -= len(chunk)
                plain = decryptor.update(chunk)
                if outgoing is not None:
                    outgoing.write(plain)
            tail = decryptor.finalize()
            if outgoing is not None:
                outgoing.write(tail)
        except InvalidTag as exc:
            raise ProtectionError("The encrypted backup failed authentication. It was changed or uses a different key.") from exc
    return {"encrypted": True, "encryption": "AES-256-GCM", "key_id": key_identifier(key)}


def verify_encrypted_file(source: Path, *, purpose: str, database=None) -> dict:
    return _decrypt(Path(source), None, purpose=purpose, database=database)


def decrypt_file(source: Path, destination: Path, *, purpose: str, database=None) -> None:
    """Publish no plaintext until its authentication has succeeded.

    Temporary plaintext is owner-only and removed on any failure. Callers must
    not open the destination until this function returns successfully.
    """
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or source.is_symlink():
        raise ValueError("Choose a different output file and a regular source file.")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('The output file already exists; choose a new path.')
    descriptor, pending_name = tempfile.mkstemp(prefix='.authenticated-restore-', dir=destination.parent)
    pending = Path(pending_name)
    try:
        with os.fdopen(descriptor, 'wb') as outgoing:
            _decrypt(source, outgoing, purpose=purpose, database=database)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        os.link(pending, destination)
        _sync_directory(destination.parent)
    finally:
        pending.unlink(missing_ok=True)
