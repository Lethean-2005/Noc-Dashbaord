@echo off
REM ============================================================
REM  Create the two desktop icons for the Noc Dashboard:
REM    - "Noc Dashboard"      starts the dashboard
REM    - "Dashboard Settings" opens the configurator
REM  No administrator rights needed. Safe to re-run any time
REM  (it also refreshes the Windows icon cache).
REM  Lives in scripts\ - the project root is one level up.
REM ============================================================
cd /d "%~dp0.."

powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut($d+'\Noc Dashboard.lnk'); $s.TargetPath='%~dp0start_dashboard.bat'; $s.WorkingDirectory='%CD%'; $s.IconLocation='%CD%\app\static\images\noc_dashboard.ico'; $s.Description='Start the Noc Dashboard'; $s.Save(); $s=$w.CreateShortcut($d+'\Dashboard Settings.lnk'); $s.TargetPath='%~dp0configure.bat'; $s.WorkingDirectory='%CD%'; $s.IconLocation='%CD%\app\static\images\noc_dashboard.ico'; $s.Description='Open the Noc Dashboard settings window'; $s.Save()"

REM Refresh the Windows icon cache so the new icons show correctly.
ie4uinit.exe -show 2>nul

echo.
echo Done. Two icons were added to your Desktop:
echo   - Noc Dashboard       (starts the dashboard)
echo   - Dashboard Settings  (opens the configurator)
pause
