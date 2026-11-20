# NOC Dashboard

Current release: **v19.3.11** (16 November 2026). Project metadata uses `19.3.11`; release labels use `v19.3.11`.

A Flask NOC monitoring dashboard. Almost every card is live, backed by two
real upstream databases synced into a local SQLite cache
(`instance/localstorage.db`) on background schedules — pages never query
MSSQL/PostgreSQL directly, only the local cache.

- **ISP POP / EZE / TCT / IT NODE** — from MSSQL (`noc.TBL_PPD`).
- **VVIP Site, Mentor Site, RAN Status (Main AC/Site Down/Tech Down), Alarm
  Site Down / Completely Site Down / Main Failure / DG On, Incident /
  INC-WO by status, Incident Site Down, INC-WO Site Down / Resolved** — all
  from PostgreSQL (`object_138` the alarm feed, `object_322` Incident,
  site/incident/inc_wo tables), each with its own sync scheduler.

Reports/Custom Dashboard pages read the same live services as the main
dashboard. Toggle any card off without touching code via the `FEATURE_*`
flags in `.env` (re-read on every request, no restart needed).

`/incident-report` is a fillable, exportable incident report document
(PDF/DOCX) matching the standard Wholesale Products & Service Delivery
template — editable fields laid directly on the page, a date-grouped
Chronology of Events, and phone-photo (including HEIC) Picture Reference
uploads. See `app/services/incident_report/` and the in-app Help page's own
"Incident Report" section for the full behavior.

`/congestion` is a standalone, bookmarkable page showing just the Top
Congestion Devices card (e.g. for a dedicated wallboard) — the card itself
isn't shown on the main dashboard at all.

## Architecture

Routes (blueprints) call services (business logic, no SQL), which call
repositories (data access, one method per query), which either run a named
`.sql` query or read the local cache.

```
Noc-Dashboard/
├── app/
│   ├── routes/         # Blueprints: dashboard, reports, mentor
│   ├── services/       # Business logic — never imports flask or touches SQL directly
│   ├── repositories/   # Data access, one per domain
│   ├── database/       # connection.py (Postgres), mssql.py (MSSQL),
│   │                   #   cache.py (SQLite alarm cache), queries/*.sql
│   ├── templates/       # Jinja2 templates (layouts, per-blueprint views, partials)
│   ├── static/          # CSS/JS/images
│   └── utils/           # Logging, formatting, date, validation helpers
├── webhook/             # Microsoft Teams alert cards, one file per alarm type
│                        #   (python -m webhook — see webhook/README.md)
├── scripts/             # start_dashboard.bat, configure.bat, create_shortcuts.bat
├── instance/            # localstorage.db — the local alarm cache (gitignored)
└── tests/
```

Two databases in play, neither queried directly by a page — everything
reads the local SQLite cache, kept fresh by background schedulers started
once in `create_app()`:

- **MSSQL** — the ISP POP / EZE / TCT / IT NODE alarm source
  (`app/services/alarm/alarm_scheduler.py`, every `MSSQL_SYNC_INTERVAL_SECONDS`).
