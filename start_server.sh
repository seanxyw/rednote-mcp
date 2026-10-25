#!/bin/bash
export PYTHONUNBUFFERED=1
export PYTHONWARNINGS=ignore

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -n "$PYTHON_BIN" ] && [ -x "$PYTHON_BIN" ]; then
    PY="$PYTHON_BIN"
elif [ -x "$SCRIPT_DIR/venv/bin/python" ]; then
    PY="$SCRIPT_DIR/venv/bin/python"
else
    PY="python3"
fi

exec "$PY" "$SCRIPT_DIR/rednote_mcp_server.py" --stdio 2>> "$SCRIPT_DIR/server.log"
