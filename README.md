# NOC Dashboard

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

- **Telegram** (`app/services/telegram/telegram_alert.py`) — one alert,
  Incident Site Down over a configurable outage threshold, sent as a table
  image every `ALERT_INTERVAL_SECONDS` (default 4h), clock-aligned.
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

The app runs at `http://localhost:5000` (or whatever `PORT` is set to in
`.env`). The local alarm cache (`instance/localstorage.db`) is created
automatically on first run — no manual seed step needed.

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

Each file rotates at `LOG_MAX_BYTES` (default 10MB), keeping
`LOG_BACKUP_COUNT` (default 5) old copies.

## Running it

`scripts/start_dashboard.bat` starts the app via the project's venv and
opens the browser once it's up. `scripts/create_shortcuts.bat` adds Desktop
shortcuts for that and for `scripts/configure.bat`, which opens a small
PySide6 window (`configurator.py`) to toggle dashboard cards on/off and
edit sync/alert intervals without hand-editing `.env`.
