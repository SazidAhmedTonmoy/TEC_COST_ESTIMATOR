"""Install Apache file protection without replacing cPanel Passenger settings."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BEGIN = b'# BEGIN TEC FLOW PRIVATE FILE PROTECTION'
END = b'# END TEC FLOW PRIVATE FILE PROTECTION'


def merge_rules(existing: bytes, rules: bytes) -> bytes:
    block = BEGIN + b'\n' + rules.strip() + b'\n' + END + b'\n'
    if BEGIN not in existing and END not in existing:
        return block + existing
    if existing.count(BEGIN) != 1 or existing.count(END) != 1:
        raise ValueError('Apache security markers are incomplete or duplicated; check .htaccess before installing')
    first = existing.index(BEGIN)
    last = existing.index(END)
    if first > last:
        raise ValueError('Apache security markers are out of order; check .htaccess before installing')
    last += len(END)
    # The managed closing marker owns its line ending. Every byte outside the
    # managed block stays in its original order; protection must precede any
    # host RewriteRule using [L]/[END] to bypass physical files.
    if existing[last:last + 2] == b'\r\n':
        last += 2
    elif existing[last:last + 1] == b'\n':
        last += 1
    return block + existing[:first] + existing[last:]


def install(root: Path = ROOT) -> bool:
    root = Path(root).resolve()
    target = root / '.htaccess'
    if target.is_symlink():
        raise ValueError('Install Apache security rules into the existing .htaccess target; symbolic links are not replaced')
    rules = (root / 'security' / 'apache-access.conf').read_bytes()
    existing = target.read_bytes() if target.exists() else b''
    updated = merge_rules(existing, rules)
    if updated == existing:
        return False
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix='.htaccess-security-', dir=root)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='TEC Flow application directory')
    args = parser.parse_args()
    try:
        changed = install(args.root)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Apache protection was not installed: {exc}\n')
    print('Apache private-file protection installed.' if changed else 'Apache private-file protection is already current.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
