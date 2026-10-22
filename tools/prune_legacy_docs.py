"""Dry-run-first removal of root release-note files consolidated into README.md."""
from pathlib import Path
import argparse
import re

ROOT = Path(__file__).resolve().parents[1]
LEGACY = (
    re.compile(r"CHANGED_FILES_.*\.txt", re.I),
    re.compile(r"QUALITY_REVIEW_.*\.txt", re.I),
    re.compile(r"UPDATE_INSTRUCTIONS(?:_V[0-9.]+)?\.(?:txt|md)", re.I),
    re.compile(r"UPDATE_V[0-9.]+\.md", re.I),
    re.compile(r"V[0-9.]+_FILE_MANIFEST\.json", re.I),
    re.compile(r"TENDERS_UPDATE\.md", re.I),
)


def candidates():
    return [p for p in ROOT.iterdir() if p.is_file() and not p.is_symlink() and
            any(pattern.fullmatch(p.name) for pattern in LEGACY)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Delete the listed legacy docs')
    args=parser.parse_args()
    files=sorted(candidates())
    for file in files:
        print(('DELETE' if args.apply else 'WOULD DELETE'), file.name)
        if args.apply: file.unlink()
    print(len(files), 'legacy documentation files', 'removed' if args.apply else 'listed (dry run)')


if __name__=='__main__':
    main()
