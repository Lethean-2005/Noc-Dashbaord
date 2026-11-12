> Dedicated worker update: `python run.py` and `scripts/start_dashboard.bat` ensure the independent worker is running. `python run.py --web-only` serves HTTP only when another task/service manages the worker. Before replacing worker code, run `.venv\Scripts\python.exe worker.py --stop` and stop the web server; preserve `.env` and `instance/`. After launch, check `/api/v1/system/sync`. For automatic worker recovery, explicitly install `scripts/install_sync_worker_task.ps1`; its default trigger is current-user logon, not unattended boot. See `docs/sync-worker.md` in the repository for complete operations guidance.

# VM Setup

Commands to get the dashboard running on this VM, in order. Run each
command one at a time — don't chain them with `&`. See **Troubleshooting**
at the bottom if any step doesn't behave as described.

## Updating an existing VM installation

1. Stop the old dashboard before copying files or its SQLite database.
2. Extract the new ZIP into a new folder.
3. Copy the old `.env` file and the entire old `instance/` folder into the new
   `Noc-Dashboard/` folder, next to `run.py`. Both are required; neither is in the ZIP.
4. Create the virtual environment and install `requirements.txt` using the setup
   steps below. Virtual environments should be recreated when changing folders.
5. Start only the new dashboard. Wait for its next successful cache sync and
   refresh the browser with Ctrl+F5.

Keep the old folder as a backup. Do not run both versions together: both could
send alerts. Existing saved data and alert history are retained through `instance/`;
normal incident/alarm caches continue refreshing from the source systems.

## Step 1 — Unzip

Extract the deploy zip anywhere on the VM (e.g. `E:\Noc-Dashboard`).

For an upgrade, keep the VM's existing `.env` and entire `instance/` folder.
They contain connection settings, alert history, congestion exclusions, Mentor
sites, and saved reports/uploads. The ZIP excludes them. Extract the application
files into the existing project folder; do not replace it with an empty folder.
Back up `.env` and `instance/` before upgrading, then restart the application.

## Step 2 — Stop the dashboard

