#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -n "$PYTHON_BIN" ] && [ -x "$PYTHON_BIN" ]; then
    PY="$PYTHON_BIN"
elif [ -x "$SCRIPT_DIR/venv/bin/python" ]; then
    PY="$SCRIPT_DIR/venv/bin/python"
else
    PY="python3"
fi

exec "$PY" "$SCRIPT_DIR/rednote_login.py" "$@"
