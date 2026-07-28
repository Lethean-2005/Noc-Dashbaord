@echo off
REM Open the Noc Dashboard configuration window (card toggles, sync intervals, alerts).
REM Lives in scripts\ - always runs from the project root.
cd /d "%~dp0.."

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" configurator.py
) else (
    start "" pythonw configurator.py
)
