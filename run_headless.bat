@echo off
setlocal
:: ─────────────────────────────────────────────────────────────────────────
:: run_headless.bat  —  Run Công Văn Processor without GUI
:: Used by Windows Task Scheduler for automatic daily execution.
:: ─────────────────────────────────────────────────────────────────────────
chcp 65001 > nul
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Khong tim thay Windows virtual environment tai venv\.
    echo Chay setup.bat truoc.
    exit /b 1
)

set "LOGFILE=%~dp0_scheduler_run.log"
echo [%DATE% %TIME%] Starting headless run >> "%LOGFILE%"

call "%PYTHON_EXE%" run_app.py --headless --log-file "%LOGFILE%" %*
set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="0" (
    echo [%DATE% %TIME%] Completed successfully >> "%LOGFILE%"
) else if "%EXIT_CODE%"=="2" (
    echo [%DATE% %TIME%] ERROR: Not signed in. Please run run.bat first. >> "%LOGFILE%"
) else (
    echo [%DATE% %TIME%] Completed with errors (exit code %EXIT_CODE%) >> "%LOGFILE%"
)

exit /b %EXIT_CODE%
