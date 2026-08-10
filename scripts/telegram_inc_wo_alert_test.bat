@echo off
REM ============================================================
REM  Manually trigger the Telegram INC-WO Site Down alert once, for
REM  testing. Sends a REAL message (via TELEGRAM_BOT_INC_WO_TOKEN) to
REM  whatever TELEGRAM_CHAT_IDS_INC_WO is set in .env if anything is over
REM  threshold. The bot must already be a member of that chat.
REM  Run it twice in a row to see that there's no duplicate-send guard -
REM  see scripts\telegram_inc_wo_alert_test.py's header for why.
REM  Lives in scripts\ - always runs from the project root.
REM ============================================================
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

".venv\Scripts\python.exe" telegram_inc_wo_alert_test.py

echo.
pause
