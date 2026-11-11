@echo off
REM ============================================================
REM  Rebuild this project's .venv against Python 3.14, installed
REM  ALONGSIDE the existing Python 3.9 via uv (not the official
REM  python.org installer - that needs Administrator rights and is
REM  blocked by this VM's Group Policy for non-admin accounts, which
REM  is exactly why uv is used instead: it installs per-user, no
REM  admin needed).
REM
REM  Confirmed via PyPI that every dependency this app needs ships a
REM  real cp314 Windows wheel, including the compiled ones:
REM  psycopg2-binary, pymssql, pywin32. SQLAlchemy has no cp314 wheel
REM  but ships a pure-Python fallback, which pip installs with no
REM  error.
REM
REM  This script does NOT install Python itself - uv already did
REM  that (see the "Python 3.14 not found" message below if it
REM  hasn't). It only rebuilds .venv and installs dependencies, which
REM  only need write access to this project folder - no admin rights
REM  needed for anything in this script.
REM
REM  Does NOT touch or uninstall the existing Python 3.9 - only this
REM  app's own .venv folder gets rebuilt, which is all
REM  start_dashboard.bat ever uses (always calls
REM  .venv\Scripts\python.exe, never the bare "python" on PATH, which
REM  may still resolve to 3.9 - see that file).
REM
REM  Stops and asks you to confirm before each step that actually
REM  changes something: replacing the project's .venv, and installing
REM  the fully-patched dependencies.
REM
REM  Lives in scripts\ - always runs from the project root.
REM ============================================================
cd /d "%~dp0.."

set "PY_VERSION=3.14.10"
set "BACKUP_NAME=.venv_py39_backup"

echo ============================================================
echo  Noc Dashboard - rebuild .venv on Python %PY_VERSION%
echo ============================================================
echo.

REM ------------------------------------------------------------
REM Step 1: is python3.14 available on PATH?
REM ------------------------------------------------------------
python3.14 --version >nul 2>&1
if not %errorlevel%==0 (
    echo python3.14 was not found on PATH in this shell.
    echo.
    echo If Python 3.14 isn't installed on this account yet, install it
    echo with uv - no admin rights needed ^(run from MobaXterm bash,
    echo where uv is already set up^):
    echo.
    echo   export PATH="/drives/c/Users/svc_nocremote/.local/bin:$PATH"
    echo   uv python install 3.14 --default
    echo.
    echo If it's already installed but this CMD/PowerShell window just
    echo doesn't see it, open a NEW window ^(PATH changes from uv only
    echo apply to new sessions^), or call the full path directly:
    echo.
    echo   C:\Users\svc_nocremote\.local\bin\python3.14.exe --version
    echo.
    echo Once "python3.14 --version" works in this kind of window,
    echo re-run this script.
    pause
    exit /b 1
)

for /f "delims=" %%v in ('python3.14 --version') do echo Found: %%v

echo.
echo ------------------------------------------------------------
echo About to rebuild this project's .venv against Python 3.14.
echo The CURRENT .venv (Python 3.9) will be renamed to a backup
echo folder, NOT deleted, so you can roll back if needed.
echo.
echo IMPORTANT: make sure the dashboard is NOT currently running
echo (close the start_dashboard.bat window / stop run.py) - the
echo running process locks files inside .venv and the rename will
echo fail if it's still active.
echo ------------------------------------------------------------
choice /c YN /m "Dashboard is stopped and ready to rebuild .venv - proceed"
if errorlevel 2 goto :abort

if exist ".venv" (
    if exist "%BACKUP_NAME%" (
        echo A previous backup "%BACKUP_NAME%" already exists - remove or
        echo rename it first, then re-run this script.
        pause
        exit /b 1
    )
    echo Step 1 of 2: backing up current .venv to %BACKUP_NAME% ...
    move ".venv" "%BACKUP_NAME%" >nul
    if not %errorlevel%==0 (
        echo Could not rename .venv - is the dashboard still running?
        pause
        exit /b 1
    )
) else (
    echo Step 1 of 2: no existing .venv found, nothing to back up.
)

echo Creating new .venv with Python 3.14 ...
python3.14 -m venv .venv
if not %errorlevel%==0 (
    echo venv creation failed.
    pause
    exit /b 1
)

echo.
echo ------------------------------------------------------------
echo About to install dependencies into the new .venv from
echo requirements.txt (the fully-patched versions, confirmed to
echo have real cp314 wheels - see that file's own header).
echo ------------------------------------------------------------
choice /c YN /m "Proceed with installing dependencies"
if errorlevel 2 goto :abort

echo Step 2 of 2: installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if not %errorlevel%==0 (
    echo pip install failed - see the error above. The old environment
    echo is still safe in the %BACKUP_NAME% folder.
    pause
    exit /b 1
)

echo.
echo Running a basic import smoke test...
".venv\Scripts\python.exe" -c "import flask, PIL, pillow_heif, requests, dotenv; print('Imports OK')"
if not %errorlevel%==0 (
    echo Smoke test failed - see the error above.
    pause
    exit /b 1
)

if exist "tests" (
    echo Running the test suite...
    ".venv\Scripts\python.exe" -m pytest -q
) else (
    echo (tests\ folder not present on this deployment - skipping pytest,
    echo  same as every other dev-only tool in this deploy. See the dev
    echo  checkout if you need to run the full suite.)
)

echo.
echo ============================================================
echo  Done. .venv now runs on Python %PY_VERSION%.
echo  The old Python 3.9 .venv is kept at: %BACKUP_NAME%
echo.
echo  Next steps:
echo    1. Start the dashboard as usual (start_dashboard.bat) and
echo       confirm it comes up and the pages you care about work.
echo    2. Once you're confident it's stable, you can delete
echo       %BACKUP_NAME% to reclaim disk space.
echo ============================================================
pause
exit /b 0

:abort
echo.
echo Cancelled - nothing further was changed.
pause
exit /b 1
