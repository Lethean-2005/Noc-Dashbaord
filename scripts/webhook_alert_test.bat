@echo off
REM ============================================================
REM  Manually trigger the Teams webhook alert(s), for testing.
REM  Sends REAL card(s) to whatever TEAMS_WEBHOOK_* URL(s) are set in .env.
REM  Leave the prompt blank and press Enter to send every configured
REM  alert (send-all), or type one key (see webhook\README.md's table,
REM  or run "python -m webhook list") to send just that one.
REM  Lives in scripts\ - always runs from the project root.
REM ============================================================
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

set /p KEY="Alert key (blank = send-all): "

if "%KEY%"=="" (
    ".venv\Scripts\python.exe" -m webhook send-all
) else (
    ".venv\Scripts\python.exe" -m webhook send %KEY%
)

echo.
pause
