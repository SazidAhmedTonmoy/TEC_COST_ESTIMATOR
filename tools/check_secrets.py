"""Scan application source or release ZIPs for common credential signatures.

Output contains rule names, paths and line numbers only, never matched values.
This check supplements code review; it cannot prove that every secret is absent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.pytest_cache'}
BINARY_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.png', '.jpg', '.jpeg', '.webp', '.gif',
                   '.ico', '.woff', '.woff2', '.ttf', '.pdf', '.xlsx', '.xlsm', '.pyc', '.enc'}
MAX_FILE_BYTES = 20 * 1024 * 1024
SIGNATURES = {
    'google-api-key': re.compile(r'\bAIza[0-9A-Za-z_-]{35}\b'),
    'openai-style-secret': re.compile(r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}'),
    'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'aws-access-key-id': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'stripe-secret-key': re.compile(r'\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b'),
    'slack-token': re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
    'private-key-block': re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----'),
}
ASSIGNED_SECRET = re.compile(
    r'''(?im)\b(?:gemini_api_key|openai_api_key|api_key|api_secret|api_token|client_secret|access_token|password)\b["']?\s*[:=]\s*["']([^"'\\\r\n]{16,})["']''')


def scan_text(name: str, text: str) -> list[dict]:
    findings = []
    for rule, pattern in SIGNATURES.items():
        for match in pattern.finditer(text):
            findings.append({'path': name, 'line': text.count('\n', 0, match.start()) + 1, 'rule': rule})
    # Test fixtures deliberately include nonproduction password strings. Known
    # provider-token/private-key signatures above still apply to every text file.
    if 'tests' not in PurePosixPath(name).parts:
        for match in ASSIGNED_SECRET.finditer(text):
            value = match.group(1).strip()
            if value.startswith(('<', '${')) or value.lower().startswith(('your-', 'your_', 'replace-with', 'example-')):
                continue
            findings.append({'path': name, 'line': text.count('\n', 0, match.start()) + 1,
                             'rule': 'literal-secret-assignment'})
    return findings


def eligible(name: str, size: int) -> bool:
    path = PurePosixPath(name)
    if any(part in IGNORED_PARTS for part in path.parts) or size > MAX_FILE_BYTES:
        return False
    if path.suffix.lower() in BINARY_SUFFIXES or any(part.startswith(('.db-', '.sqlite-')) for part in path.suffixes):
        return False
    return not re.search(r'\.(?:db|sqlite3?)[.-]', path.name, re.I)


def scan(target: Path) -> dict:
    target = Path(target)
    result = {'scanned_files': 0, 'findings': [], 'skipped_files': 0}

    def consume(name, size, read):
        if not eligible(name, size):
            result['skipped_files'] += 1
            return
        content = read()
        if b'\x00' in content:
            result['skipped_files'] += 1
            return
        result['scanned_files'] += 1
        result['findings'].extend(scan_text(name, content.decode('utf-8', errors='replace')))

    if target.is_file() and zipfile.is_zipfile(target):
        with zipfile.ZipFile(target) as archive:
            for member in archive.infolist():
                if not member.is_dir():
                    consume(member.filename, member.file_size, lambda m=member: archive.read(m))
    elif target.is_dir():
        for path in sorted(target.rglob('*')):
            if path.is_file() and not path.is_symlink():
                name = path.relative_to(target).as_posix()
                consume(name, path.stat().st_size, path.read_bytes)
    else:
        raise ValueError('Choose an application directory or release ZIP')
    result['findings'] = sorted(result['findings'], key=lambda f: (f['path'], f['line'], f['rule']))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path, nargs='?', default=ROOT)
    args = parser.parse_args()
    try:
        result = scan(args.target)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(2, f'Secret scan could not finish: {type(exc).__name__}\n')
    print(json.dumps(result, indent=2))
    return 1 if result['findings'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
