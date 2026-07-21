@echo off
:: ─────────────────────────────────────────────────────────────────────────
:: setup.bat  —  Windows source setup for Cong Van Processor
:: ─────────────────────────────────────────────────────────────────────────
chcp 65001 > nul
cd /d "%~dp0"

set "PYTHON=py -3"

echo ================================================================
echo  Cong Van Processor - Windows Source Setup
echo ================================================================
echo.

:: ── Step 1: Verify Python ─────────────────────────────────────────────────
echo [1/5] Checking Python...
%PYTHON% --version
if %errorlevel% neq 0 (
    echo ERROR: Python Launcher not found. Install Python 3.10+ with py launcher.
    pause & exit /b 1
)
%PYTHON% -c "import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if %errorlevel% neq 0 (
    echo ERROR: Python 3.10+ with tkinter is required.
    echo Install Python from python.org and enable Tcl/Tk support.
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
call venv\Scripts\python.exe -c "import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if %errorlevel% neq 0 (
    echo ERROR: Existing venv is not Python 3.10+ with tkinter.
    echo Delete the venv folder and run setup.bat again.
    pause & exit /b 1
)

:: ── Step 3: Install dependencies ─────────────────────────────────────────
echo.
echo [3/5] Installing Python dependencies...
call venv\Scripts\pip.exe install -r requirements.txt
if %errorlevel% neq 0 ( echo ERROR installing dependencies & pause & exit /b 1 )
call venv\Scripts\pip.exe install pytest
if %errorlevel% neq 0 ( echo ERROR installing pytest & pause & exit /b 1 )

:: ── Step 3.5: Check Tesseract OCR ─────────────────────────────────────────
echo.
echo [3.5] Checking Tesseract OCR (required for scanned PDFs)...
where tesseract >nul 2>&1
if %errorlevel% neq 0 (
    echo   Tesseract not found. Installing via winget...
    winget install --id UB-Mannheim.TesseractOCR -e --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo.
        echo   WARNING: winget install failed. Install manually:
        echo     https://github.com/UB-Mannheim/tesseract/wiki
        echo   Then download vie.traineddata to Tesseract's tessdata folder:
        echo     https://github.com/tesseract-ocr/tessdata_best
        echo.
    ) else (
        echo   Tesseract installed. Add to PATH if needed, then restart terminal.
        echo   Also download vie.traineddata to Tesseract's tessdata folder:
        echo     https://github.com/tesseract-ocr/tessdata_best
    )
) else (
    echo   Tesseract found: OK
)

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
