#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Windows .exe build khong duoc ho tro tren macOS."
echo "Dung file nay de nhac workflow:"
echo "  1. Dev va test tren macOS bang ./run.sh hoac ./run_headless.sh"
echo "  2. Build Windows tren may Windows bang build.bat"
echo "  3. Dist Windows se duoc kem setup_scheduler.bat va run_headless.bat"
