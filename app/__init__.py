"""Application factory."""
import os

from dotenv import load_dotenv

# Must run before `app.config` is imported — Config reads os.environ at
# class-definition time, so .env values loaded any later are silently ignored.
load_dotenv()

from flask import Flask  # noqa: E402 — must come after load_dotenv() above

from app.config import config_map  # noqa: E402
from app.extensions import cache, csrf, db, login_manager  # noqa: E402


def create_app(env=None):
    env = env or os.environ.get("APP_ENV", "default")

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_map[env])

    os.makedirs(app.instance_path, exist_ok=True)

    _register_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_template_filters(app)
    _init_alarm_cache(app)
    _init_site_cache(app)
    _init_incident_cache(app)
    _init_telegram_alert(app)

    return app


def _register_extensions(app):
    db.init_app(app)
    cache.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)


def _register_blueprints(app):
    from app.routes.api import api_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.mentor import mentor_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(mentor_bp, url_prefix="/mentor")
    app.register_blueprint(api_bp, url_prefix="/api")


def _register_template_filters(app):
    from app.utils.formatter import badge_color

    app.jinja_env.filters["badge_color"] = badge_color


def _init_alarm_cache(app):
    """Create the local alarm cache tables (instance/localstorage.db) —
    always, so routes can query them even before the first sync — then start
    the background MSSQL sync. The sync thread itself is skipped in tests (no
    real MSSQL to hit) and, under the Werkzeug debug reloader, skipped in
    the watcher parent process so it doesn't run twice."""
    from app.database.cache import init_cache_db

    with app.app_context():
        init_cache_db()
    if app.testing:
        return
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from app.services.alarm_scheduler import start

        start(app, app.config["MSSQL_SYNC_INTERVAL_SECONDS"])


def _init_site_cache(app):
    """Start the background Postgres Site sync. The site_cache table itself
    is already created by _init_alarm_cache()'s call to init_cache_db()
    (that one function creates every cache table, alarm and site alike), so
    this only needs to start the scheduler thread — same skip conditions as
    _init_alarm_cache (no real Postgres to hit in tests; only the debug
    reloader's live child process, not its watcher parent)."""
    if app.testing:
        return
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from app.services.site_scheduler import start

        start(app, app.config["SITE_SYNC_INTERVAL_SECONDS"])


def _init_incident_cache(app):
    """Start the background Postgres Incident/INC-WO sync. Both cache tables
    (incident_by_status, inc_wo_by_status) are already created by
    _init_alarm_cache()'s call to init_cache_db() (that one function creates
    every cache table), so this only needs to start the scheduler thread —
    same skip conditions as _init_site_cache."""
    if app.testing:
        return
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from app.services.incident_scheduler import start

        start(app, app.config["INCIDENT_SYNC_INTERVAL_SECONDS"])


def _init_telegram_alert(app):
    """Start the background Telegram Site Down alert loop (every
    ALERT_INTERVAL_SECONDS). Reads the incident_by_status cache that
    _init_incident_cache() already keeps in sync — no new cache table needed
    here. Same skip conditions as the other _init_* functions; additionally
    a no-op whenever TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_IDS aren't set, so a
    dev machine without those in .env just never starts this thread."""
    if app.testing:
        return
    if not app.config.get("TELEGRAM_BOT_TOKEN") or not app.config.get("TELEGRAM_CHAT_IDS"):
        return
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from app.services.telegram_alert import start

        start(app, app.config["ALERT_INTERVAL_SECONDS"])


def _register_error_handlers(app):
    from flask import render_template

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template("errors/500.html"), 500
