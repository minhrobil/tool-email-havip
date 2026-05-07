@echo off
:: ─────────────────────────────────────────────────────────────────────────
:: build.bat  —  Build standalone Windows .exe with PyInstaller
::
:: Output: dist\ToolXuLyMailCongVan\ToolXuLyMailCongVan.exe
:: Also copies dist-ready helper scripts for Windows scheduling.
:: ─────────────────────────────────────────────────────────────────────────
chcp 65001 > nul
cd /d "%~dp0"

echo ================================================================
echo  Building ToolXuLyMailCongVan.exe ...
echo ================================================================

set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Khong tim thay venv\Scripts\python.exe.
    echo Chay setup.bat truoc khi build tren Windows.
    echo.
    pause
    exit /b 1
)

if not exist "packaging\windows\run_headless.dist.bat" (
    echo [ERROR] Khong tim thay packaging\windows\run_headless.dist.bat.
    pause
    exit /b 1
)

if not exist "packaging\windows\setup_scheduler.dist.bat" (
    echo [ERROR] Khong tim thay packaging\windows\setup_scheduler.dist.bat.
    pause
    exit /b 1
)

:: Install/update dependencies first
call "%PYTHON_EXE%" -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ❌ Dependency install failed.
    pause
    exit /b 1
)

:: Install Playwright browser (Chromium) — required for portal automation
call "%PYTHON_EXE%" -m playwright install chromium
if %errorlevel% neq 0 (
    echo.
    echo ❌ Playwright Chromium install failed.
    pause
    exit /b 1
)

:: Run PyInstaller
call "%PYTHON_EXE%" -m PyInstaller ^
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
    copy /y "config.json" "dist\ToolXuLyMailCongVan\config.json" > nul
    copy /y "packaging\windows\run_headless.dist.bat" "dist\ToolXuLyMailCongVan\run_headless.bat" > nul
    copy /y "packaging\windows\setup_scheduler.dist.bat" "dist\ToolXuLyMailCongVan\setup_scheduler.bat" > nul

    :: ── Bundle Playwright Chromium browser into the dist folder ──────────────
    :: Playwright (frozen EXE) looks for browsers in:
    ::   _internal\playwright\driver\package\.local-browsers\
    :: Copy from already-installed ms-playwright to avoid re-downloading.
    echo.
    echo Bundling Playwright Chromium into dist...
    set "BROWSERS_DEST=dist\ToolXuLyMailCongVan\_internal\playwright\driver\package\.local-browsers"
    if not exist "%BROWSERS_DEST%" mkdir "%BROWSERS_DEST%"

    set "COPIED=0"
    for /d %%D in ("%LOCALAPPDATA%\ms-playwright\chromium_headless_shell-*") do (
        echo   Copying %%~nxD ^(~265 MB^)...
        xcopy /E /I /Y /Q "%%D" "%BROWSERS_DEST%\%%~nxD" > nul
        set "COPIED=1"
    )
    if "%COPIED%"=="0" (
        echo   [WARNING] Chromium headless shell not found in %%LOCALAPPDATA%%\ms-playwright\
        echo   Users will need to install manually.
    ) else (
        echo   [OK] Chromium bundled.
    )

    echo.
    echo Build successful!
    echo.
    echo   Executable : dist\ToolXuLyMailCongVan\ToolXuLyMailCongVan.exe
    echo   Scheduler  : dist\ToolXuLyMailCongVan\setup_scheduler.bat
    echo.
    echo Deployment: Copy entire dist\ToolXuLyMailCongVan\ folder to target machine.
    echo             Chromium is bundled -- no additional setup needed.
    echo.
) else (
    echo.
    echo Build failed. Check error messages above.
)

pause
