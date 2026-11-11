@echo off
REM ============================================================
REM  Manually trigger the Site Down 24h Teams down-alert once, for testing.
REM  Sends a REAL card to whatever SITE_DOWN_24H_ALERT_WEBHOOK_URL is set
REM  in .env, for every currently-active Site Down incident over
REM  SITE_DOWN_24H_ALERT_THRESHOLD_HOURS that hasn't been down-alerted yet.
REM  Has a duplicate-send guard (the ledger) - running it twice in a row
REM  will NOT send a second real message for the same incident.
REM
REM  Self-contained - the Python code runs inline below, no separate
REM  tests\manual\*.py file needed (that folder isn't included in deploy
REM  zips, so this version works on the VM out of the box).
REM
REM  Lives in scripts\ - always runs from the project root.
REM ============================================================
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "from app import create_app; from app.services.incident.site_down_24h_alert_service import check_and_send_down_alerts; app = create_app(); ctx = app.app_context(); ctx.push(); sent = check_and_send_down_alerts(); print(f'sent={sent}')"

echo.
pause
