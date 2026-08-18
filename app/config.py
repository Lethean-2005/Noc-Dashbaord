"""Application configuration.

Config (below) reads every setting from the environment once, at class-
definition time — so app/__init__.py MUST call load_dotenv() before this
module is ever imported, or .env values are silently ignored in favor of
the hardcoded defaults here. That one-time read is fine for things that
only matter at startup (DB host, secret key, ...), but dashboard card
visibility needs to change without restarting the app — see
get_feature_flags() below for that.

DevelopmentConfig / TestingConfig / ProductionConfig only override what
differs from the base Config; config_map picks one by APP_ENV.
"""

import os
from datetime import timedelta
from pathlib import Path


def _bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# ── Feature flags — dashboard card visibility ───────────────────────
# One flag per card on dashboard/index.html and reports/index.html.
# Unlike everything else in Config, these are re-read straight from
# .env on every request (see get_feature_flags() + the `features`
# context processor in app/__init__.py) instead of once at startup —
# so toggling a card on/off, whether by hand or via configurator.py,
# takes effect on the very next page load with no restart needed.
_FEATURE_DEFAULTS = {
    "FEATURE_VVIP_SITE": True,
    "FEATURE_MENTOR_SITE": True,
    "FEATURE_ISP_POP": True,
    "FEATURE_TCT_PORT": True,
    "FEATURE_INCIDENT_INCWO_STATUS": True,
    "FEATURE_RAN_STATUS": True,
    "FEATURE_INCIDENT_SITEDOWN": True,
    "FEATURE_ALARM_SITE_DOWN": True,
    "FEATURE_ALARM_COMPLETELY_SITE_DOWN": True,
    "FEATURE_ALARM_MAIN_FAILURE": True,
    "FEATURE_INCWO_SITE_DOWN": True,
    "FEATURE_ALARM_DG_ON": True,
    "FEATURE_INCWO_RESOLVED": True,
    "FEATURE_IT_NODE": True,
}

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def get_feature_flags():
    """Parse .env fresh (never touching os.environ) and return every
    FEATURE_* flag as {key: bool}, falling back to its default (True)
    if the file is missing or the key isn't set."""
    values = dict(_FEATURE_DEFAULTS)
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key in _FEATURE_DEFAULTS:
                values[key] = _bool(val.strip().strip("\"'"), default=True)
    return values


