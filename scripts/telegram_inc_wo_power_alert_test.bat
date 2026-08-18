@echo off
REM ============================================================
REM  Manually trigger the Telegram INC-WO Category Power alert once, for
REM  testing. Sends a REAL message (via TELEGRAM_BOT_INC_WO_POWER_TOKEN) to
REM  whatever TELEGRAM_CHAT_IDS_INC_WO_POWER is set in .env if anything is
REM  over threshold. The bot must already be a member of that chat.
REM  Run it twice in a row to see that there's no duplicate-send guard -
REM  see telegram_inc_wo_power_alert_test.py's header for why.
REM  Lives in scripts\ - always runs from the project root.
REM ============================================================
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

".venv\Scripts\python.exe" tests\manual\telegram_inc_wo_power_alert_test.py

echo.
pause
