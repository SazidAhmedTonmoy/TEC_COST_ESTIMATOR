"""Copy-only encryption and verified recovery for TEC Flow database snapshots."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from conest_app.data_protection import (  # noqa: E402
    ProtectionError, decrypt_file, encrypt_file, key_file_path, key_identifier,
    load_key, verify_encrypted_file,
)


def _check_sqlite(path):
    with closing(sqlite3.connect(f'{Path(path).resolve().as_uri()}?mode=ro', uri=True)) as connection:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('The database snapshot failed its integrity check.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('encrypt', 'decrypt', 'verify', 'status'))
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--kind', choices=('catalog', 'tenders'), default='catalog')
    parser.add_argument('--key-database', type=Path,
                        help='Original catalog path identifying the server key; defaults to CONEST_DB_PATH.')
    arguments = parser.parse_args(argv)
    purpose = 'backup:' + arguments.kind
    try:
        if arguments.action == 'status':
            key = load_key(database=arguments.key_database)
            key_path = key_file_path(arguments.key_database)
            print(json.dumps({
                'algorithm': 'AES-256-GCM', 'key_id': key_identifier(key),
                'key_source': 'environment' if key_path is None else str(key_path),
                'coverage': 'Saved API credentials and encrypted database backups',
                'live_database': 'Ordinary SQLite; encrypted host storage is required for full data at rest protection',
            }, indent=2))
            return 0
        source = arguments.source
        if source is None or not source.is_file() or source.is_symlink():
            parser.error('--source must be an existing regular file.')
        output = arguments.output
        if arguments.action in ('encrypt', 'decrypt'):
            if output is None:
                parser.error('--output is required; existing files are never overwritten.')
            if output.exists() or output.is_symlink() or source.resolve() == output.resolve():
                parser.error('Choose a new output path; existing files are never overwritten.')
            if not output.parent.is_dir():
                parser.error('Create the destination directory first.')
        if arguments.action == 'encrypt':
            if not str(output).endswith('.db.enc'):
                parser.error('Encrypted output must end in .db.enc.')
            with tempfile.TemporaryDirectory(prefix='tec-protect-') as temporary:
                snapshot = Path(temporary) / 'snapshot.db'
                snapshot.touch(mode=0o600)
                with closing(sqlite3.connect(f'{source.resolve().as_uri()}?mode=ro', uri=True)) as incoming:
                    with closing(sqlite3.connect(snapshot)) as destination:
                        incoming.backup(destination)
                _check_sqlite(snapshot)
                encrypt_file(snapshot, output, purpose=purpose, database=arguments.key_database)
            print('Encrypted copy created and authenticated. The source is unchanged.')
        else:
            verify_encrypted_file(source, purpose=purpose, database=arguments.key_database)
            # Put the final verified file on the destination filesystem for an
            # atomic no-overwrite publication, including cross-device restores.
            parent = output.parent if output is not None else None
            with tempfile.TemporaryDirectory(prefix='.tec-verified-', dir=parent) as temporary:
                snapshot = Path(temporary) / 'snapshot.db'
                decrypt_file(source, snapshot, purpose=purpose, database=arguments.key_database)
                _check_sqlite(snapshot)
                if arguments.action == 'decrypt':
                    os.link(snapshot, output)
                    print('Verified recovery copy created with owner-only permissions. The source is unchanged.')
                else:
                    print('Encrypted backup authentication and SQLite integrity checks passed.')
        return 0
    except (ProtectionError, sqlite3.Error, OSError, ValueError) as exc:
        # ProtectionError messages are local and never include keys or contents.
        print('Data protection failed: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