class Config:
    """Base configuration shared by all environments."""

    # ── Application ──────────────────────────────────────────────
    APP_NAME = os.environ.get("APP_NAME", "Dashboard")
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")

    # ── Server ───────────────────────────────────────────────────
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", 8000))
    # waitress's own default is 4 — too few once several NOC staff have the
    # dashboard open at once: the Overall page alone makes ~10 sequential
    # SQLite cache reads per load, and every open tab full-page-reloads on
    # its own DASHBOARD_LOG_INTERVAL_SECONDS timer (dashboard/index.html),
    # so those reloads land in synchronized bursts across everyone's
    # browsers rather than spread out — a small thread pool means that
    # burst queues up instead of running concurrently. See run.py.
    WAITRESS_THREADS = int(os.environ.get("WAITRESS_THREADS", 8))

    # ── PostgreSQL — Incident/Site/VIP data source ──────────────
    # Read by app/database/connection.py's run_query(). Backs the Incident,
    # INC-WO, Site, and VIP caches synced by app/services/incident/
    # incident_sync_service.py, app/services/site/site_sync_service.py, and
    # app/services/vip/*_sync_service.py.
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_NAME = os.environ.get("DB_NAME", "dashboard_db")
    DB_USER = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.environ.get("DB_POOL_SIZE", 10)),
        "pool_timeout": int(os.environ.get("DB_POOL_TIMEOUT", 30)),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", 20)),
    }

    # ── MSSQL — alarm source for the ISP POP / EZE / TCT cards ──
    # Read by app/database/mssql.py. A background job (app/services/alarm/alarm_scheduler.py)
    # syncs this into the local cache (instance/localstorage.db) every
    # MSSQL_SYNC_INTERVAL_SECONDS — pages read the cache, never MSSQL directly.
    MSSQL_HOST = os.environ.get("MSSQL_HOST", "")
    MSSQL_DATABASE = os.environ.get("MSSQL_DATABASE", "")
    MSSQL_USER = os.environ.get("MSSQL_USER", "")
    MSSQL_PASSWORD = os.environ.get("MSSQL_PASSWORD", "")
    MSSQL_SYNC_INTERVAL_SECONDS = int(os.environ.get("MSSQL_SYNC_INTERVAL_SECONDS", 10))

    # ── Site cache — Site table (object_160) on PostgreSQL ──────
    # Read by app/repositories/site/site_repository.py. A background job
    # (app/services/site/site_scheduler.py) syncs this into the local cache
    # (instance/localstorage.db) every SITE_SYNC_INTERVAL_SECONDS. Site data
    # changes far less often than live alarms, so this defaults to a much
    # longer interval than MSSQL_SYNC_INTERVAL_SECONDS.
    SITE_SYNC_INTERVAL_SECONDS = int(os.environ.get("SITE_SYNC_INTERVAL_SECONDS", 300))

    # ── site_lookup cache — site_lookup_mv on PostgreSQL ─────────
    # Read by app/repositories/site/site_lookup_repository.py. A background
    # job (app/services/site/site_lookup_scheduler.py) syncs this into the
    # local cache every SITE_LOOKUP_SYNC_INTERVAL_SECONDS. This is the
    # lookup table Postgres's own get_processed_site() function used to
    # query per-row inside ape_alarm.sql — see app/utils/get_processed_site.py.
    # Changes about as rarely as Site data, so it shares SITE's interval.
    SITE_LOOKUP_SYNC_INTERVAL_SECONDS = int(
        os.environ.get("SITE_LOOKUP_SYNC_INTERVAL_SECONDS", 300)
    )

    # ── Incident cache — Incident table (object_322) on PostgreSQL ──
    # Read by app/repositories/incident/incident_repository.py. A background job
    # (app/services/incident/incident_scheduler.py) syncs this into the local cache
    # (instance/localstorage.db) every INCIDENT_SYNC_INTERVAL_SECONDS.
    # Same 5-minute default as SITE_SYNC_INTERVAL_SECONDS, so every
    # Postgres-backed sync job puts the same, predictable load on the DB.
    INCIDENT_SYNC_INTERVAL_SECONDS = int(os.environ.get("INCIDENT_SYNC_INTERVAL_SECONDS", 300))

    # ── Dashboard data-freshness heartbeat (logs/dashboard.log) ─────
    # app/routes/dashboard.py's start() logs the same "Dashboard data as
    # of: ..." line the homepage logs per-view, but on its own clock-
    # aligned schedule (00:00, 00:05, 00:10, ... for the 300s default) so
    # dashboard.log has a regular trace even between page views.
    DASHBOARD_LOG_INTERVAL_SECONDS = int(os.environ.get("DASHBOARD_LOG_INTERVAL_SECONDS", 300))

    # ── ape_alarm cache — broader NE/connectivity alarms on object_138 ──
    # Read by app/repositories/ape_alarm/ape_alarm_repository.py. A background job
    # (app/services/ape_alarm/ape_alarm_scheduler.py) syncs this into the local cache
    # (instance/localstorage.db) every APE_ALARM_SYNC_INTERVAL_SECONDS.
    # object_138 is a 10M-row foreign table with no supporting index, so
    # every sync here is a genuinely heavy scan — matches
    # SITE/INCIDENT_SYNC_INTERVAL_SECONDS's 300s (5 min) rather than a
    # longer interval, at the cost of hitting that scan 3x more often.
    APE_ALARM_SYNC_INTERVAL_SECONDS = int(os.environ.get("APE_ALARM_SYNC_INTERVAL_SECONDS", 300))

    # ── vip_alarm cache — every alarm type at VIP/VVIP sites, derived
    # locally from the already-synced ape_alarm cache (no Postgres call of
    # its own) ──
    # A background job (app/services/vip/vip_alarm_scheduler.py) rebuilds
    # this from ape_alarm + site_cache (both already-synced local tables)
    # every VIP_ALARM_SYNC_INTERVAL_SECONDS — see
    # app/services/vip/vip_alarm_sync_service.py.
    VIP_ALARM_SYNC_INTERVAL_SECONDS = int(os.environ.get("VIP_ALARM_SYNC_INTERVAL_SECONDS", 300))

    # ── vip_site cache — VIP/VVIP Site master data, pulled directly from
    # MSSQL's SITE_INFO (see app/services/vip/vip_site_sync_service.py) ──
    # A background job (app/services/vip/vip_site_scheduler.py) refreshes
    # this every VIP_SITE_SYNC_INTERVAL_SECONDS.
    VIP_SITE_SYNC_INTERVAL_SECONDS = int(os.environ.get("VIP_SITE_SYNC_INTERVAL_SECONDS", 300))

    # ── all-tasks summary — one combined "Total" log line across every
    # cache table (app/services/all_tasks_scheduler.py), on its own timer
    # independent of each job's own sync interval above ──
    ALL_TASKS_SUMMARY_INTERVAL_SECONDS = int(
        os.environ.get("ALL_TASKS_SUMMARY_INTERVAL_SECONDS", 300)
    )

    # ── Dashboard behavior ───────────────────────────────────────
    TIMEZONE = os.environ.get("TIMEZONE", "UTC")
    DEFAULT_THEME = os.environ.get("DEFAULT_THEME", "light")
    ROWS_PER_PAGE = int(os.environ.get("ROWS_PER_PAGE", 25))

    # Each user's Card Layout choices (order/hidden cards — see
    # app/static/js/card-layout.js) live only in their own browser's
    # localStorage, keyed partly on this value. Bumping it (a config
    # change, not a code edit) makes every existing saved key invisible to
    # the JS — old data is left alone in the browser, just never read
    # again — so every user resets to default the next time they open the
    # dashboard, with no action needed from them.
    CARD_LAYOUT_RESET_VERSION = os.environ.get("CARD_LAYOUT_RESET_VERSION", "1")

    # ── Logging ──────────────────────────────────────────────────
    # app/utils/logger.py writes every record (at LOG_LEVEL or above) to
    # LOG_PATH, and additionally mirrors ERROR/CRITICAL records to
    # LOG_ERROR_PATH, so failures are easy to find without grepping the
    # full app log.
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_PATH = os.environ.get("LOG_PATH", "logs/app.log")
    LOG_ERROR_PATH = os.environ.get("LOG_ERROR_PATH", "logs/error.log")

    # ── Session ──────────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(seconds=int(os.environ.get("SESSION_TIMEOUT", 3600)))

    # ── Notifications (optional integrations) ───────────────────
    TEAMS_WEBHOOK = os.environ.get("TEAMS_WEBHOOK", "")
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    # Comma-separated — one alert can go to more than one chat/group.
    TELEGRAM_CHAT_IDS = os.environ.get("TELEGRAM_CHAT_IDS", "")

    # ── Site Down Telegram alert (app/services/telegram/telegram_alert.py) ──
    # Sends Incident Site Down rows whose outage has passed
    # ALERT_THRESHOLD_MIN, every ALERT_INTERVAL_SECONDS.
    ALERT_THRESHOLD_MIN = int(os.environ.get("ALERT_THRESHOLD_MIN", 240))
    ALERT_INTERVAL_SECONDS = int(os.environ.get("ALERT_INTERVAL_SECONDS", 14400))

    # ── INC-WO Site Down Telegram alert
    # (app/services/telegram/telegram_inc_wo_alert.py) ──
    # Same shape as the alert above, but for the "INC-WO Site Down" card
    # (inc_wo_site_down cache) instead of "Incident Site Down", sent via a
    # SEPARATE bot (TELEGRAM_BOT_INC_WO_TOKEN) to its OWN chat/group
    # (TELEGRAM_CHAT_IDS_INC_WO) — a different bot posting to a different
    # group entirely, independent of TELEGRAM_CHAT_IDS above. Never starts
    # unless both TELEGRAM_BOT_INC_WO_TOKEN and TELEGRAM_CHAT_IDS_INC_WO
    # are set, independent of whether the Site Down alert above is
    # configured.
    #
    # Deliberately different defaults from the Site Down alert above:
    # threshold 0 (every current INC-WO Site Down row gets sent, not just
    # ones open past a threshold) and interval 900s/15min (not 4h) — this
    # alert is meant to read as "here's the current INC-WO Site Down list
    # right now", refreshed often, not "here's what's been open too long".
    TELEGRAM_BOT_INC_WO_TOKEN = os.environ.get("TELEGRAM_BOT_INC_WO_TOKEN", "")
    TELEGRAM_CHAT_IDS_INC_WO = os.environ.get("TELEGRAM_CHAT_IDS_INC_WO", "")
    INC_WO_ALERT_THRESHOLD_MIN = int(os.environ.get("INC_WO_ALERT_THRESHOLD_MIN", 0))
    INC_WO_ALERT_INTERVAL_SECONDS = int(os.environ.get("INC_WO_ALERT_INTERVAL_SECONDS", 900))

    # ── INC-WO Category Power Telegram alert
    # (app/services/telegram/telegram_inc_wo_power_alert.py) ──
    # Same shape as the INC-WO Site Down alert above, for category='power'
    # instead — a third, separate bot/chat, Telegram-only (no dashboard
    # card). Never starts unless both env vars are set.
    TELEGRAM_BOT_INC_WO_POWER_TOKEN = os.environ.get("TELEGRAM_BOT_INC_WO_POWER_TOKEN", "")
    TELEGRAM_CHAT_IDS_INC_WO_POWER = os.environ.get("TELEGRAM_CHAT_IDS_INC_WO_POWER", "")
    INC_WO_POWER_ALERT_THRESHOLD_MIN = int(os.environ.get("INC_WO_POWER_ALERT_THRESHOLD_MIN", 0))
    INC_WO_POWER_ALERT_INTERVAL_SECONDS = int(
        os.environ.get("INC_WO_POWER_ALERT_INTERVAL_SECONDS", 900)
    )

    # ── INC-WO General Telegram alert
    # (app/services/telegram/telegram_inc_wo_general_alert.py) ──
    # Every INC-WO category EXCEPT site_down/power (those two already have
    # their own dedicated alerts above) — a fourth, separate bot/chat,
    # Telegram-only (no dashboard card). Same threshold-0/900s defaults.
    # Never starts unless both env vars are set.
    TELEGRAM_BOT_INC_WO_GENERAL_TOKEN = os.environ.get("TELEGRAM_BOT_INC_WO_GENERAL_TOKEN", "")
    TELEGRAM_CHAT_IDS_INC_WO_GENERAL = os.environ.get("TELEGRAM_CHAT_IDS_INC_WO_GENERAL", "")
    INC_WO_GENERAL_ALERT_THRESHOLD_MIN = int(
        os.environ.get("INC_WO_GENERAL_ALERT_THRESHOLD_MIN", 0)
    )
    INC_WO_GENERAL_ALERT_INTERVAL_SECONDS = int(
        os.environ.get("INC_WO_GENERAL_ALERT_INTERVAL_SECONDS", 900)
    )

    # ── Teams webhook alerts (webhook/ package) ─────────────────────
    # Master on/off for the scheduled Teams sends (webhook.start(), called
    # from _init_webhook_alerts() below) and how often send_all() runs.
    # Each individual card's on/off is really "is its TEAMS_WEBHOOK_* URL
    # set in .env" (see webhook/common.py's resolve_url()), not a flag here.
    TEAMS_ALERTS_ENABLED = os.environ.get("TEAMS_ALERTS_ENABLED", "true").strip().lower() == "true"
    TEAMS_ALERT_INTERVAL_SECONDS = int(os.environ.get("TEAMS_ALERT_INTERVAL_SECONDS", 900))
    # When an alert has 0 active rows, the send is skipped by default (see
    # webhook/common.py's _send_empty_enabled()). Set to true to still post
    # a "no active alarms" card every cycle.
    WEBHOOK_SEND_EMPTY = os.environ.get("WEBHOOK_SEND_EMPTY", "false").strip().lower() == "true"
    # Base dashboard URL used to build each Teams card's "View Report" /
    # "View Dashboard" links (webhook/common.py). Blank = links omitted.
    DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")

    # ── Security ─────────────────────────────────────────────────
    WTF_CSRF_ENABLED = _bool(os.environ.get("CSRF_ENABLED"), default=True)

    JSON_SORT_KEYS = False


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    # Defaults to True (cookie only sent over HTTPS) — the correct setting
    # once this is actually served over HTTPS. Until then, plain HTTP
    # deployments (e.g. http://172.16.8.145:5000) need this set to False in
    # .env, or the session cookie holding the CSRF token never gets sent
    # back, and every form submit fails with "The CSRF session token is
    # missing." Set SESSION_COOKIE_SECURE=False in .env as a temporary
    # measure only — switch back to True once HTTPS is set up.
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), default=True)


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
