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

pkill -f rednote_mcp_server.py 2>/dev/null || true
sleep 1
nohup "$PY" "$SCRIPT_DIR/rednote_mcp_server.py" > "$SCRIPT_DIR/server.log" 2>&1 </dev/null &
sleep 2
cat "$SCRIPT_DIR/server.log"
