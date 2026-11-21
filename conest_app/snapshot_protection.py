"""Publish verified migration snapshots without leaving a plaintext backup."""
from __future__ import annotations

import os
from pathlib import Path
import uuid

from .data_protection import encrypt_file, verify_encrypted_file


def publish_snapshot(plaintext: Path, target: Path, *, purpose: str, database: Path | None = None) -> Path:
    """Encrypt a new private snapshot, authenticate it, then publish atomically.

    Callers own and remove their temporary plaintext file in a finally block.
    Existing snapshots are never overwritten, including concurrent publishers.
    """
    encrypted = target.with_name('.' + target.name + '.' + uuid.uuid4().hex + '.pending')
    try:
        encrypt_file(plaintext, encrypted, purpose=purpose, database=database)
        verify_encrypted_file(encrypted, purpose=purpose, database=database)
        try:
            # A same-directory hard link publishes the complete encrypted file
            # atomically, and O_EXCL semantics protect an existing recovery copy.
            os.link(encrypted, target)
        except FileExistsError:
            verify_encrypted_file(target, purpose=purpose, database=database)
        return target
    finally:
        encrypted.unlink(missing_ok=True)
