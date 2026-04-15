@echo off
setlocal
chcp 65001 > nul
cd /d "%~dp0"

echo ================================================================
echo  Tool Xu Ly Mail Cong Van - Task Scheduler Setup
echo ================================================================
echo.

set "TASK_NAME=ToolXuLyMailCongVan"
set "RUN_TIME=08:00"
set "HEADLESS_BAT=%~dp0run_headless.bat"
set "TASK_CMD=%COMSPEC% /d /c ""%HEADLESS_BAT%"""
set "RUN_AS=%USERDOMAIN%\%USERNAME%"

if not exist "%HEADLESS_BAT%" (
    echo [ERROR] Khong tim thay run_headless.bat trong thu muc dist.
    pause
    exit /b 1
)

echo This will create a daily scheduled task named "%TASK_NAME%".
echo The task will run every day at %RUN_TIME% using the current user account.
echo.
echo Requirements:
echo  - Sign in first using ToolXuLyMailCongVan.exe
echo  - Keep this folder in a stable location after scheduling
echo.

schtasks /query /tn "%TASK_NAME%" > nul 2>&1
if %errorlevel% equ 0 (
    echo Task "%TASK_NAME%" already exists. Updating...
    schtasks /delete /tn "%TASK_NAME%" /f > nul 2>&1
)

schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "%TASK_CMD%" ^
  /sc DAILY ^
  /st %RUN_TIME% ^
  /ru "%RUN_AS%" ^
  /rl HIGHEST ^
  /f ^
  /it

if %errorlevel% equ 0 (
    echo.
    echo Task Scheduler job created successfully.
    echo   Task name : %TASK_NAME%
    echo   Runs at   : %RUN_TIME% every day
    echo   Command   : %TASK_CMD%
) else (
    echo.
    echo Failed to create task. Make sure to run this script with sufficient permissions.
)

echo.
pause
