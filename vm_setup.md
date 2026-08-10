# VM Setup

Commands to get the dashboard running on a fresh VM, in order. Run each
command one at a time — don't chain them with `&`.

## 1. Unzip

Extract the deploy zip anywhere on the VM (e.g. `E:\Noc-Dashboard`).

## 2. Create the virtual environment

```
python -m venv .venv
```

If this fails with a path error, check that `python` on PATH is a real
Python install (not a Windows Store alias) and that the account running it
has write access to the folder.

## 3. Activate it

**Command Prompt:**
```
.venv\Scripts\activate
```

**Git Bash:** the generated `activate` script can have CRLF line endings
that break `source` in bash (`$'\r': command not found`). Either fix it
once —
```bash
sed -i 's/\r$//' .venv/Scripts/activate
source .venv/Scripts/activate
```
— or skip activation entirely and call the venv's Python directly by path
for every command below (`.venv/Scripts/python.exe ...`), which sidesteps
the issue completely and is what `scripts/start_dashboard.bat` does
internally anyway.

## 4. Upgrade pip first

The VM's default pip is often old enough (e.g. 21.1.3) that it fails to
pick a prebuilt wheel for some packages and tries to compile from source
instead — which then fails with `Microsoft Visual C++ 14.0 or greater is
required` if no compiler is installed. Upgrading pip first avoids this:

```
.venv/Scripts/python.exe -m pip install --upgrade pip
```

## 5. Install dependencies

```
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

### If a package fails with "Could not find a version that satisfies ..."

The VM's package index doesn't have that exact pinned version (this
happened with `requests==2.34.2` and `PySide6==6.11.1` — both too new for
this VM's mirror). The error lists every version the VM's index actually
has, e.g.:

```
ERROR: Could not find a version that satisfies the requirement requests==2.34.2
(from versions: ..., 2.32.5, 2.32.4, 2.32.3, ...)
```

Pick a version from that list, update `requirements.txt` (and
`pyproject.toml`'s matching `>=` line), then re-run the install.

### If a package fails trying to compile (e.g. `greenlet`)

First check whether a prebuilt wheel exists at all, without touching the
version pin:

```
.venv/Scripts/python.exe -m pip install --only-binary=:all: -r requirements.txt
```

- If that **succeeds**, the problem was pip's resolver, not a missing
  wheel — make sure step 4 (pip upgrade) actually ran, then retry the full
  `pip install -r requirements.txt`.
- If that **fails too**, pin the package to a specific version confirmed
  to have a wheel (same approach as the previous section), or as a last
  resort install "Microsoft C++ Build Tools" from the URL in the error.

## 6. Start the dashboard

```
scripts\start_dashboard.bat
```

Run this from Command Prompt (it's a `.bat` file — Git Bash can run it too,
but double-clicking it in Explorer is simplest). It opens
`http://localhost:<PORT>/` in the browser automatically after a few
seconds.

## 7. Optional: desktop shortcuts

```
scripts/create_shortcuts.bat
```

Adds two Desktop icons: **Noc Dashboard** (starts it) and **Dashboard
Settings** (opens `configurator.py`).

## 8. Configuration

`scripts\configure.bat` opens a settings window (`configurator.py`) to
toggle which dashboard cards are shown and edit sync/alert intervals —
saves back to `.env`.

- **Card visibility** (`FEATURE_*` flags) applies live, on the next page
  load — no restart needed.
- **Sync intervals and alert settings** need the dashboard restarted
  (close the window, run `scripts\start_dashboard.bat` again) to take
  effect, since those control background threads that only read `.env`
  once at startup.

`.env` already has this deployment's real database credentials — no
changes needed unless this VM should point at different databases.

## 9. Optional: auto-start on VM boot/reboot

By default the dashboard only starts when someone double-clicks the
**Noc Dashboard** shortcut. If the VM reboots (Windows update, host
restart, power loss) and nobody logs in and starts it manually, the
dashboard — and all its background sync jobs — stay down until someone
does. Pick one of the two options below to fix that.

### Option A — Task Scheduler (needs admin rights, recommended)

Starts the dashboard automatically at boot, even if nobody logs in.

1. Open **Task Scheduler** (`taskschd.msc`)
2. **Create Task** (not "Create Basic Task")
3. **General** tab:
   - Name: `Noc Dashboard`
   - Check **"Run whether user is logged on or not"**
   - Check **"Run with highest privileges"**
4. **Triggers** tab → **New** → Begin the task: **"At startup"**
5. **Actions** tab → **New** → Start a program:
   - Program/script: full path to `scripts\start_dashboard.bat`
     (e.g. `E:\Noc-Dashboard\scripts\start_dashboard.bat`)
   - Start in: the project root folder (e.g. `E:\Noc-Dashboard`) —
     required, otherwise the `.bat` can't find the venv/app
6. Save — enter the VM account's password when prompted
7. Test: right-click the task → **Run**, confirm the dashboard starts

Equivalent one-line version (run from an elevated Command Prompt):
```
schtasks /create /tn "Noc Dashboard" /tr "E:\Noc-Dashboard\scripts\start_dashboard.bat" /sc onstart /ru SYSTEM
```
(adjust the path to wherever this VM's copy actually lives)

### Option B — Startup folder shortcut (no admin needed)

Simpler, but only starts the dashboard when that specific Windows
account logs in — not on an unattended reboot.

1. Press `Win + R`, type `shell:startup`, press Enter — this opens the
   Startup folder for the current user
2. Copy the **Noc Dashboard** desktop shortcut (created by
   `scripts/create_shortcuts.bat` in step 7) into that folder
3. Done — it now starts automatically the next time this account logs in