- **PostgreSQL** — every other card's source: the broader alarm feed
  (`object_138`, a 10M-row unindexed table on a hot-standby replica — see
  `app/database/queries/ape_alarm.sql`'s own header for the "conflict with
  recovery" replica-timing risk that comes with querying it), plus
  Incident/INC-WO/Site tables. Each has its own sync scheduler
  (`app/services/*/`), all wired in `app/__init__.py`'s `_BACKGROUND_JOBS`.

## Alerts

Two independent outbound alert channels, both reading the same local caches
(no extra Postgres/MSSQL load):

- **Telegram** — three independent alerts, each its own bot/chat/schedule,
  none starts unless its own credentials are set in `.env`:
  - `app/services/telegram/telegram_alert.py` — Incident Site Down over a
    configurable outage threshold (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_IDS`,
    `ALERT_THRESHOLD_MIN`/`ALERT_INTERVAL_SECONDS`, default 4h).
  - `app/services/telegram/telegram_inc_wo_alert.py` — the current INC-WO
    Site Down list, refreshed on its own interval rather than threshold-gated
    (`TELEGRAM_BOT_INC_WO_TOKEN`/`TELEGRAM_CHAT_IDS_INC_WO`,
    `INC_WO_ALERT_THRESHOLD_MIN`/`INC_WO_ALERT_INTERVAL_SECONDS`, default
    0min/15min — 0 threshold means every open row, not just ones over a
    threshold).
  - `app/services/telegram/telegram_inc_wo_power_alert.py` — same shape as
    the INC-WO Site Down alert, but for category='power' work orders
    instead of 'site_down' (`TELEGRAM_BOT_INC_WO_POWER_TOKEN`/
    `TELEGRAM_CHAT_IDS_INC_WO_POWER`,
    `INC_WO_POWER_ALERT_THRESHOLD_MIN`/`INC_WO_POWER_ALERT_INTERVAL_SECONDS`,
    same 0min/15min default). Telegram-only — no dashboard card behind it.
  - All three send as a table image (Pillow) with a plain-text fallback, and
    all three can be configured from `configurator.py`'s General tab
    instead of hand-editing `.env`.
- **Microsoft Teams** (`webhook/` — see `webhook/README.md`) — one card per
  alarm type (EZE, TCT, POP Down/Power, Main Failure, DG On, Site Down,
  INC-WO Site Down, ...), sent every `TEAMS_ALERT_INTERVAL_SECONDS`
  (default 15 min), clock-aligned. Each
  card's Teams webhook URL lives in `.env`; an unset URL just skips that
  one card. `python -m webhook list/preview/send/send-all` for manual
  testing — never sends on its own.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
pip install -r requirements.txt
copy .env.example .env           # then fill in real values — see below
python run.py
```

The app runs at `http://localhost:<PORT>`, where `PORT` comes from `.env`
(code default is 8000 if unset — but set it explicitly per machine, since
`.env` is gitignored and never shared between environments; e.g. this
project's own VM runs on 5000 while local dev runs on 8000). The local
alarm cache (`instance/localstorage.db`) is created automatically on first
run — no manual seed step needed.

### Required `.env` values

- `SECRET_KEY` — a real random value, not the placeholder. Generate one with:
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- `MSSQL_HOST`, `MSSQL_DATABASE`, `MSSQL_USER`, `MSSQL_PASSWORD` — needed for
  the ISP POP / EZE / TCT / IT NODE cards to show live data. Without these,
  the cards just show 0/green (MSSQL sync fails silently and logs the
  error — the dashboard itself doesn't crash).
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` — the PostgreSQL
  connection every other live card (Incident, INC-WO, RAN, Alarm Site
  Down/Main Failure/DG On, VVIP, Mentor) reads through its own sync
  scheduler. Same silent-fail-and-log behavior as MSSQL if unset.
- `APP_ENV` — `development` (debug on) or `production` (debug off). Turn
  debug off before this runs anywhere besides your own machine — debug mode
  exposes an interactive Python console in the browser on any unhandled
  error.
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_IDS` and `TEAMS_WEBHOOK_*` (one per
  channel, see `webhook/README.md`) — optional. Neither alert channel starts
  without its own credentials set.
- `DASHBOARD_URL` — this machine's own reachable address (e.g.
  `http://<this-host>:5000`). Fills in the "View Dashboard" / "View Report"
  links on Teams cards; blank just omits them. Since `.env` is gitignored,
  set this to each machine's own address — never copy one host's value to
  another's `.env`.

## Tests

```bash
pytest
```

## Logs

Every request/background-thread log line goes to stdout and to
`logs/app.log`. A few narrower files pull out just one thing so it's
readable without grepping the full log (see `app/utils/logger.py`):

| File | What it holds |
|---|---|
| `logs/error.log` | ERROR/CRITICAL only, from any source |
| `logs/attempts.log` | Postgres retry attempts (e.g. "conflict with recovery" storms) |
| `logs/dashboard.log` | Data freshness — one line per page view, plus a clock-aligned heartbeat every `DASHBOARD_LOG_INTERVAL_SECONDS` even with no visits |
| `logs/telegram.log` | The Telegram alert's own send/skip/fail history |
| `logs/webhook.log` | The Teams webhook alerts' own send/skip/fail history |
| `logs/requests.log` | One line per HTTP request (method, path, status, duration, remote address) — use this to correlate a slow/reported page load with a specific endpoint or a burst of concurrent requests |

Each file rotates at `LOG_MAX_BYTES` (default 10MB), keeping
`LOG_BACKUP_COUNT` (default 5) old copies.

## Running it

`scripts/start_dashboard.bat` starts the app via the project's venv and
opens the browser once it's up. `scripts/create_shortcuts.bat` adds Desktop
shortcuts for that and for `scripts/configure.bat`, which opens a small
PySide6 window (`configurator.py`) to toggle dashboard cards on/off and
edit sync/alert intervals without hand-editing `.env`.

## JSON API

The JSON API is listed at `/api/v1/`. Map data is available at `/api/v1/map/sites`. Existing JSON URLs remain compatible. See [API usage](docs/api.md) for supported requests and CSRF requirements.

## Dedicated sync worker

The web server serves HTTP only; `python run.py` ensures its separate worker is started first. Use `python run.py --web-only` when a separate service manages the worker. `worker.py` owns all scheduled sync and Teams/Telegram loops. Run both from the same project folder and preserve `.env` and `instance/`. The normal `scripts/start_dashboard.bat` launcher ensures an independent hidden worker is running before starting the website. The normal dashboard launcher and direct python run.py request graceful worker shutdown on Ctrl+C; explicit --web-only mode leaves worker lifecycle to its supervisor.

Check status at `/api/v1/system/sync` or run `.venv\Scripts\python.exe worker.py --status`. Validate schedules without syncing or sending with `.venv\Scripts\python.exe worker.py --check`. See [worker operations](docs/sync-worker.md) before migration.

Historical performance charts now load as their section approaches the viewport, so initial dashboard rendering prioritizes live cards. Filters and existing chart endpoints remain unchanged. The loader offers Retry on failure; `/?load_performance=1` provides a full-page fallback. Set `DASHBOARD_LAZY_PERFORMANCE=false` and restart the web process to disable deferred loading.

Historical SLA and response/resolution drilldowns show all matching rows in one table, without pagination. Exports retain the complete result for the selected view filters.

HTTP error pages share a consistent layout for all application HTTP exceptions. API errors remain JSON; status codes and protocol headers are preserved. Mentor upload/session errors provide readable recovery guidance.


## v19.3.9 update

Site Down by Age worklog popups now list every incident in the selected group, including incidents without worklogs. Expand a row to see its entries or the explicit empty-worklog message. Multi-site incidents appear once. Worklog contents remain lazy-loaded.

Smart Report credit tables use the reference two-row header and a full-width merged orange footer. The credit table is inline to prevent Word from shifting the orange shading away from its border. Existing monthly USD amounts remain stored and are exported as month-labelled text in the merged footer.

For VM export validation, double-click scripts/test_pdf_export.bat. It tests five sample reports in both hidden and visible Word without changing settings or saved reports. Word may appear during the visible comparison. Each export has a 45-second timeout. PDF exports now run Word in hidden mode, verified with incident reports, fault images, and Smart Network sample reports. Restart the dashboard after updating the converter. Microsoft Word remains required on the server.


## Dashboard and worker shortcuts

Run scripts/create_shortcuts.bat from each new installation to refresh the desktop targets. Noc Dashboard starts or reuses the worker before opening the website. NOC_Worker starts or shows the worker without opening the website. Its console is a status snapshot; closing it leaves the background worker running.

The dashboard launcher automatically requests a graceful handoff from a verified dedicated worker in an older project folder. It waits for in-progress jobs before starting the new worker. A healthy current worker is reused. Unrecognized processes and legacy embedded schedulers require manual attention; they are never force-stopped. Early worker tracebacks are retained in logs/worker-startup.log.

For an update: press Ctrl+C in the old dashboard console and wait for the worker-stopped message. Back up .env and the complete instance folder before deleting any old installation. Extract the new version, restore .env and instance, prepare its .venv and requirements, and rerun scripts/create_shortcuts.bat. Double-click Noc Dashboard to start both services. Normal sync schedules and saved notification history are preserved.

For the first upgrade from a launcher older than v19.3.10, stop its worker from the old folder and confirm stopped status before copying instance data. Automatic process handoff does not migrate files between folders.


## v19.3.11 restoration update

Restoration replies wait for both Actual Root Cause and Resolution, and never use suspected
cause or comments as replacements. Alarms use Issue Occurred At to Cleared Alarm Received At;
NOC/manual incidents use Created At to Closed At. Missing, invalid, or future restoration
timestamps defer sending. Incomplete replies remain pending for the next five-minute check.
The message shows the actual restoration time, even when the details are completed later.
Existing replies recorded as sent are not automatically resent.

Set NOTIFICATIONS_ENABLED=false on local development machines and true on the one sending VM.
Restart workers after changing this setting. Source-data sync continues in local sync-only mode.
The setting defaults to true for existing installations; the ZIP contains no real .env or instance data.
Preserve your VM .env and entire instance folder during upgrades. Power Automate must retain
its RestoreSent tracking, use trigger concurrency 1, and review duplicate mappings. A webhook
acceptance does not guarantee that a later Teams action succeeded; reconcile failed flow runs
before retrying. This package does not change the live Power Automate flow.


## Incident Report reference update

New Incident Reports use the supplied October Items / Description / Remark reference, with
separate customer-report, Telcotech-response, occurrence, and resolution times. Interruption
is calculated from occurrence to resolution. Dated activities, first/second faults, per-item
remarks and optional photos are supported. DOCX and Word-rendered PDF
share the same packaged reference. Saved legacy reports keep their original layout; use
Use updated template to preview the new layout and save only when ready. Existing data is
not rewritten by viewing or exporting. New report fields are added to local storage without
removing existing columns. Smart Network monthly reports keep their own template.


First- and second-fault picture uploads are separate on the October Incident Report form.
Each saved photo keeps its fault label; older unlabelled images remain general Picture References.
Legacy additional-detail values remain saved but are hidden from the new editor and exports.
Saved improvement plans are preserved but hidden from incident report editors and exports. PDF/DOCX attachments are
labelled by fault and sized to fit the page without distortion. Removing the second fault section
does not silently delete its saved photos; re-add the section to view/edit them, or explicitly
remove individual images before saving. Existing reports and images are never bulk-reassigned.


Report saves refresh their form token before native submission, keeping the clicked Draft/Final
intent and file uploads. If token refresh fails, the editor stays open with the unsaved inputs.
CSRF protection remains enabled and rejection reasons are logged without token or form contents.
The updated Incident Report hides both Additional incident details and Improvement and Preventive
Plan in its editor and exports, while retaining previously saved values for compatibility.


Congestion history caches every matching TCT bandwidth/congestion source alarm within
CONGESTION_HISTORY_WEEKS, including restored alarms; the Top 20 chart is a display limit only.
Weekly drilldown links open All alarm events, with a separate row for each occurrence and its
restoration time. Interface summary remains available. CSV exports follow the selected view
and date range without a Top 20 limit. Existing blacklist rules hide interfaces from views;
they do not remove the underlying cached records. History is bounded by the configured weeks,
not an indefinite archive. Source records removed upstream cannot be guaranteed by a refill cache.

The history source query removes identical rows introduced by duplicate ISP/POP mappings;
each distinct alarm remains available, including unmapped devices. This can reduce inflated
historical chart counts after the next worker sync without losing underlying alarm events.
