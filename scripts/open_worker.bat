@echo off
setlocal
title NOC_Worker
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Project Python was not found. Set up this project's .venv first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\ensure_sync_worker.py
if errorlevel 1 (
    pause
    exit /b 1
)
echo.
".venv\Scripts\python.exe" worker.py --status
echo.
echo This is a status snapshot. Run this icon again to refresh it.
echo The worker runs in the background. Closing this window does not stop it.
pause
