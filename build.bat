@echo off
:: ─────────────────────────────────────────────────────────────────────────
:: build.bat  —  Build standalone Windows .exe with PyInstaller
::
:: Output: dist\ToolXuLyMailCongVan\ToolXuLyMailCongVan.exe
:: Users only need this .exe + config.json; no Python install required.
:: ─────────────────────────────────────────────────────────────────────────
chcp 65001 > nul
cd /d "%~dp0"

echo ================================================================
echo  Building ToolXuLyMailCongVan.exe ...
echo ================================================================

:: Install/update dependencies first
pip install -r requirements.txt

:: Install Playwright browser (Chromium) — required for portal automation
playwright install chromium
playwright install-deps chromium

:: Run PyInstaller
pyinstaller ^
  --name ToolXuLyMailCongVan ^
  --onedir ^
  --windowed ^
  --icon NONE ^
  --add-data "config.json;." ^
  --hidden-import msal ^
  --hidden-import msal.authority ^
  --hidden-import msal.application ^
  --hidden-import fitz ^
  --hidden-import openpyxl ^
  --hidden-import dateutil ^
  --hidden-import dateutil.relativedelta ^
  --hidden-import playwright ^
  --hidden-import playwright.sync_api ^
  --collect-all msal ^
  --collect-all playwright ^
  run_app.py

if %errorlevel% equ 0 (
    echo.
    echo ✅ Build successful!
    echo.
    echo   Executable : dist\ToolXuLyMailCongVan\ToolXuLyMailCongVan.exe
    echo.
    echo IMPORTANT: Playwright Chromium must also be available on the target machine.
    echo   Option A: Run 'playwright install chromium' on the target machine.
    echo   Option B: Copy the Chromium folder from %%LOCALAPPDATA%%\ms-playwright\
    echo             to the same path on the target machine.
    echo.
    echo Deployment steps:
    echo   1. Copy the entire dist\ToolXuLyMailCongVan\ folder to the target machine
    echo   2. Edit config.json with the correct Azure client_id and folder paths
    echo   3. Install Playwright browser on target machine (see above)
    echo   4. Double-click ToolXuLyMailCongVan.exe to launch
) else (
    echo.
    echo ❌ Build failed. Check error messages above.
)

pause
