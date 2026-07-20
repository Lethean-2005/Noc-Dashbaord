"""Application configuration.

Config (below) reads every setting from the environment once, at class-
definition time — so app/__init__.py MUST call load_dotenv() before this
module is ever imported, or .env values are silently ignored in favor of
the hardcoded defaults here.

DevelopmentConfig / TestingConfig / ProductionConfig only override what
differs from the base Config; config_map picks one by APP_ENV.
"""
import os
from datetime import timedelta


def _bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    """Base configuration shared by all environments."""

    # ── Application ──────────────────────────────────────────────
    APP_NAME = os.environ.get("APP_NAME", "Dashboard")
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")

    # ── Server ───────────────────────────────────────────────────
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", 5000))

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
    # Read by app/database/mssql.py. A background job (app/services/alarm_scheduler.py)
    # syncs this into the local cache (instance/localstorage.db) every
    # MSSQL_SYNC_INTERVAL_SECONDS — pages read the cache, never MSSQL directly.
    MSSQL_HOST = os.environ.get("MSSQL_HOST", "")
    MSSQL_DATABASE = os.environ.get("MSSQL_DATABASE", "")
    MSSQL_USER = os.environ.get("MSSQL_USER", "")
    MSSQL_PASSWORD = os.environ.get("MSSQL_PASSWORD", "")
    MSSQL_SYNC_INTERVAL_SECONDS = int(os.environ.get("MSSQL_SYNC_INTERVAL_SECONDS", 10))

    # ── Site cache — Site table (object_160) on PostgreSQL ──────
    # Read by app/repositories/site_repository.py. A background job
    # (app/services/site_scheduler.py) syncs this into the local cache
    # (instance/localstorage.db) every SITE_SYNC_INTERVAL_SECONDS. Site data
    # changes far less often than live alarms, so this defaults to a much
    # longer interval than MSSQL_SYNC_INTERVAL_SECONDS.
    SITE_SYNC_INTERVAL_SECONDS = int(os.environ.get("SITE_SYNC_INTERVAL_SECONDS", 300))

    # ── Incident cache — Incident table (object_322) on PostgreSQL ──
    # Read by app/repositories/incident_repository.py. A background job
    # (app/services/incident_scheduler.py) syncs this into the local cache
    # (instance/localstorage.db) every INCIDENT_SYNC_INTERVAL_SECONDS.
    # Incidents change more often than Site master data, so this defaults to
    # a shorter interval than SITE_SYNC_INTERVAL_SECONDS.
    INCIDENT_SYNC_INTERVAL_SECONDS = int(os.environ.get("INCIDENT_SYNC_INTERVAL_SECONDS", 60))

    # ── Dashboard behavior ───────────────────────────────────────
    TIMEZONE = os.environ.get("TIMEZONE", "UTC")
    DEFAULT_THEME = os.environ.get("DEFAULT_THEME", "light")
    AUTO_REFRESH_SECONDS = int(os.environ.get("AUTO_REFRESH_SECONDS", 60))
    ROWS_PER_PAGE = int(os.environ.get("ROWS_PER_PAGE", 25))

    # ── Logging ──────────────────────────────────────────────────
    # app/utils/logger.py writes every record (at LOG_LEVEL or above) to
    # LOG_PATH, and additionally mirrors ERROR/CRITICAL records to
    # LOG_ERROR_PATH, so failures are easy to find without grepping the
    # full app log.
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_PATH = os.environ.get("LOG_PATH", "logs/app.log")
    LOG_ERROR_PATH = os.environ.get("LOG_ERROR_PATH", "logs/error.log")

    # ── Flask-Caching (page/view cache, separate from the MSSQL cache) ──
    CACHE_ENABLED = _bool(os.environ.get("CACHE_ENABLED"), default=True)
    CACHE_TYPE = "SimpleCache" if CACHE_ENABLED else "NullCache"
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get("CACHE_TIMEOUT", 300))

    # ── Session ──────────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(seconds=int(os.environ.get("SESSION_TIMEOUT", 3600)))

    # ── Notifications (optional integrations) ───────────────────
    TEAMS_WEBHOOK = os.environ.get("TEAMS_WEBHOOK", "")
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    # Comma-separated — one alert can go to more than one chat/group.
    TELEGRAM_CHAT_IDS = os.environ.get("TELEGRAM_CHAT_IDS", "")

    # ── Site Down Telegram alert (app/services/telegram_alert.py) ──
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
