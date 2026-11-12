@echo off
REM ============================================================
REM  Noc Dashboard - double-click to start everything.
REM  Runs the Flask app via the project's venv, then opens the
REM  browser once the server is up.
REM  Lives in scripts\ - always runs from the project root.
REM ============================================================
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found at .venv\Scripts\python.exe
    echo.
    echo Run these commands first:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)

REM The worker is an independent process and survives closing this web window.
".venv\Scripts\python.exe" scripts\ensure_sync_worker.py
if errorlevel 1 (
    echo Worker startup failed. Resolve the worker error before starting the dashboard.
    pause
    exit /b 1
)

for /f "tokens=2 delims==" %%p in ('findstr /b "PORT=" .env 2^>nul') do set "PORT=%%p"
if "%PORT%"=="" set "PORT=8000"

start "" cmd /c "timeout /t 5 >nul & start http://localhost:%PORT%/"

echo Starting Noc Dashboard on http://localhost:%PORT%/ ...
echo (Close this window to stop the dashboard.)
".venv\Scripts\python.exe" run.py --web-only

echo.
echo Dashboard stopped.
pause
