@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment missing. Set up .venv first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" worker.py
exit /b %errorlevel%
