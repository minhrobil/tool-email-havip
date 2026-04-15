@echo off
:: ─────────────────────────────────────────────────────────────────────────
:: run.bat  —  Launch Công Văn Processor (GUI mode)
:: Double-click this file to start the application.
:: ─────────────────────────────────────────────────────────────────────────
chcp 65001 > nul
cd /d "%~dp0"

:: Use venv Python if available, otherwise fall back to system Python
if exist venv\Scripts\python.exe (
    set PYTHON=venv\Scripts\python.exe
) else (
    set PYTHON="C:\Program Files\Python312\python.exe"
    echo NOTE: Virtual environment not found. Run setup.bat first for best results.
)

echo Starting Cong Van Processor...
%PYTHON% run_app.py

if %errorlevel% neq 0 (
    echo.
    echo Application exited with error. Check the log above.
    echo If this is the first run, make sure to run setup.bat first.
    pause
)

