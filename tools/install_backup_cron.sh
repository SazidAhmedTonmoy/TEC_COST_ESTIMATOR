#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
if command -v python3.11 >/dev/null 2>&1; then BACKUP_BOOT=python3.11
elif command -v python3 >/dev/null 2>&1; then BACKUP_BOOT=python3
else echo 'Python is required to install scheduled backups.' >&2; exit 1
fi
BACKUP_PY="$("$BACKUP_BOOT" tools/select_python.py)"
"$BACKUP_PY" tools/install_backup_cron.py
