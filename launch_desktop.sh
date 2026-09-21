#!/usr/bin/env bash
# ResumeTailor Desktop launcher (Linux/macOS).
# Activates the local virtualenv if present and runs desktop.py.

set -euo pipefail

cd "$(dirname "$0")"

VENV_BIN=".venv/bin"
if [ ! -x "$VENV_BIN/python" ]; then
    echo "Virtual environment not found at $VENV_BIN/python." >&2
    echo "Create it first:" >&2
    echo "  python3 -m venv .venv" >&2
    echo "  $VENV_BIN/pip install -r requirements.txt" >&2
    exit 1
fi

# macOS lacks python3-gi but the desktop app uses pywebview's native
# Cocoa backend, so no system packages are required there.
# On Linux we need GTK + WebKit2; if they're missing pywebview will
# raise a clear error pointing the user at the package install command.

exec "$VENV_BIN/python" desktop.py "$@"
