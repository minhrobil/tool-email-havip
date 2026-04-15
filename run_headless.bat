@echo off
:: ─────────────────────────────────────────────────────────────────────────
:: run_headless.bat  —  Run Công Văn Processor without GUI
:: Used by Windows Task Scheduler for automatic daily execution.
:: ─────────────────────────────────────────────────────────────────────────
chcp 65001 > nul
cd /d "%~dp0"

if exist venv\Scripts\python.exe (
    set PYTHON=venv\Scripts\python.exe
) else (
    set PYTHON="C:\Program Files\Python312\python.exe"
)

set LOGFILE=%~dp0_scheduler_run.log
echo [%DATE% %TIME%] Starting headless run >> "%LOGFILE%"

%PYTHON% run_app.py --headless --log-file "%LOGFILE%"

if %errorlevel% equ 0 (
    echo [%DATE% %TIME%] Completed successfully >> "%LOGFILE%"
) else if %errorlevel% equ 2 (
    echo [%DATE% %TIME%] ERROR: Not signed in. Please run run.bat first. >> "%LOGFILE%"
) else (
    echo [%DATE% %TIME%] Completed with errors (exit code %errorlevel%) >> "%LOGFILE%"
)

