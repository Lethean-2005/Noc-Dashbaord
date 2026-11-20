@echo off
setlocal
REM ============================================================
REM  Create the desktop icons for the Noc Dashboard:
REM    - "Noc Dashboard"      starts the dashboard
REM    - "Dashboard Settings" opens the configurator
REM    - "NOC_Worker" starts or shows the background worker
REM  No administrator rights needed. Safe to re-run any time
REM  (it also refreshes the Windows icon cache).
REM  Lives in scripts\ - the project root is one level up.
REM ============================================================
cd /d "%~dp0.."
set "NOC_SHORTCUT_ROOT=%CD%"

powershell -NoProfile -Command "$root=$env:NOC_SHORTCUT_ROOT; $desktop=[Environment]::GetFolderPath('Desktop'); $shell=New-Object -ComObject WScript.Shell; foreach($item in @(@('Noc Dashboard','start_dashboard.bat'),@('Dashboard Settings','configure.bat'),@('NOC_Worker','open_worker.bat'))){ $link=$shell.CreateShortcut((Join-Path $desktop ($item[0]+'.lnk'))); $link.TargetPath=Join-Path $root ('scripts\'+$item[1]); $link.WorkingDirectory=$root; $link.IconLocation=Join-Path $root 'app\static\images\noc_dashboard.ico'; $link.Description=$item[0]; $link.Save() }"
if errorlevel 1 (
    echo Could not create desktop shortcuts.
    pause
    exit /b 1
)

REM Refresh the Windows icon cache so the new icons show correctly.
ie4uinit.exe -show 2>nul

echo.
echo Done. Three icons were added to your Desktop:
echo   - Noc Dashboard       (starts the dashboard)
echo   - Dashboard Settings  (opens the configurator)
echo   - NOC_Worker          (starts or shows the background worker)
pause
