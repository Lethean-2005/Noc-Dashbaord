"""Application configuration.

Config reads every setting from the environment once, at class-
definition time — app/__init__.py must call load_dotenv() before this
module is imported, or .env values are silently ignored. Feature flags
are the exception (see get_feature_flags() — re-read per request).

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


# One flag per dashboard card. Re-read straight from .env on every
# request (see get_feature_flags() + app/__init__.py's `features`
# context processor) instead of once at startup, so toggling a card
# takes effect on the next page load with no restart.
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
    FEATURE_* flag as {key: bool}, defaulting to True if unset."""
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
    STREAMLINE_BASE_URL = os.environ.get("STREAMLINE_BASE_URL", "https://prd-web-mc.cellcard.com.kh").rstrip("/")
    APP_NAME = os.environ.get("APP_NAME", "Dashboard")
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
    # Caps request body size so an oversized upload can't be read fully
    # into memory in one go. 5 MB was generous for a site_code CSV (the
    # only upload in the app until now); 20 MB leaves room for the
    # Incident Report's Picture Reference photos (a handful of phone
    # photos per report, base64-encoded into the database — see
    # incident_report_service.py's own note on why).
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 20 * 1024 * 1024))

    # ── Server ───────────────────────────────────────────────────
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", 8000))
    # waitress's default of 4 threads is too few once several NOC staff
    # have the dashboard open — page loads make several sequential
    # SQLite reads and reload on a synchronized timer. See run.py.
    WAITRESS_THREADS = int(os.environ.get("WAITRESS_THREADS", 8))

    # ── PostgreSQL — Incident/Site/VIP data source ──────────────
    # Read by app/database/connection.py's run_query().
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
    # Synced into the local cache every MSSQL_SYNC_INTERVAL_SECONDS by
    # app/services/alarm/alarm_scheduler.py; pages read the cache only.
    MSSQL_HOST = os.environ.get("MSSQL_HOST", "")
    MSSQL_DATABASE = os.environ.get("MSSQL_DATABASE", "")
    MSSQL_USER = os.environ.get("MSSQL_USER", "")
    MSSQL_PASSWORD = os.environ.get("MSSQL_PASSWORD", "")
    MSSQL_SYNC_INTERVAL_SECONDS = int(os.environ.get("MSSQL_SYNC_INTERVAL_SECONDS", 10))

    # ── Site cache — Site table (object_160) on PostgreSQL ──────
    # Longer interval than MSSQL's — site data changes far less often
    # than live alarms.
    SITE_SYNC_INTERVAL_SECONDS = int(os.environ.get("SITE_SYNC_INTERVAL_SECONDS", 300))

    # ── site_lookup cache — site_lookup_mv on PostgreSQL ─────────
    # The lookup table get_processed_site() uses — see
    # app/utils/get_processed_site.py.
    SITE_LOOKUP_SYNC_INTERVAL_SECONDS = int(
        os.environ.get("SITE_LOOKUP_SYNC_INTERVAL_SECONDS", 300)
    )

    # ── Incident cache — Incident table (object_322) on PostgreSQL ──
    INCIDENT_SYNC_INTERVAL_SECONDS = int(os.environ.get("INCIDENT_SYNC_INTERVAL_SECONDS", 300))

    # ── Congestion History cache — historical TCT bandwidth/congestion
    # alarms on MSSQL (noc.TBL_PPD), for the dashboard's Congestion
    # History card + drilldown. A much slower cadence than the 10s
    # active-only alarm sync (MSSQL_SYNC_INTERVAL_SECONDS above) since
    # this reads a wide historical window, not just currently-active
    # rows. CONGESTION_HISTORY_WEEKS is the single source of truth for
    # both how far back to sync AND how many weeks the chart displays.
    CONGESTION_SYNC_INTERVAL_SECONDS = int(os.environ.get("CONGESTION_SYNC_INTERVAL_SECONDS", 300))
    CONGESTION_HISTORY_WEEKS = int(os.environ.get("CONGESTION_HISTORY_WEEKS", 4))

    # ── Dashboard data-freshness heartbeat (logs/dashboard.log) ─────
    # Logs "Dashboard data as of: ..." on a clock-aligned schedule so
    # dashboard.log has a regular trace even between page views.
    DASHBOARD_LOG_INTERVAL_SECONDS = int(os.environ.get("DASHBOARD_LOG_INTERVAL_SECONDS", 300))

    # ── ape_alarm cache — broader NE/connectivity alarms on object_138 ──
    # object_138 is a 10M-row foreign table with no supporting index —
    # every sync is a heavy scan.
    APE_ALARM_SYNC_INTERVAL_SECONDS = int(os.environ.get("APE_ALARM_SYNC_INTERVAL_SECONDS", 300))

    # ── vip_alarm cache — derived locally from ape_alarm + site_cache,
    # no separate Postgres call. See vip_alarm_sync_service.py.
    VIP_ALARM_SYNC_INTERVAL_SECONDS = int(os.environ.get("VIP_ALARM_SYNC_INTERVAL_SECONDS", 300))

    # ── vip_site cache — VIP/VVIP Site master data from MSSQL's SITE_INFO.
    VIP_SITE_SYNC_INTERVAL_SECONDS = int(os.environ.get("VIP_SITE_SYNC_INTERVAL_SECONDS", 300))

    # ── pop cache — POP master data from MSSQL's TBL_POP.
    POP_SYNC_INTERVAL_SECONDS = int(os.environ.get("POP_SYNC_INTERVAL_SECONDS", 300))

    # ── mssql_site_onair cache — On-Air site master data from MSSQL's
    # TBL_SITE joined to TBL_NE for VENDOR, independent from
    # Postgres's site_cache.
    MSSQL_SITE_ONAIR_SYNC_INTERVAL_SECONDS = int(
        os.environ.get("MSSQL_SITE_ONAIR_SYNC_INTERVAL_SECONDS", 300)
    )

    # ── partner_contact cache — from MSSQL's TBL_PARTNER /
    # TBL_PARTNER_CONTACT.
    PARTNER_CONTACT_SYNC_INTERVAL_SECONDS = int(
        os.environ.get("PARTNER_CONTACT_SYNC_INTERVAL_SECONDS", 300)
    )

    # Shared password gate in front of Partner Contact's bulk Import button
    # (checked server-side in routes/partner_contact.py — the browser
    # never holds this value, only what the user typed).
    PARTNER_CONTACT_IMPORT_PASSWORD = os.environ.get(
        "PARTNER_CONTACT_IMPORT_PASSWORD", "nocdashboard"
    )

    # ── all-tasks summary — one combined "Total" log line across every
    # cache table, on its own timer.
    ALL_TASKS_SUMMARY_INTERVAL_SECONDS = int(
        os.environ.get("ALL_TASKS_SUMMARY_INTERVAL_SECONDS", 300)
    )

    # ── Dashboard behavior ───────────────────────────────────────
    TIMEZONE = "Asia/Phnom_Penh"
    DEFAULT_THEME = os.environ.get("DEFAULT_THEME", "light")
    ROWS_PER_PAGE = int(os.environ.get("ROWS_PER_PAGE", 25))

    # Card Layout choices live in each user's browser localStorage,
    # keyed partly on this value — bumping it resets everyone's saved
    # layout to default on next load, with no code change needed.
    CARD_LAYOUT_RESET_VERSION = os.environ.get("CARD_LAYOUT_RESET_VERSION", "1")

    # ── Logging ──────────────────────────────────────────────────
    # app/utils/logger.py writes every record to LOG_PATH and mirrors
    # ERROR/CRITICAL to LOG_ERROR_PATH.
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
    TELEGRAM_CHAT_IDS = os.environ.get("TELEGRAM_CHAT_IDS", "")  # comma-separated

    # ── Site Down Telegram alert (telegram_alert.py) ──
    # Sends Incident Site Down rows over ALERT_THRESHOLD_MIN, every
    # ALERT_INTERVAL_SECONDS.
    ALERT_THRESHOLD_MIN = int(os.environ.get("ALERT_THRESHOLD_MIN", 240))
    ALERT_INTERVAL_SECONDS = int(os.environ.get("ALERT_INTERVAL_SECONDS", 14400))

    # ── INC-WO Site Down Telegram alert (telegram_inc_wo_alert.py) ──
    # Own bot/chat, independent of the Site Down alert above. Threshold
    # 0 / interval 900s by design — reads as "current list right now",
    # not "open too long". Never starts unless both env vars are set.
    TELEGRAM_BOT_INC_WO_TOKEN = os.environ.get("TELEGRAM_BOT_INC_WO_TOKEN", "")
    TELEGRAM_CHAT_IDS_INC_WO = os.environ.get("TELEGRAM_CHAT_IDS_INC_WO", "")
    INC_WO_ALERT_THRESHOLD_MIN = int(os.environ.get("INC_WO_ALERT_THRESHOLD_MIN", 0))
    INC_WO_ALERT_INTERVAL_SECONDS = int(os.environ.get("INC_WO_ALERT_INTERVAL_SECONDS", 900))

    # ── INC-WO Category Power Telegram alert
    # (telegram_inc_wo_power_alert.py) ── category='power', own
    # bot/chat, Telegram-only. Never starts unless both env vars are set.
    TELEGRAM_BOT_INC_WO_POWER_TOKEN = os.environ.get("TELEGRAM_BOT_INC_WO_POWER_TOKEN", "")
    TELEGRAM_CHAT_IDS_INC_WO_POWER = os.environ.get("TELEGRAM_CHAT_IDS_INC_WO_POWER", "")
    INC_WO_POWER_ALERT_THRESHOLD_MIN = int(os.environ.get("INC_WO_POWER_ALERT_THRESHOLD_MIN", 0))
    INC_WO_POWER_ALERT_INTERVAL_SECONDS = int(
        os.environ.get("INC_WO_POWER_ALERT_INTERVAL_SECONDS", 900)
    )

    # ── INC-WO General Telegram alert
    # (telegram_inc_wo_general_alert.py) ── every category except
    # site_down/power, own bot/chat, Telegram-only.
    TELEGRAM_BOT_INC_WO_GENERAL_TOKEN = os.environ.get("TELEGRAM_BOT_INC_WO_GENERAL_TOKEN", "")
    TELEGRAM_CHAT_IDS_INC_WO_GENERAL = os.environ.get("TELEGRAM_CHAT_IDS_INC_WO_GENERAL", "")
    INC_WO_GENERAL_ALERT_THRESHOLD_MIN = int(
        os.environ.get("INC_WO_GENERAL_ALERT_THRESHOLD_MIN", 0)
    )
    INC_WO_GENERAL_ALERT_INTERVAL_SECONDS = int(
        os.environ.get("INC_WO_GENERAL_ALERT_INTERVAL_SECONDS", 900)
    )

    # ── Site Down 24h Teams alert
    # (app/services/incident/site_down_24h_alert_service.py) ── 2 posts
    # per incident: a down-over-24h alert, and later a separate
    # restored-confirmation once it actually resolves — never resent,
    # unlike every alert in webhook/. Each has its own Power Automate
    # flow/URL (SITE_DOWN_24H_ALERT_WEBHOOK_URL / _RESTORE_WEBHOOK_URL
    # in .env) — renamed from the original placeholder TESTING_WEBHOOK_URL/
    # TESTING_REPLY names once both flows were confirmed working, so .env
    # now names each by what it actually does instead of "testing".
    SITE_DOWN_24H_ALERT_WEBHOOK_URL = os.environ.get("SITE_DOWN_24H_ALERT_WEBHOOK_URL", "")
    # Separate flow/URL for the restore-confirmation — the down-alert's
    # own flow saves each post's Teams Message ID into a SharePoint list
    # keyed by incident_ref (no Premium license for a Response action),
    # and THIS flow looks that row up, replies in the same thread using
    # it, then deletes the row. Two independent flows rather than one
    # flow with a branch, since this trigger type's designer doesn't
    # support moving already-built actions into a condition branch
    # without a fragile manual drag — a second copy of the same simple
    # trigger->actions shape the user already knows how to build.
    SITE_DOWN_24H_ALERT_RESTORE_WEBHOOK_URL = os.environ.get(
        "SITE_DOWN_24H_ALERT_RESTORE_WEBHOOK_URL", ""
    )
    # How often the down-alert check runs — 5 minutes, so an incident
    # gets caught shortly after it actually crosses the threshold
    # instead of waiting up to a full day for the next daily check.
    SITE_DOWN_24H_ALERT_INTERVAL_SECONDS = int(
        os.environ.get("SITE_DOWN_24H_ALERT_INTERVAL_SECONDS", 300)
    )
    # How often the restore-confirmation check runs — same 5 minutes as
    # the down-alert check above, so a restore is noticed within minutes
    # of actually happening, not up to 15 later.
    SITE_DOWN_24H_ALERT_RESTORE_INTERVAL_SECONDS = int(
        os.environ.get("SITE_DOWN_24H_ALERT_RESTORE_INTERVAL_SECONDS", 300)
    )
    SITE_DOWN_24H_ALERT_THRESHOLD_HOURS = int(
        os.environ.get("SITE_DOWN_24H_ALERT_THRESHOLD_HOURS", 24)
    )

    # ── Teams webhook alerts (webhook/ package) ─────────────────────
    # Each card's on/off is really "is its TEAMS_WEBHOOK_* URL set" (see
    # webhook/common.py's resolve_url()), not a flag here.
    TEAMS_ALERTS_ENABLED = os.environ.get("TEAMS_ALERTS_ENABLED", "true").strip().lower() == "true"
    TEAMS_ALERT_INTERVAL_SECONDS = int(os.environ.get("TEAMS_ALERT_INTERVAL_SECONDS", 900))
    # An alert with 0 active rows is skipped by default; true posts a
    # "no active alarms" card every cycle.
    WEBHOOK_SEND_EMPTY = os.environ.get("WEBHOOK_SEND_EMPTY", "false").strip().lower() == "true"
    # Base dashboard URL for each Teams card's link. Blank omits it.
    DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")

    # ── Security ─────────────────────────────────────────────────
    WTF_CSRF_ENABLED = _bool(os.environ.get("CSRF_ENABLED"), default=True)
    # Flask-WTF defaults this to 3600s (1 hour) if unset. Pages like
    # Partner Contact render their csrf_token once at page load and never
    # reload (no periodic location.reload() like the dashboard has), so a
    # NOC operator who leaves the tab open past an hour hit "Bad Request —
    # the CSRF token has expired" on their next Edit/Delete (confirmed
    # live). This app has no login system to tie token lifetime to (see
    # MEMORY: unused Flask-Login scaffold), so there's no real security
    # boundary a time limit is protecting here — None disables the
    # time-based expiry entirely; the token still only validates for
    # requests carrying the matching session cookie.
    WTF_CSRF_TIME_LIMIT = None

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
    # Defaults True (HTTPS-only cookie). Plain-HTTP deployments need
    # this False in .env, or CSRF form submits fail — switch back to
    # True once HTTPS is set up.
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), default=True)


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
