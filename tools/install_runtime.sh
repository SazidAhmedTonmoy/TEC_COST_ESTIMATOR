#!/usr/bin/env sh
# Use the production interpreter, not an unrelated system pip.
set -eu
cd "$(dirname "$0")/.."
if command -v python3.11 >/dev/null 2>&1; then BOOT=python3.11
elif command -v python3 >/dev/null 2>&1; then BOOT=python3
else echo 'No Python interpreter is available.' >&2; exit 1
fi
PY="$("$BOOT" tools/select_python.py --require-configured)"
# Reject an unsupported Python/SQLite before pip changes the selected runtime.
# Timezone data is checked after installation because requirements provides it.
"$PY" tools/check_runtime.py --preflight
echo "Installing application dependencies with $PY"
if "$PY" -c 'import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)'; then
  "$PY" -m pip install -r requirements.txt
else
  "$PY" -m pip install --user -r requirements.txt
fi
"$PY" tools/check_runtime.py
# Do not initialize a guessed database here. The restarted application and its
# health endpoint migrate the database selected by the actual WSGI environment.
