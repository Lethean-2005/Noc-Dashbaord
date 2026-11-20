# Dedicated sync worker

## Runtime structure

The web process (`run.py`, Flask CLI or WSGI app factory) serves requests and does not start scheduled work or leader-lock takeover threads. The dedicated worker (`worker.py`) registers the existing sync and alert schedulers against the same configuration and local `instance/localstorage.db`.

This change does not modify source SQL, cache table definitions, incident/badge logic, blacklist keys, saved reports, or restoration message fields. Normal user actions may still write data or trigger their existing targeted refresh. There is no second database or copy of saved exclusions.

The worker retains all configured intervals, original per-job offsets and Cambodia clock alignment. Telegram channels, regular Teams webhooks and Site Down/down-restoration checks keep their configuration gates and initial delayed send behavior. Starting or restarting the worker does not force an immediate send or reset the persistent Site Down alert ledger. A slow query can delay a job beyond its interval; separate processes do not eliminate network or database delays.

## One-time migration

1. Stop all older dashboard processes that still contain embedded schedulers. Do not leave an old version running alongside this one.
2. Update code in the same project folder. Preserve `.env`, `instance/`, and the virtual environment. If using a new folder, preserve the same complete data directory and configuration before starting it.
3. Run `.venv\Scripts\python.exe worker.py --check`. It validates configuration and offsets without creating the app, syncing data or sending alerts.
4. Start using `scripts/start_dashboard.bat`. It ensures a hidden independent worker is ready, then runs the web server. Alternatively, start `scripts/start_sync_worker.bat` and the web command in separate processes.
5. Check `/api/v1/system/sync`, the normal cache freshness display/logs and the next scheduled cycles. Initially jobs report waiting until their existing next clock boundary. Fresh heartbeat alone does not prove every source query succeeded.

Running `python run.py` now ensures the independent worker is ready before starting HTTP. `python run.py --web-only`, Flask CLI and WSGI imports intentionally serve HTTP only; use them when a separate task/service manages the worker. The batch launcher ensures the worker once and then invokes the web-only mode. No schedulers run inside web threads.

## Windows automatic recovery

An optional installer is provided at `scripts/install_sync_worker_task.ps1`. Run it explicitly in PowerShell for the current Windows user. It registers `NocDashboardSyncWorker` in Task Scheduler, starts it at that user's logon, prevents overlapping task instances and restarts failed executions after one minute (up to 999 retries). It does not require storing a password. Start it initially with `Start-ScheduledTask -TaskName NocDashboardSyncWorker`.

This task is not a Windows service and does not promise unattended execution before user logon. For an always-on VM without an interactive session, operations should configure an approved service/task account and boot-time service management. The provided task has not been installed automatically. Avoid a second independent supervisor; the machine-wide lock also blocks accidental duplicates.

The logon task uses an absolute project path. If a new release is installed in a different folder, stop the old worker/task and re-register the task from the new folder. Keeping a stable installation folder avoids this path change.

## Health and troubleshooting

`worker.py --status` and `GET /api/v1/system/sync` read the heartbeat without fetching source data. Status includes PID, start time, timezone and per-job interval, last attempt, completed-without-exception time, duration, thread state and error class. `healthy` requires a running state, live reported threads and a heartbeat no older than 60 seconds. It is an operational heartbeat rather than a guarantee of source freshness or downstream Teams delivery. Detailed source-query failures remain in existing job/retry logs. `last_success_at` means the scheduler callback returned without raising; callbacks that internally log a partial failure can still return.

Heartbeat writes occur every 15 seconds to a small atomically replaced JSON file in `instance/`; they do not add repeated SQLite writes. SQLite WAL mode and the existing busy timeout continue to support readers while the worker updates caches. Existing short read caches can add their normal refresh delay to newly committed data.

Worker file names use a `worker-` prefix in the configured log directory (for example `logs/worker-app.log`, `logs/worker-error.log`, and `logs/worker-telegram.log`). This prevents web and worker processes holding the same rotating log files open on Windows. Optional `WORKER_LOG_PATH`, `WORKER_LOG_ERROR_PATH`, and corresponding `WORKER_`-prefixed log settings override worker destinations without changing web settings. Existing Telegram, webhook and retry log categories remain available. No token, webhook URL or raw exception message is included in the public status file.

