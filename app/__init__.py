"""Application factory."""

import os
from importlib import import_module

from dotenv import load_dotenv

# Must run before `app.config` is imported — Config reads os.environ at
# class-definition time, so .env values loaded any later are silently ignored.
load_dotenv()

from flask import Flask  # noqa: E402 — must come after load_dotenv() above

from app.config import config_map  # noqa: E402
from app.extensions import csrf, db, login_manager  # noqa: E402


def create_app(env=None, instance_path=None):
    """`instance_path`, if given, overrides Flask's default instance folder
    (where instance/localstorage.db lives — see app/database/cache.py). Only
    tests pass this, so each test run gets its own empty SQLite cache
    instead of reading whatever real data happens to be synced into the
    dev machine's instance/localstorage.db."""
    env = env or os.environ.get("APP_ENV", "default")
    
    app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    app.config.from_object(config_map[env])

    os.makedirs(app.instance_path, exist_ok=True)

    _register_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_template_filters(app)
    _register_context_processors(app)
    _init_cache_db(app)
    _start_background_jobs(app)
    _init_telegram_alert(app)
    _init_inc_wo_telegram_alert(app)
    _init_inc_wo_power_telegram_alert(app)
    _init_inc_wo_general_telegram_alert(app)
    _init_webhook_alerts(app)

    return app


def _register_extensions(app):
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)


def _register_blueprints(app):
    from app.routes.dashboard import dashboard_bp
    from app.routes.map_view import map_view_bp
    from app.routes.mentor import mentor_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(mentor_bp, url_prefix="/mentor")
    app.register_blueprint(map_view_bp, url_prefix="/map")


def _register_template_filters(app):
    from app.utils.formatter import badge_color, status_badge_class

    app.jinja_env.filters["badge_color"] = badge_color
    app.jinja_env.filters["status_badge_class"] = status_badge_class


def _register_context_processors(app):
    @app.context_processor
    def inject_feature_flags():
        from app.config import get_feature_flags

        return {"features": get_feature_flags()}


def _init_cache_db(app):
    """Create every local cache table (instance/localstorage.db) up front,
    always, so routes can query them even before the first sync lands."""
    from app.database.cache import init_cache_db

    with app.app_context():
        init_cache_db()


# (scheduler module, config key holding its interval in seconds) — every
# entry here used to be its own near-identical _init_*_cache() function
# (~100 lines total) repeating the same testing/debug-reloader skip-guard
# by hand. Collapsed into _start_background_jobs() below; add a domain's
# background sync here instead of writing a new function for it.
_BACKGROUND_JOBS = (
    ("app.services.alarm.alarm_scheduler", "MSSQL_SYNC_INTERVAL_SECONDS"),
    ("app.services.site.site_scheduler", "SITE_SYNC_INTERVAL_SECONDS"),
    ("app.services.site.site_lookup_scheduler", "SITE_LOOKUP_SYNC_INTERVAL_SECONDS"),
    ("app.services.incident.incident_scheduler", "INCIDENT_SYNC_INTERVAL_SECONDS"),
    ("app.services.ape_alarm.ape_alarm_scheduler", "APE_ALARM_SYNC_INTERVAL_SECONDS"),
    ("app.services.vip.vip_alarm_scheduler", "VIP_ALARM_SYNC_INTERVAL_SECONDS"),
    ("app.services.vip.vip_site_scheduler", "VIP_SITE_SYNC_INTERVAL_SECONDS"),
    ("app.services.all_tasks_scheduler", "ALL_TASKS_SUMMARY_INTERVAL_SECONDS"),
    ("app.routes.dashboard", "DASHBOARD_LOG_INTERVAL_SECONDS"),
)


def _start_background_jobs(app):
    """Starts every scheduler in _BACKGROUND_JOBS. Skipped in tests (no real
    MSSQL/Postgres to hit), under the Werkzeug debug reloader skipped in the
    watcher parent process so nothing starts twice, and skipped for now in
    any process that isn't this machine's leader (see leader_lock.py) — so
    an externally-duplicated `run.py` process still serves HTTP normally but
    never runs its own duplicate set of schedulers. A follower doesn't stay
    a follower forever: wait_for_leadership() keeps retrying in the
    background and starts these same jobs automatically the moment the
    leader disappears, instead of needing every process manually restarted."""
    if app.testing:
        return
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    def _start_all():
        for module_path, config_key in _BACKGROUND_JOBS:
            import_module(module_path).start(app, app.config[config_key])

    from app.services.leader_lock import is_leader, wait_for_leadership

    if is_leader():
        _start_all()
        return

    from app.utils.logger import get_logger

    get_logger(__name__).info(
        "Another process already owns background sync — this process will serve HTTP "
        "requests only for now, and take over automatically if that process stops."
    )
    wait_for_leadership(_start_all)


