#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[ERROR] Chua co Python virtual environment tai .venv." >&2
  echo "Chay ./setup.sh truoc, sau do chay lai ./run_headless.sh." >&2
  exit 1
fi

LOG_FILE="$SCRIPT_DIR/_scheduler_run.log"

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting headless run"
  if "$PYTHON_BIN" run_app.py --headless --log-file "$LOG_FILE" "$@"; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Completed successfully"
  else
    EXIT_CODE=$?
    if [[ "$EXIT_CODE" -eq 2 ]]; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Not signed in. Please run ./run.sh first."
    else
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] Completed with errors (exit code $EXIT_CODE)"
    fi
    exit "$EXIT_CODE"
  fi
} >>"$LOG_FILE" 2>&1