If another worker or an older embedded scheduler owns the existing machine-wide lock, a second worker exits with code 2. It does not overwrite the first worker's heartbeat or start schedulers. The standard dashboard launcher identifies a dedicated worker in an older folder and requests its graceful stop before starting this project. Direct worker.py execution still reports a conflict. Unrecognized processes and legacy embedded schedulers require manual stopping; no force-kill is used. Saved databases and sending ledgers are preserved.

## Stopping and updating

Run `.venv\Scripts\python.exe worker.py --stop` for a hidden worker, or use Ctrl+C in a foreground worker. A stop request targets the current PID and startup session, so an old request does not stop a restarted worker. Graceful shutdown: waiting loops wake immediately, in-flight work is allowed to finish, and the worker retains its lock until all threads stop. A stopped worker leaves saved data intact. An explicit --web-only restart does not stop the worker. The normal dashboard launcher passes --stop-worker-on-exit and requests graceful shutdown on Ctrl+C. To change worker code, configuration or source credentials, restart the worker as well; replacing files under a running worker is not a safe worker-code deployment strategy.

Windows task termination or a VM shutdown may forcibly stop the process. SQLite transactions retain their normal atomicity, but an external webhook accepted just before a forced stop can still create an uncertain delivery outcome. The worker does not introduce exactly-once delivery guarantees. Power Automate HTTP acceptance still does not independently confirm downstream completion.

No live alerts or production source writes should be used during automated verification. Use temporary instance directories and mocked source/sender calls.


## Updating with desktop shortcuts

The normal dashboard launcher starts the worker first and closes it gracefully after Ctrl+C stops the web server. Wait for the stopped message. If in-flight jobs exceed the shutdown wait, the console explicitly says the worker is still finishing and the old folder must be retained. Debug-reloader exits and HTTP bind failures do not stop an existing shared worker. Closing an old web console cannot stop a worker already handed off to a different project folder.

Before removing an old installation, preserve .env and the complete instance directory. Restore them into the extracted update and install requirements in that folder's virtual environment. Run scripts/create_shortcuts.bat to refresh Noc Dashboard, Dashboard Settings and NOC_Worker links. NOC_Worker targets scripts/open_worker.bat and shows a status snapshot without starting HTTP. It does not require a second worker installation.

Automatic cross-folder handoff uses the existing loopback lock to identify a Windows process, verifies the dashboard script path and matching heartbeat PID, and writes a session-specific stop request to the owning instance directory. It waits for the old lock to be released. Windows venv redirector children are recognized when validating a newly spawned worker. A named mutex serializes competing launchers. Missing or stale identities block automatic handoff rather than stopping an unrelated process. The existing job intervals, source queries and notification rules are unchanged.

If the optional Windows logon task was installed, explicitly rerun scripts/install_sync_worker_task.ps1 from the new installation to update its target. Startup does not silently change scheduled tasks.


## Local sync without notifications

Set `NOTIFICATIONS_ENABLED=false` in the local `.env` and restart the local worker.
Data sync and dashboard refreshes continue; scheduled and manual Teams/Telegram delivery is blocked,
including Site Down restoration replies. Disabled delivery does not update notification sent records.
Set `NOTIFICATIONS_ENABLED=true` on the VM responsible for sending notifications, then restart its worker.
Existing installations default to true. Keep only one machine enabled; this switch does not provide
cross-machine deduplication if two machines are both enabled. Existing duplicates are not removed.


## Restoration readiness

A restoration reply waits for the source-specific timestamp (Alarm: Cleared Alarm Received At;
NOC/manual: Closed At), a valid start-to-restoration order, and a restoration time no later than now.
Both Actual Root Cause and Resolution must contain non-whitespace text. Missing details leave the
notification pending for the next scheduled check; suspected cause and comments are not substitutes.
The message keeps the actual restoration time even when it is sent later after details are completed.
Already recorded replies are not resent or amended automatically. A webhook acceptance still does
not prove that all Power Automate actions completed; review failed flow runs before retrying.
