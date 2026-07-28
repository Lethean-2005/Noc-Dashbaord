@echo off
REM ============================================================
REM  Manually trigger the Telegram Site Down alert once, for testing.
REM  Sends a REAL message to whatever TELEGRAM_CHAT_IDS is set in .env
REM  (currently the -5532478916 group) if anything is over threshold.
REM  Run it twice in a row to see that there's no duplicate-send guard -
REM  see scripts\telegram_alert_test.py's header for why.
REM  Lives in scripts\ - always runs from the project root.
REM ============================================================
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

".venv\Scripts\python.exe" telegram_alert_test.py

echo.
pause
