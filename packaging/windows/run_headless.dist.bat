@echo off
setlocal
chcp 65001 > nul
cd /d "%~dp0"

set "EXE_PATH=%~dp0ToolXuLyMailCongVan.exe"
set "LOGFILE=%~dp0_scheduler_run.log"

if not exist "%EXE_PATH%" (
    echo [%DATE% %TIME%] ERROR: ToolXuLyMailCongVan.exe not found >> "%LOGFILE%"
    exit /b 1
)

echo [%DATE% %TIME%] Starting headless run >> "%LOGFILE%"
"%EXE_PATH%" --headless --log-file "%LOGFILE%"
set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="0" (
    echo [%DATE% %TIME%] Completed successfully >> "%LOGFILE%"
) else (
    echo [%DATE% %TIME%] Completed with errors (exit code %EXIT_CODE%) >> "%LOGFILE%"
)

exit /b %EXIT_CODE%
