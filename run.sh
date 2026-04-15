#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[ERROR] Chua co Python virtual environment tai .venv." >&2
  echo "Chay ./setup.sh truoc, sau do chay lai ./run.sh." >&2
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import tkinter
PY
then
  echo "[ERROR] .venv Python khong co tkinter (_tkinter), nen khong chay duoc GUI." >&2
  echo "Hay tao lai .venv bang Python co tkinter:" >&2
  echo "  rm -rf .venv" >&2
  echo "  ./setup.sh" >&2
  echo "Neu can chi dinh Python:" >&2
  echo "  PYTHON_BOOTSTRAP=/path/to/python3 ./setup.sh" >&2
  exit 1
fi

echo "Starting Cong Van Processor..."
exec "$PYTHON_BIN" run_app.py "$@"