If a `start_dashboard.bat` window is already running from a previous
install, close it (or stop `run.py` however it's running). Skip this on a
brand-new VM with nothing running yet.

## Step 3 — Confirm Python 3.14

```
python --version
```

Should print `Python 3.14.10`. `requirements.txt` needs Python 3.11+. If
this prints an older version or fails, install Python 3.14 first — no
admin rights needed, via `uv` (see **Troubleshooting**) — then come back
to this step.

## Step 4 — Back up the old `.venv` (only if one exists)

Check first:

**CMD/PowerShell:**
```
dir .venv
```

**MobaXterm bash:**
```bash
ls
```

**No `.venv` listed** (fresh extraction, nothing built here yet) — skip
straight to Step 5, nothing to back up.

**`.venv` listed** — back it up before overwriting it:

**CMD/PowerShell:**
```
move .venv .venv_py39_backup
```

**MobaXterm bash:**
```bash
mv .venv .venv_py39_backup
```

## Step 5 — Create the virtual environment

```
python -m venv .venv
```

## Step 6 — Upgrade pip

**CMD/PowerShell:**
```
.venv\Scripts\python.exe -m pip install --upgrade pip
```

**MobaXterm bash** (backslashes don't work as path separators in bash —
always use forward slashes there):
```bash
.venv/Scripts/python.exe -m pip install --upgrade pip
```

## Step 7 — Install dependencies

**CMD/PowerShell:**
```
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**MobaXterm bash:**
```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

## Step 8 — Smoke-test the install

**CMD/PowerShell:**
```
.venv\Scripts\python.exe -c "import flask, PIL, pillow_heif, requests, dotenv; print('Imports OK')"
```

**MobaXterm bash:**
```bash
.venv/Scripts/python.exe -c "import flask, PIL, pillow_heif, requests, dotenv; print('Imports OK')"
```

Should print `Imports OK`.

## Step 9 — Start the dashboard

**CMD/PowerShell:**
```
scripts\start_dashboard.bat
```

**MobaXterm bash:**
```bash
scripts/start_dashboard.bat
```

Opens `http://localhost:<PORT>/` in the browser automatically after a few
seconds. Confirm the pages you use load correctly — including a photo
upload on the Incident Report page, to confirm HEIC still decodes.

## Step 10 — Clean up the backup

**CMD/PowerShell:**
```
rmdir /s /q .venv_py39_backup
```

**MobaXterm bash:**
```bash
rm -rf .venv_py39_backup
```

Only once you're confident the dashboard is stable. Reclaims disk space.

## Step 11 — Optional: desktop shortcuts

**CMD/PowerShell:**
```
scripts\create_shortcuts.bat
```

**MobaXterm bash:**
```bash
scripts/create_shortcuts.bat
```

Adds two Desktop icons: **Noc Dashboard** (starts it) and **Dashboard
Settings** (opens `configurator.py`).

## Step 12 — Optional: configuration

**CMD/PowerShell:**
```
scripts\configure.bat
```

**MobaXterm bash:**
```bash
scripts/configure.bat
```

Opens a settings window to toggle dashboard cards and edit sync/alert
intervals — saves back to `.env`. Card visibility applies live; sync/alert
changes need the dedicated worker restarted.

## Step 13 - Optional: automatic worker startup and recovery

For a normal signed-in Windows user, run PowerShell explicitly:

```powershell
.\scripts\install_sync_worker_task.ps1
Start-ScheduledTask -TaskName NocDashboardSyncWorker
```

This installs a dedicated worker task at user logon with one-minute restart after failure. It does not install or start automatically during a ZIP update. Start the website separately with the existing dashboard shortcut. The worker and web server are separate processes.

For unattended VM boot, ask the VM administrator to register separate boot-time tasks/services: one executes the project's `.venv\Scripts\python.exe worker.py`, the other executes `.venv\Scripts\python.exe run.py --web-only`, both with the project as working directory and an account that can access the configured source systems. Do not manage both through one parent task if independent restarts are required. The provided default installer uses interactive user logon, not a SYSTEM account or stored password.

If older boot automation launches the combined dashboard batch file, review it when adopting separate process supervision. Stop old embedded schedulers before the first worker starts. On folder changes, update task paths; keeping a stable installation folder avoids this.

---

## Troubleshooting

### Installing Python 3.14 (no admin rights needed)

The official python.org installer needs Administrator rights and is
blocked by this VM's Group Policy. Install per-user via `uv` instead, from
MobaXterm bash:

```bash
export PATH="/drives/c/Users/svc_nocremote/.local/bin:$PATH"
uv python install 3.14 --default
echo 'export PATH="/drives/c/Users/svc_nocremote/.local/bin:$PATH"' >> ~/.bashrc
```

Then open a **new** CMD/PowerShell window and re-run Step 3. If plain
`python` ever shows the old 3.9 instead of 3.14, use `python3.14`
explicitly, or the full path
`C:\Users\svc_nocremote\.local\bin\python3.14.exe` — that always works
regardless of PATH ordering. The old Python 3.9 is never removed; 3.14
installs alongside it.

### "This installation is forbidden by system policy" (error `0x80070659`)

That's the Group Policy block mentioned above — use the `uv` steps instead
of the official installer.

### Step 5 fails, or mixes old and new packages

Don't skip Step 4 and create `.venv` directly over an existing one —
Python's `venv` module doesn't fully wipe the target directory by default,
so you'd get the new 3.14 interpreter mixed with old 3.9-compiled packages
(breaks with ABI/import errors). If you don't want to keep a backup copy,
use `python -m venv .venv --clear` instead of Steps 4+5 — `--clear` forces
a real wipe with no rollback copy.

### "Could not rename .venv - is the dashboard still running?"

Something still has a file inside `.venv` open — go back to Step 2 and
confirm every `python.exe run.py` process is actually stopped (check Task
Manager if closing the window didn't seem to work).

### A previous `.venv_py39_backup` already exists

Rename or delete the old one first if you're sure it's no longer needed,
then retry Step 4.

### Step 7 fails with "Could not find a version that satisfies ..."

The VM's package index doesn't have that exact pinned version. The error
lists every version it actually has — pick one, update `requirements.txt`
(and `pyproject.toml`'s matching `>=` line), then re-run Step 7.

### Step 7 fails trying to compile a package (e.g. `greenlet`)

Check whether a prebuilt wheel exists at all, without touching the pin
(CMD/PowerShell shown — in bash, use `.venv/Scripts/python.exe` instead):
```
.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
```
Succeeds → the problem was pip's resolver, make sure Step 6 actually ran,
then retry Step 7 normally. Fails too → pin the package to a version
confirmed to have a wheel, or install "Microsoft C++ Build Tools" from the
URL in the error.

### Run the Step 4–8 rebuild as one script instead

`scripts\upgrade_python_vm.bat` automates Steps 4–8, pausing for a Y/N
confirmation before each change. No admin rights needed. It checks for
`python3.14` specifically (not plain `python`), so it works correctly even
on a window where PATH ordering differs.

### Activating `.venv` instead of calling `python.exe` directly

Every command above calls `.venv\Scripts\python.exe` directly rather than
activating first — works the same either way. To activate instead:
Command Prompt: `.venv\Scripts\activate`. Git Bash: the generated
`activate` script can have CRLF issues (`$'\r': command not found`) — fix
with `sed -i 's/\r$//' .venv/Scripts/activate` first, or just keep calling
`.venv/Scripts/python.exe` directly, which is what
`scripts\start_dashboard.bat` does internally anyway.


Source-system links use `STREAMLINE_BASE_URL` (default: the existing Streamline
address). Keep this setting in the VM environment when changing code. Dashboard,
exports and alerts share it. Application/display time is fixed to
`Asia/Phnom_Penh` (UTC+7), independent of the browser/PC timezone.


Telegram manual test buttons run scripts/send_telegram_test.py, which ships in
the deployment ZIP. They do not require tests/manual and do not start background
schedulers. The Site Down Alert (Over 4Hours) uses TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_IDS; ALERT_THRESHOLD_MIN=240 selects four hours. Adding a member
to the existing Telegram group does not change these settings.

To check the runner without sending: .venv\Scripts\python.exe
scripts\send_telegram_test.py site-down --dry-run. Normal launchers send real
alerts using the existing synced cache. Start the dashboard and complete its
first sync before testing on a fresh VM.
