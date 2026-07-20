# NOC Dashboard

A Flask NOC monitoring dashboard. The ISP POP / EZE / TCT alarm cards are
live, backed by a real MSSQL alarm feed synced into a local SQLite cache
every few seconds. Everything else (VVIP, Mentor, RAN, Incident/INC-WO,
Custom Dashboard) is still a static visual placeholder — no query behind it
yet.

## Architecture

Routes (blueprints) call services (business logic, no SQL), which call
repositories (data access, one method per query), which either run a named
`.sql` query or read the local cache.

```
Noc-Dashboard/
├── app/
│   ├── routes/         # Blueprints: dashboard, reports, mentor, api
│   ├── services/       # Business logic — never imports flask or touches SQL directly
│   ├── repositories/   # Data access, one per domain
│   ├── database/       # connection.py (Postgres), mssql.py (MSSQL),
│   │                   #   cache.py (SQLite alarm cache), queries/*.sql
│   ├── templates/       # Jinja2 templates (layouts, per-blueprint views, partials)
│   ├── static/          # CSS/JS/images
│   └── utils/           # Logging, formatting, date, validation helpers
├── scripts/             # scheduler.py (report jobs), seed.py (Postgres models — currently unused)
├── instance/            # localstorage.db — the local alarm cache (gitignored)
└── tests/
```

Two databases in play:

- **MSSQL** — the real alarm source (`noc.TBL_PPD`). A background thread
  (`app/services/alarm_scheduler.py`, started once in `create_app()`) pulls
  active alarms every `MSSQL_SYNC_INTERVAL_SECONDS` and writes them into the
  local SQLite cache. Pages never query MSSQL directly.
- **PostgreSQL** — configured in `app/config.py` but not yet wired to any
  real table; the incidents/reports/mentor pages are still static.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
pip install -r requirements.txt
copy .env.example .env           # then fill in real values — see below
python run.py
```

The app runs at `http://localhost:8000` (or whatever `PORT` is set to in
`.env`). The local alarm cache (`instance/localstorage.db`) is created
automatically on first run — no manual seed step needed.

### Required `.env` values

- `SECRET_KEY` — a real random value, not the placeholder. Generate one with:
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- `MSSQL_HOST`, `MSSQL_DATABASE`, `MSSQL_USER`, `MSSQL_PASSWORD` — needed for
  the ISP POP / EZE / TCT cards to show live data. Without these, the cards
  just show 0/green (MSSQL sync fails silently and logs the error — the
  dashboard itself doesn't crash).
- `APP_ENV` — `development` (debug on) or `production` (debug off). Turn
  debug off before this runs anywhere besides your own machine — debug mode
  exposes an interactive Python console in the browser on any unhandled
  error.

## Tests

```bash
pytest
```

## Logs

Every request/background-thread log line goes to stdout and to
`logs/app.log`; anything at ERROR level or above is mirrored to
`logs/error.log` as well, so failures (e.g. a failed MSSQL sync) are easy to
find without grepping the full log.

## Scheduled report jobs

`scripts/scheduler.py` is a separate, standalone entry point for
Postgres-backed report jobs (wire it up to cron / Windows Task Scheduler /
a job runner) — unrelated to the MSSQL alarm sync above, which runs
automatically inside the app itself and needs no external scheduler.
