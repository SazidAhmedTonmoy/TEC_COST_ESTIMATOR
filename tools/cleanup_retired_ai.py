"""Check for (or explicitly remove) AI files retired in TEC Flow v3.8.13.

An update ZIP overlays files; it cannot remove older files from a Git checkout.
Keep this list exact: do not touch databases, configuration or other user files.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETIRED_FILES = (
    'assets/app.f7ecc7922ad0.js',  # v3.8.12 compiled assistant
    'assets/app.c888126a4861.js',  # discarded v3.9.0 compiled assistant
    'assets/styles.1725e0d1f799.css',
    'assets/help_chat.js',
    'conest_app/assistant.py',
    'conest_app/assistant_actions.py',
    'conest_app/help_chat.py',
    'conest_app/hybrid_ai.py',
    'tests/test_help_assistant.py',
    'tests/test_hybrid_ai.py',
    'AI_TECHNICAL.md',
)


def retired_paths(root: Path) -> list[str]:
    return [name for name in RETIRED_FILES
            if (root / name).exists() or (root / name).is_symlink()]


def remove_retired(root: Path) -> list[str]:
    root = root.resolve()
    # Only run on the replacement guide release, not on a pre-removal checkout.
    for name in ('assets/user_guide.js', 'tests/test_user_guide.py'):
        if not (root / name).is_file():
            raise ValueError('Apply the v3.8.13 replacement source before removing retired AI files.')
    names = retired_paths(root)
    # Preflight every path so a directory or a redirected parent is not removed.
    for name in names:
        path = root / name
        if not path.parent.resolve().is_relative_to(root) or not (path.is_file() or path.is_symlink()):
            raise ValueError(f'Refusing to remove unexpected path: {name}')
    for name in names:
        (root / name).unlink()
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Remove only the listed retired AI source/test files.')
    args = parser.parse_args()
    names = retired_paths(ROOT)
    if not names:
        print('Retired AI source check passed: no obsolete files found.')
        return 0
    print('Obsolete AI files remaining in this checkout:')
    for name in names:
        print(f'  {name}')
    if not args.apply:
        print('Apply v3.8.13, run python tools/cleanup_retired_ai.py --apply, then git add -A and commit the deletions.')
        return 1
    try:
        remove_retired(ROOT)
    except (OSError, ValueError) as exc:
        print(f'Cleanup failed: {exc}')
        return 1
    print('Removed retired AI files. Review git status and commit the deletions. No databases or configuration changed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
