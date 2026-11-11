@echo off
REM Sends one REAL configured Telegram alert. Uses the deployable runner;
REM no tests folder is required and no background schedulers are started.
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\send_telegram_test.py incwo-site-down
set "alert_result=%errorlevel%"
echo.
pause
exit /b %alert_result%
