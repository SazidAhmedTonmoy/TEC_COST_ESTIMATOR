"""Delegate Passenger to the shipped runtime, preserving host Python/env setup."""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BEGIN = b'# BEGIN TEC FLOW WSGI RUNTIME DELEGATION'
END = b'# END TEC FLOW WSGI RUNTIME DELEGATION'
DELEGATION = b'from conest_app.wsgi_runtime import application'
FRESH_BOOTSTRAP = b'''# TEC Flow Passenger entry point.
import sys
from pathlib import Path
_tec_flow_root = str(Path(__file__).resolve().parent)
if _tec_flow_root not in sys.path:
    sys.path.insert(0, _tec_flow_root)
'''


def merge_runtime(existing: bytes) -> bytes:
    if BEGIN in existing or END in existing:
        if existing.count(BEGIN) != 1 or existing.count(END) != 1:
            raise ValueError('WSGI runtime markers are incomplete or duplicated; no startup file was changed')
        first = existing.index(BEGIN)
        last = existing.index(END)
        if first > last:
            raise ValueError('WSGI runtime markers are out of order; no startup file was changed')
        last += len(END)
        if existing[last:last + 2] == b'\r\n':
            last += 2
        elif existing[last:last + 1] == b'\n':
            last += 1
        existing = existing[:first] + existing[last:]
    block = BEGIN + b'\n' + DELEGATION + b'\n' + END + b'\n'
    return existing + (b'\n' if existing and not existing.endswith(b'\n') else b'') + block


def _check_syntax(source: bytes, label: str) -> None:
    try:
        ast.parse(source, filename=label)
    except (SyntaxError, ValueError, UnicodeError) as exc:
        # SyntaxError text can contain an environment assignment or credential.
        # Report only the affected file category and line number, never source.
        line = getattr(exc, 'lineno', None)
        suffix = f' at line {line}' if line else ''
        raise ValueError(f'{label} is not valid Python{suffix}; no startup file was changed') from None


def install(root: Path = ROOT) -> bool:
    root = Path(root).resolve()
    target = root / 'passenger_wsgi.py'
    runtime = root / 'conest_app' / 'wsgi_runtime.py'
    if target.is_symlink():
        raise ValueError('Install WSGI delegation into the startup file target; symbolic links are not replaced')
    if not runtime.is_file():
        raise ValueError('The shipped WSGI runtime is missing; upload the complete update before installing')
    _check_syntax(runtime.read_bytes(), 'Shipped WSGI runtime')
    existing = target.read_bytes() if target.exists() else FRESH_BOOTSTRAP
    _check_syntax(existing, 'Existing WSGI startup file')
    updated = merge_runtime(existing)
    _check_syntax(updated, 'Updated WSGI startup file')
    if target.exists() and updated == existing:
        target.chmod(0o600)
        return False
    fd, temporary = tempfile.mkstemp(prefix='.passenger-security-', dir=root)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
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
        parser.exit(1, f'WSGI runtime was not installed: {exc}\n')
    print('Passenger runtime delegation installed.' if changed else 'Passenger runtime delegation is already current.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
