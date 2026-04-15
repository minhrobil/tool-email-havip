@echo off
:: ─────────────────────────────────────────────────────────────────────────
:: setup.bat  —  First-time environment setup for Cong Van Processor
:: Uses Python at C:\Program Files\Python312\python.exe
:: Run this ONCE before using the application.
:: ─────────────────────────────────────────────────────────────────────────
chcp 65001 > nul
cd /d "%~dp0"

set PYTHON="C:\Program Files\Python312\python.exe"

echo ================================================================
echo  Cong Van Processor - First-time Setup
echo ================================================================
echo.

:: ── Step 1: Verify Python ─────────────────────────────────────────────────
echo [1/5] Checking Python...
%PYTHON% --version
if %errorlevel% neq 0 (
    echo ERROR: Python not found at C:\Program Files\Python312\python.exe
    pause & exit /b 1
)

:: ── Step 2: Create virtual environment ────────────────────────────────────
echo.
echo [2/5] Creating virtual environment in .\venv\ ...
if exist venv (
    echo   venv already exists, skipping creation.
) else (
    %PYTHON% -m venv venv
    if %errorlevel% neq 0 ( echo ERROR creating venv & pause & exit /b 1 )
    echo   venv created.
)

:: ── Step 3: Install dependencies ─────────────────────────────────────────
echo.
echo [3/5] Installing Python dependencies...
call venv\Scripts\pip.exe install -r requirements.txt
if %errorlevel% neq 0 ( echo ERROR installing dependencies & pause & exit /b 1 )

:: ── Step 4: Install Playwright Chromium browser ───────────────────────────
echo.
echo [4/5] Installing Playwright Chromium browser (may take a few minutes)...
call venv\Scripts\playwright.exe install chromium
if %errorlevel% neq 0 ( echo ERROR installing Playwright browser & pause & exit /b 1 )

:: ── Step 5: Run tests ─────────────────────────────────────────────────────
echo.
echo [5/5] Running tests to verify installation...
call venv\Scripts\python.exe -m pytest tests/ -v --tb=short
if %errorlevel% neq 0 (
    echo.
    echo WARNING: Some tests failed. Check output above.
    echo The application may still work — tests are verification only.
) else (
    echo.
    echo All tests passed!
)

echo.
echo ================================================================
echo  Setup complete!
echo ================================================================
echo.
echo NEXT STEPS:
echo   1. Edit config.json  -^>  set azure.client_id
echo      (See README.md -^> Azure App Registration for instructions)
echo.
echo   2. Double-click run.bat to launch the application
echo.
echo   3. Click "Dang nhap Microsoft" to sign in once
echo.
echo   4. Click "Quet mail" to start processing
echo.
pause

