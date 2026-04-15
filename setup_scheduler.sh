#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

HOUR="${1:-8}"
MINUTE="${2:-0}"
LABEL="com.toolxulymailcongvan"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
RUN_SCRIPT="$SCRIPT_DIR/run_headless.sh"
LOG_FILE="$SCRIPT_DIR/_scheduler_run.log"
ERROR_LOG="$SCRIPT_DIR/_scheduler_run.err.log"

if [[ ! "$HOUR" =~ ^([0-9]|1[0-9]|2[0-3])$ ]]; then
  echo "[ERROR] Gio khong hop le: $HOUR" >&2
  exit 1
fi

if [[ ! "$MINUTE" =~ ^([0-9]|[1-5][0-9])$ ]]; then
  echo "[ERROR] Phut khong hop le: $MINUTE" >&2
  exit 1
fi

if [[ ! -x "$RUN_SCRIPT" ]]; then
  echo "[ERROR] Khong tim thay script chay headless: $RUN_SCRIPT" >&2
  echo "Hay chmod +x run_headless.sh roi thu lai." >&2
  exit 1
fi

mkdir -p "$(dirname "$PLIST_PATH")"

cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$RUN_SCRIPT</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$SCRIPT_DIR</string>
  <key>RunAtLoad</key>
  <false/>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>$HOUR</integer>
    <key>Minute</key>
    <integer>$MINUTE</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_FILE</string>
  <key>StandardErrorPath</key>
  <string>$ERROR_LOG</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"

echo "Scheduler da duoc cai tren macOS."
echo "Label     : $LABEL"
echo "Thoi gian : $(printf '%02d:%02d' "$HOUR" "$MINUTE") moi ngay"
echo "Plist     : $PLIST_PATH"
echo
echo "Lenh go bo:"
echo "  launchctl bootout gui/$(id -u) \"$PLIST_PATH\""
echo "  rm \"$PLIST_PATH\""