def _init_telegram_alert(app):
    """Start the background Telegram Site Down alert loop (every
    ALERT_INTERVAL_SECONDS). Reads the incident_by_status cache that the
    incident scheduler (see _BACKGROUND_JOBS above) already keeps in sync —
    no new cache table needed here. Same skip conditions as
    _start_background_jobs() (including the leader_lock check with the same
    automatic-takeover-on-leader-loss behavior — a follower process must
    not send duplicate Telegram alerts either); additionally a no-op
    whenever TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_IDS aren't set, so a dev
    machine without those in .env just never starts this thread."""
    if app.testing:
        return
    if not app.config.get("TELEGRAM_BOT_TOKEN") or not app.config.get("TELEGRAM_CHAT_IDS"):
        return
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from app.services.leader_lock import is_leader, wait_for_leadership
        from app.services.telegram.telegram_alert import start

        def _start_telegram():
            start(app, app.config["ALERT_INTERVAL_SECONDS"])

        if is_leader():
            _start_telegram()
        else:
            wait_for_leadership(_start_telegram)


def _init_inc_wo_telegram_alert(app):
    """Start the background Telegram INC-WO Site Down alert loop (every
    INC_WO_ALERT_INTERVAL_SECONDS). Same skip conditions as
    _init_telegram_alert() above, but gated on
    TELEGRAM_BOT_INC_WO_TOKEN/TELEGRAM_CHAT_IDS_INC_WO instead of
    TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_IDS — a separate bot posting to its
    own chat, independent of whether the Site Down alert above is
    configured. See app/services/telegram/telegram_inc_wo_alert.py."""
    if app.testing:
        return
    if not app.config.get("TELEGRAM_BOT_INC_WO_TOKEN") or not app.config.get(
        "TELEGRAM_CHAT_IDS_INC_WO"
    ):
        return
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from app.services.leader_lock import is_leader, wait_for_leadership
        from app.services.telegram.telegram_inc_wo_alert import start

        def _start_inc_wo_telegram():
            start(app, app.config["INC_WO_ALERT_INTERVAL_SECONDS"])

        if is_leader():
            _start_inc_wo_telegram()
        else:
            wait_for_leadership(_start_inc_wo_telegram)


def _init_inc_wo_power_telegram_alert(app):
    """Start the background Telegram INC-WO Category Power alert loop —
    same skip conditions as _init_inc_wo_telegram_alert() above, but
    gated on TELEGRAM_BOT_INC_WO_POWER_TOKEN/TELEGRAM_CHAT_IDS_INC_WO_POWER,
    a third, separate bot/chat."""
    if app.testing:
        return
    if not app.config.get("TELEGRAM_BOT_INC_WO_POWER_TOKEN") or not app.config.get(
        "TELEGRAM_CHAT_IDS_INC_WO_POWER"
    ):
        return
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from app.services.leader_lock import is_leader, wait_for_leadership
        from app.services.telegram.telegram_inc_wo_power_alert import start

        def _start_inc_wo_power_telegram():
            start(app, app.config["INC_WO_POWER_ALERT_INTERVAL_SECONDS"])

        if is_leader():
            _start_inc_wo_power_telegram()
        else:
            wait_for_leadership(_start_inc_wo_power_telegram)


def _init_inc_wo_general_telegram_alert(app):
    """Start the background Telegram INC-WO General alert loop — same
    skip conditions as _init_inc_wo_power_telegram_alert() above, but
    gated on TELEGRAM_BOT_INC_WO_GENERAL_TOKEN/TELEGRAM_CHAT_IDS_INC_WO_GENERAL,
    a fourth, separate bot/chat."""
    if app.testing:
        return
    if not app.config.get("TELEGRAM_BOT_INC_WO_GENERAL_TOKEN") or not app.config.get(
        "TELEGRAM_CHAT_IDS_INC_WO_GENERAL"
    ):
        return
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from app.services.leader_lock import is_leader, wait_for_leadership
        from app.services.telegram.telegram_inc_wo_general_alert import start

        def _start_inc_wo_general_telegram():
            start(app, app.config["INC_WO_GENERAL_ALERT_INTERVAL_SECONDS"])

        if is_leader():
            _start_inc_wo_general_telegram()
        else:
            wait_for_leadership(_start_inc_wo_general_telegram)


def _init_webhook_alerts(app):
    """Start the background Teams webhook alert loop (every
    TEAMS_ALERT_INTERVAL_SECONDS — see webhook/__init__.py's start()). Same
    skip conditions as _init_telegram_alert() above (including the
    leader_lock automatic-takeover-on-leader-loss behavior — a follower
    process must not send duplicate Teams alerts either); additionally a
    no-op whenever TEAMS_ALERTS_ENABLED is false, so it can be switched off
    in .env without touching code."""
    if app.testing:
        return
    if not app.config.get("TEAMS_ALERTS_ENABLED"):
        return
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from app.services.leader_lock import is_leader, wait_for_leadership
        from webhook import start

        def _start_webhook_alerts():
            start(app, app.config["TEAMS_ALERT_INTERVAL_SECONDS"])

        if is_leader():
            _start_webhook_alerts()
        else:
            wait_for_leadership(_start_webhook_alerts)


def _register_error_handlers(app):
    from flask import render_template

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template("errors/500.html"), 500
