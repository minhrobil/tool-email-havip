@echo off
setlocal
:: ─────────────────────────────────────────────────────────────────────────
:: run.bat  —  Launch Công Văn Processor (GUI mode)
:: Double-click this file to start the application.
:: ─────────────────────────────────────────────────────────────────────────
chcp 65001 > nul
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Khong tim thay Windows virtual environment tai venv\.
    echo Chay setup.bat truoc.
    echo.
    pause
    exit /b 1
)

echo Starting Cong Van Processor...
call "%PYTHON_EXE%" run_app.py %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Application exited with error. Check the log above.
    echo Neu day la may moi, hay cai dependencies va Playwright Chromium truoc khi chay.
    pause
)

exit /b %EXIT_CODE%
