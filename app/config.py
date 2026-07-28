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

    # ── PostgreSQL — primary application database ───────────────
    # Currently unused: incidents/reports/mentor pages are still static
    # placeholders (see project memory), so these stay at their .env.example
    # defaults until that data gets wired in.
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
    SITE_LOOKUP_SYNC_INTERVAL_SECONDS = int(os.environ.get("SITE_LOOKUP_SYNC_INTERVAL_SECONDS", 300))

    # ── Incident cache — Incident table (object_322) on PostgreSQL ──
    # Read by app/repositories/incident/incident_repository.py. A background job
    # (app/services/incident/incident_scheduler.py) syncs this into the local cache
    # (instance/localstorage.db) every INCIDENT_SYNC_INTERVAL_SECONDS.
    # Same 5-minute default as SITE_SYNC_INTERVAL_SECONDS, so every
    # Postgres-backed sync job puts the same, predictable load on the DB.
    INCIDENT_SYNC_INTERVAL_SECONDS = int(os.environ.get("INCIDENT_SYNC_INTERVAL_SECONDS", 300))

    # ── ape_alarm cache — broader NE/connectivity alarms on object_138 ──
    # Read by app/repositories/ape_alarm/ape_alarm_repository.py. A background job
    # (app/services/ape_alarm/ape_alarm_scheduler.py) syncs this into the local cache
    # (instance/localstorage.db) every APE_ALARM_SYNC_INTERVAL_SECONDS.
    # object_138 is a 10M-row foreign table with no supporting index, so
    # this defaults to a much longer interval than
    # SITE/INCIDENT_SYNC_INTERVAL_SECONDS to keep that scan infrequent.
    APE_ALARM_SYNC_INTERVAL_SECONDS = int(os.environ.get("APE_ALARM_SYNC_INTERVAL_SECONDS", 900))

    # ── vip_alarm cache — every alarm type at VIP/VVIP sites, derived
    # locally from the already-synced ape_alarm cache (no Postgres call of
    # its own) ──
    # A background job (app/services/vip/vip_alarm_scheduler.py) rebuilds
    # this from ape_alarm + site_cache (both already-synced local tables)
    # every VIP_ALARM_SYNC_INTERVAL_SECONDS — see
    # app/services/vip/vip_alarm_sync_service.py.
    VIP_ALARM_SYNC_INTERVAL_SECONDS = int(os.environ.get("VIP_ALARM_SYNC_INTERVAL_SECONDS", 900))

    # ── vip_incident_alarm cache — purely local join of vip_alarm +
    # incident_by_status + site_cache (no Postgres call, no replica risk) ──
    # Read by app/repositories/vip/vip_incident_alarm_cache_repository.py. A
    # background job (app/services/vip/vip_incident_alarm_scheduler.py) rebuilds
    # this from the other three (already-synced) local tables every
    # VIP_INCIDENT_ALARM_SYNC_INTERVAL_SECONDS — short by default since this
    # is cheap, in-process work, not a Postgres round trip.
    VIP_INCIDENT_ALARM_SYNC_INTERVAL_SECONDS = int(os.environ.get("VIP_INCIDENT_ALARM_SYNC_INTERVAL_SECONDS", 60))

    # ── vip_site cache — VIP/VVIP Site master data, pulled directly from
    # MSSQL's SITE_INFO (see app/services/vip/vip_site_sync_service.py) ──
    # A background job (app/services/vip/vip_site_scheduler.py) refreshes
    # this every VIP_SITE_SYNC_INTERVAL_SECONDS.
    VIP_SITE_SYNC_INTERVAL_SECONDS = int(os.environ.get("VIP_SITE_SYNC_INTERVAL_SECONDS", 900))

    # ── all-tasks summary — one combined "Total" log line across every
    # cache table (app/services/all_tasks_scheduler.py), on its own timer
    # independent of each job's own sync interval above ──
    ALL_TASKS_SUMMARY_INTERVAL_SECONDS = int(os.environ.get("ALL_TASKS_SUMMARY_INTERVAL_SECONDS", 300))

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

    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "")

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
    SESSION_COOKIE_SECURE = True


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
