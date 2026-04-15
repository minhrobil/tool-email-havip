@echo off
:: ─────────────────────────────────────────────────────────────────────────
:: setup_scheduler.bat  —  Register daily Task Scheduler job
::
:: Run this script ONCE as Administrator to schedule automatic daily runs.
:: The task will run at 08:00 every day.
::
:: Auto-detects mode:
::   - If dist\ToolXuLyMailCongVan\ToolXuLyMailCongVan.exe exists → dùng .exe
::   - Otherwise → dùng run_headless.bat (cần Python)
:: ─────────────────────────────────────────────────────────────────────────
chcp 65001 > nul

echo ================================================================
echo  Tool Xu Ly Mail Cong Van - Task Scheduler Setup
echo ================================================================
echo.

set TASK_NAME=ToolXuLyMailCongVan
set TASK_DESC=Tu dong xu ly email cong van hang ngay luc 8:00 sang
set RUN_TIME=08:00
set EXE_PATH=%~dp0dist\ToolXuLyMailCongVan\ToolXuLyMailCongVan.exe
set LOG_FILE=%~dp0_scheduler_run.log

:: ── Auto-detect: .exe hoặc Python script ──────────────────────────────────
if exist "%EXE_PATH%" (
    echo [MODE] Dung ban .exe da build:
    echo        %EXE_PATH%
    set TASK_CMD="%EXE_PATH%" --headless --log-file "%LOG_FILE%"
) else (
    echo [MODE] Dung Python script (run_headless.bat):
    echo        %~dp0run_headless.bat
    echo.
    echo NOTE: Chua tim thay .exe. Neu muon dung .exe, chay build.bat truoc.
    set TASK_CMD="%~dp0run_headless.bat"
)

echo.
echo This will create a daily scheduled task named "%TASK_NAME%".
echo The task will run every day at %RUN_TIME% using the current user account.
echo.
echo Requirements:
echo  - Run this script as Administrator
echo  - Sign in first using the app GUI (needed once to cache credentials)
echo.

:: ── Check if task already exists ──────────────────────────────────────────
schtasks /query /tn "%TASK_NAME%" > nul 2>&1
if %errorlevel% equ 0 (
    echo Task "%TASK_NAME%" already exists. Updating...
    schtasks /delete /tn "%TASK_NAME%" /f > nul 2>&1
)

:: ── Create the task ────────────────────────────────────────────────────────
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "%TASK_CMD%" ^
  /sc DAILY ^
  /st %RUN_TIME% ^
  /ru "%USERNAME%" ^
  /rl HIGHEST ^
  /f ^
  /sd %DATE% ^
  /it

if %errorlevel% equ 0 (
    echo.
    echo ✅ Task Scheduler job created successfully!
    echo.
    echo   Task name : %TASK_NAME%
    echo   Runs at   : %RUN_TIME% every day
    echo   Command   : %TASK_CMD%
    echo   Log file  : %LOG_FILE%
    echo.
    echo To view the task:  Open Task Scheduler → Task Scheduler Library
    echo To remove task  :  schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo.
    echo ❌ Failed to create task. Make sure to run this script as Administrator.
)

echo.
pause
