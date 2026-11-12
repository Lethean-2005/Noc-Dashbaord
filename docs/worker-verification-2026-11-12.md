# Dedicated worker verification - 12 November 2026

Implemented a web-only application role and a dedicated worker role. The existing job registry and offset validator moved into app/background.py. All base jobs, configured Telegram channels and Teams gates retain the existing intervals and scheduler implementations. The worker uses the existing machine-wide exclusive lock, also detecting older embedded-scheduler versions.

Web processes do not start background loops or leadership takeover watchers. Worker shutdown interrupts waiting loops and keeps ownership while in-flight jobs finish. A session-targeted stop command permits hidden-worker shutdown without stopping the web server. Optional Windows Task Scheduler installation provides logon startup and failure recovery; it has not been installed automatically. Default worker rotating logs are separated from web logs to avoid cross-process Windows file-handle conflicts.

Verification completed:

- Full Python suite: 725 passed.
- JavaScript regression suite: 14 passed.
- Syntax parsing: 192 Python files, 20 application JavaScript files, 82 Jinja templates.
- Pyflakes: app, scripts, worker.py and run.py passed.
- PowerShell task-installer syntax passed.
- Real isolated worker process updated a temporary shared cache, remained active through two web-app restarts, rejected a duplicate worker, stopped through the CLI request, and restarted successfully.
- Cross-process exclusive lock rejection and release were verified using an isolated port.
- Saved Mentor sites, exclusions/remarks, reports, sync metadata and Site Down alert ledger survived application restart unchanged.
- WAL concurrency check confirmed a cache reader could read committed data while another connection held a write transaction, then see the new committed result.
- Registry checks verified all base jobs and configured notification jobs received their original configured intervals. Existing restore-timestamp, Teams timezone, Telegram and Site Down notification regressions passed.

No changes were made to source SQL, local cache schema, notification payload builders or blacklist matching logic. No files under scripts were deleted. Existing API work was preserved, with the additional read-only worker health route at /api/v1/system/sync.

Limits: automated verification used isolated data and fake sender/source boundaries. It did not send live Teams/Telegram messages, install scheduled tasks, start production sync jobs, or establish VM load capacity. A healthy heartbeat is not a guarantee that source systems or downstream Power Automate delivery succeeded. The existing HTTP-acceptance limitation remains. Network failures and long-running jobs can still delay updates; five-minute intervals are scheduled targets rather than a latency guarantee.

Activation: stop older embedded-scheduler builds, preserve .env and instance, validate with worker.py --check, and use scripts/start_dashboard.bat. Direct run.py is web-only. Follow docs/sync-worker.md before updating or moving the worker. Worker code/config updates require worker restart as well as any web restart. No commit, push, ZIP build or live deployment was performed by this verification.


## Startup and week-window follow-up

Normal `python run.py` now ensures the independent worker before serving HTTP, closing the direct-start path that could leave a web-only process showing stale data. The batch launcher ensures the worker once and uses `run.py --web-only`. Flask/WSGI imports and explicit web-only mode remain appropriate for separately supervised services.

All 19 configured job groups passed configuration validation; Site Down uses two loops, giving 20 observed scheduler loops. Incident sync and Site Down checks remain 300 seconds; regular Teams checks remain 900 seconds. Other configured schedules remain unchanged.

The source columns are UTC timestamp-without-time-zone fields. Five oldest-week query cutoffs now convert Cambodia midnight to its UTC equivalent before comparison. For the inspected oldest week (19 October 2026), this changes the boundary from 07:00 local to 00:00 local. Read-only source verification found 117 valid closed Site Down incidents in that seven-hour range, represented by 165 cached incident/site rows after normal synchronization. None belong to site 1902. This correction is separate from the three newer incidents explaining the earlier 309-versus-312 mismatch.

The ranking memo now retains its input list and compares identity directly, avoiding recycled Python object-ID hits when changing week selections. It does not alter how site counts are calculated.

Follow-up local readback: worker state running and healthy, 20 loops, no reported callback errors. Top 10 cache last-synced 12-Nov-2026 15:05:50 +07:00; site 1902 count 312, matching the earlier production export. The Site Down Telegram loop had not reached its first configured send time. These observations are not a claim of downstream Teams/Telegram delivery confirmation.

Validation: 744 Python tests and 16 JavaScript tests passed, along with static checks. No manual test notification was sent. Source verification used read-only transactions; normal worker cache updates remain responsible for refreshes.

The cache holds individual records for the current ISO week plus three preceding ISO weeks, with week selection applied on read. Five-minute synchronization is not five-minute retention and is not a requirement to wait 24 hours before updating. A complete calendar-day report uses Cambodia 00:00 up to the next 00:00; today is partial until midnight. Date-range filters use complete Cambodia calendar days; no separate daily selector has been added. Misleading user-facing last-30-days wording was replaced with available weeks.


### Full calendar-day filtering

Date selections use Cambodia calendar days: include 00:00 on the start date and exclude 00:00 after the end date. This includes 23:59:59 and fractional seconds. Incident, INC-WO and live-alarm date filters share this rule for table and CSV routes. Missing dates are excluded when a date filter is selected. No date selection leaves active alarms and historical records unchanged. Weekly windows remain Monday through Sunday; current days and weeks contain data received so far. Sync intervals and notification thresholds remain unchanged.
