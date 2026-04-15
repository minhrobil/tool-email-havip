#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

find_python_with_tkinter() {
  local candidates=()

  if [[ -n "${PYTHON_BOOTSTRAP:-}" ]]; then
    candidates+=("$PYTHON_BOOTSTRAP")
  fi

  while IFS= read -r candidate; do
    candidates+=("$candidate")
  done < <(which -a python3 2>/dev/null | awk '!seen[$0]++')

  candidates+=(
    "/opt/homebrew/Caskroom/miniconda/base/bin/python3"
    "/usr/local/bin/python3"
    "/opt/homebrew/bin/python3"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    [[ -x "$candidate" ]] || continue
    if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
if sys.version_info < (3, 10):
    raise SystemExit(1)
import tkinter
PY
    then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

if ! PYTHON_BIN="$(find_python_with_tkinter)"; then
  echo "[ERROR] Khong tim thay Python 3.10+ co tkinter tren macOS." >&2
  echo "GUI can tkinter. Python hien tai co the bi loi: No module named '_tkinter'." >&2
  echo "Cach xu ly goi y:" >&2
  echo "  - Dung Python co tkinter, vi du conda/base python neu co." >&2
  echo "  - Hoac cai Python tu python.org roi chay lai ./setup.sh." >&2
  echo "  - Co the chi dinh thu cong: PYTHON_BOOTSTRAP=/path/to/python3 ./setup.sh" >&2
  exit 1
fi

echo "================================================================"
echo " Cong Van Processor - macOS First-time Setup"
echo "================================================================"
echo

echo "[1/5] Checking Python..."
"$PYTHON_BIN" --version
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required.")
import tkinter
PY

echo
echo "[2/5] Creating virtual environment in .venv..."
if [[ -d ".venv" ]]; then
  if "$SCRIPT_DIR/.venv/bin/python" - <<'PY' >/dev/null 2>&1
import tkinter
PY
  then
    echo "  .venv already exists and has tkinter, skipping creation."
  else
    echo "  [ERROR] .venv exists but its Python does not have tkinter." >&2
    echo "  Remove it and rerun setup:" >&2
    echo "    rm -rf .venv" >&2
    echo "    ./setup.sh" >&2
    exit 1
  fi
else
  "$PYTHON_BIN" -m venv .venv
  echo "  .venv created."
fi

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
VENV_PIP="$SCRIPT_DIR/.venv/bin/pip"

echo
echo "[3/5] Installing Python dependencies..."
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PIP" install -r requirements.txt
"$VENV_PIP" install pytest

echo
echo "[4/5] Installing Playwright Chromium browser..."
"$VENV_PYTHON" -m playwright install chromium

echo
echo "[5/5] Verifying shell scripts..."
chmod +x run.sh run_headless.sh setup_scheduler.sh build.sh
"$VENV_PYTHON" -m pytest tests/ -v --tb=short

echo
echo "================================================================"
echo " Setup complete."
echo "================================================================"
echo
echo "NEXT STEPS:"
echo "  1. Edit config.json -> set azure.client_id if needed"
echo "  2. Run ./run.sh"
echo "  3. Login Microsoft once from the GUI"
