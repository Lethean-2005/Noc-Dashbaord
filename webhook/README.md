# webhook/ — Microsoft Teams alert senders (one per alarm type)

Each alarm type has its own small file that pulls rows from the already-
synced local SQLite cache (same cache the dashboard cards read — no extra
Postgres/MSSQL load), builds a scrolling Teams **connector card** (light
header, black/bold text, ~5 rows then vertical scroll, horizontal column
scroll), and POSTs it to **its own** webhook URL from `.env`.

All shared logic — the table, the card, the send, the CLI — lives in
**`common.py`**. Each per-alarm file is just an `AlertSpec` (title, env var,
data source, columns, report link). Change `common.py` once and every card
updates.

## Webhooks & their `.env` variables

| File | Alert (key) | `.env` variable | Data source |
|------|-------------|-----------------|--------------|
| `eze_alarm.py`           | EZE Active Alarms (`eze`)             | `TEAMS_WEBHOOK_EZE_ALERTS` (falls back to `TEAMS_WEBHOOK_URL`) | `AlarmService.get_eze_details()` |
| `tct_alarm.py`           | TCT Active Alarms (`tct`)             | `TEAMS_WEBHOOK_TCT_DOWN` | `AlarmService.get_tct_details()` |
| `pop_down.py`            | POP/PON Down (`pop_down`)             | `TEAMS_WEBHOOK_POP_DOWN` | `AlarmService.get_isp_pop_details()` filtered to `alarm == 'POP/PON DOWN'` |
| `pop_main_failure.py`    | POP/PON Power Failure (`pop_main_failure`) | `TEAMS_WEBHOOK_POP_MAIN_FAILURE` | same cache, filtered to `alarm == 'POP/PON POWER'` |
| `main_failure.py`        | Alarm Main Failure (`main_failure`)   | `TEAMS_WEBHOOK_MAIN_FAILURE` | `AlarmMainFailureService.get_details()` |
| `current_site_down.py`   | Current Site Down Alarms (`current_site_down`) | `TEAMS_WEBHOOK_CURRENT_SITES_DOWN_ALARMS` | `AlarmSiteDownService.get_details()` |
| `cso_sub_con.py`         | CSO Sub-Con (`cso_sub_con`)           | `TEAMS_WEBHOOK_CSO_SUB_CON` | same fetch as `current_site_down.py` |
| `current_site_outage.py` | Current Sites Outage (`current_site_outage`) | `TEAMS_WEBHOOK_CURRENT_SITES_OUTAGE` | same fetch as `current_site_down.py` (Alarm Site Down / ape_alarm cache) |
| `dg_on.py`               | Alarm DG On (`dg_on`)                 | `TEAMS_WEBHOOK_DG_ON` | `DgOnAlarmService.get_details()` |
| `inc_wo_site.py`         | INC-WO Site Down (`inc_wo_site`)      | `TEAMS_WEBHOOK_INC_WO_SITE_DOWN` | `IncWoService.get_site_down_details()` |

Not wired: **IT NODE** — no Teams channel/URL exists for it.

Add each URL to `.env` when you receive it, e.g.:

```
TEAMS_WEBHOOK_DG_ON=https://.../triggers/manual/paths/invoke?...
```

A webhook whose URL is **not** set is simply **skipped**, so you can enable
them one at a time as you get each URL. `DASHBOARD_URL` (also in `.env`)
fills the card's "View Report Table / View Dashboard" links — it's blank by
default (links are omitted), and since `.env` is gitignored, set it to each
machine's own reachable address (never copy one host's value to another's
`.env`).

## Command line

```bash
python -m webhook list             # show every alert + whether its URL is set
python -m webhook preview <key>    # build & print one card — NEVER sends
python -m webhook send <key>       # send one alert, e.g. send eze
python -m webhook send-all         # send every configured alert
python -m webhook                  # (no command) = send-all  (backward compatible)
python -m webhook --help           # built-in help
```

Exit codes: `0` success · `1` nothing sent / failed · `2` unknown key.

> Use `list` and `preview` for safe testing — they never post to Teams.

Every command runs inside a real Flask app context (`__main__.py` calls
`create_app()` and pushes it) — each alert's `fetch()` reads the local
cache through this project's Flask-SQLAlchemy repositories, which need
`current_app`.

## Behaviour toggles (`.env`)

| Variable | Default | Effect |
|----------|---------|--------|
| `WEBHOOK_SEND_EMPTY` | `false` | When an alert has **no rows**, the send is **skipped**. Set to `true` to still post a "no active alarms" card. |
| `TEAMS_ALERTS_ENABLED` | `true` | Master on/off for the scheduled Teams sends. |
| `TEAMS_ALERT_INTERVAL_SECONDS` | `900` (15 min) | How often the scheduler sends all alerts. |

## Automatic sending

`app/__init__.py`'s `_init_webhook_alerts()` starts the scheduler once per
process (same leader-lock / debug-reloader-safe pattern as every other
background job in this project — see `_init_telegram_alert()` right above
it), which calls `send_all()` (in `__init__.py`) on a clock-aligned schedule
(e.g. every 900s → 00:00, 00:15, 00:30, 00:45) via
`app/services/scheduler_utils.py`. The command line above is a **separate
manual tool** — it is **not** used by the scheduler, so running it can
never affect the automatic alerts.

## Where the card look is controlled

All in **`common.py`**:

- `build_html_table()` — the table (font size, padding, borders, header colour, scroll height, blue Incident/INC-WO links).
- `build_connector_card()` — the card frame (title, subtitle, footer links, `themeColor` red accent bar).
- Top-of-file constants: `_FONT`, `_TEAMS_CARD_LIMIT`, `_STREAMLINE_HOST`.

Note: a Teams **MessageCard** has a **fixed width** set by Teams — it cannot
be made wider; wide tables scroll horizontally instead. What Teams actually
renders also depends on how the receiving Power Automate flow's "Post card"
action is configured (e.g. whether it reads the raw `triggerBody()` or only
a specific field) — that's outside this codebase.

## Adding a new webhook

Copy any file, change the `_fetch()` data source, the `COLUMNS`, and the
`AlertSpec` (title / env var / report path), then add the module to the
`SPECS` list in `__init__.py`. That's it.
