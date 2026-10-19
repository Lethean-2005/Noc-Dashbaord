"""Application factory."""

import os
from importlib import import_module

from dotenv import load_dotenv

# Must run before `app.config` is imported — Config reads os.environ at
# class-definition time, so .env values loaded any later are silently ignored.
load_dotenv()

from flask import Flask, request  # noqa: E402 — must come after load_dotenv() above

from app.config import config_map  # noqa: E402
from app.extensions import compress, csrf, db, login_manager  # noqa: E402


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
    _register_static_cache_headers(app)
    _init_cache_db(app)
    _validate_scheduler_offsets()
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
    compress.init_app(app)


def _register_blueprints(app):
    from app.routes.dashboard import dashboard_bp
    from app.routes.help import help_bp
    from app.routes.incident_report import incident_report_bp
    from app.routes.map_view import map_view_bp
    from app.routes.mentor import mentor_bp
    from app.routes.partner_contact import partner_contact_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(mentor_bp, url_prefix="/mentor")
    app.register_blueprint(map_view_bp, url_prefix="/map")
    app.register_blueprint(partner_contact_bp)
    app.register_blueprint(incident_report_bp, url_prefix="/incident-report")
    app.register_blueprint(help_bp)


def _register_template_filters(app):
    from app.utils.formatter import badge_color, status_badge_class

    app.jinja_env.filters["badge_color"] = badge_color
    app.jinja_env.filters["status_badge_class"] = status_badge_class

    def versioned_static(filename):
        """url_for('static', filename=...) with a `?v=<mtime>` query
        string appended — busts the browser's cache the instant a static
        file's content actually changes (a new mtime is a new URL)
        instead of relying on a manual hard-refresh to see an edit. Real
        pain point during active work on a page's own JS/CSS (confirmed
        live: several fixes today looked "not applied" purely because
        the browser kept serving an old cached copy of incident-report.js
        under its unchanging static URL). Falls back to a plain url_for()
        if the file can't be stat'd (e.g. a typo'd path), so a missing
        asset still 404s normally instead of raising here."""
        from flask import url_for

        try:
            mtime = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
        except OSError:
            return url_for("static", filename=filename)
        return url_for("static", filename=filename, v=mtime)

    app.jinja_env.globals["versioned_static"] = versioned_static


def _register_static_cache_headers(app):
    """Every /static/ response was being sent as `Cache-Control:
    no-cache` (confirmed via a direct header check) — forcing the
    browser to round-trip a revalidation request to the server for
    EVERY static asset on EVERY page load, even when nothing changed.
    That's a real, measured cost: the dashboard's own auto-reload
    (dashboard/index.html's location.reload(), every
    DASHBOARD_LOG_INTERVAL_SECONDS) re-fetches dozens of CSS/JS/font
    files this way, several of them individually 100KB-1MB+ (tabler-
    icons alone is over 1MB). This is now safe to fix with a FAR-future
    cache instead: every template's own static reference was converted
    from a plain url_for('static', ...) to versioned_static() (this
    file's own helper, below) — which already appends `?v=<file mtime>`
    — so the URL itself changes the instant a file's content does;
    nothing stays "permanently cached" in the sense of never updating,
    it's just keyed to a URL that's only reused while the file is
    actually unchanged."""

    @app.after_request
    def _add_static_cache_control(response):
        if request.endpoint == "static":
            # Flask's own send_static_file() already sets `no-cache` by
            # default — just adding max_age/public on TOP of that (the
            # first version of this fix) left both directives present
            # together, which is self-contradictory: `no-cache` tells
            # the browser to revalidate on every single request
            # regardless of max-age, silently cancelling out the whole
            # point of this change. no_cache must be explicitly cleared
            # (None, not False — Werkzeug only drops the directive from
            # the header entirely for None) before the long-lived
            # directives below actually take effect.
            response.cache_control.no_cache = None
            response.cache_control.public = True
            response.cache_control.max_age = 31536000  # 1 year
            response.cache_control.immutable = True
        return response


def _register_context_processors(app):
    @app.context_processor
    def inject_feature_flags():
        from app.config import get_feature_flags

        return {"features": get_feature_flags()}


def _init_cache_db(app):
    """Create every local cache table (instance/localstorage.db) up front,
    always, so routes can query them even before the first sync lands."""
    from app.database.cache import close_request_cache_conn, init_cache_db

    with app.app_context():
        init_cache_db()

    # Closes the per-request cache connection BaseCacheRepository reuses
    # via cache.py's cache_conn_scope() — see that function's docstring
    # for why a page load reuses one connection instead of opening 15-20.
    app.teardown_appcontext(close_request_cache_conn)


# Every scheduler that writes to the shared SQLite cache
# (instance/localstorage.db) via offset_seconds-based clock alignment —
# used by _validate_scheduler_offsets() below. Add a new entry here
# whenever a new scheduler module gets its own OFFSET_SECONDS constant,
# or the check below can't see it. The Telegram/webhook alert loops use
# the same OFFSET_SECONDS pattern for a different, unrelated reason
# (spacing out Telegram API calls, not SQLite writes) and are
# deliberately NOT included — a different collision domain.
_SCHEDULER_OFFSET_MODULES = (
    "app.services.alarm.alarm_scheduler",
    "app.services.alarm.congestion_history_scheduler",
    "app.services.site.site_scheduler",
    "app.services.site.site_lookup_scheduler",
    "app.services.incident.incident_scheduler",
    "app.services.ape_alarm.ape_alarm_scheduler",
    "app.services.vip.vip_alarm_scheduler",
    "app.services.vip.vip_site_scheduler",
    "app.services.pop.pop_scheduler",
    "app.services.site.mssql_site_onair_scheduler",
    "app.services.partner_contact.partner_contact_scheduler",
)


def _validate_scheduler_offsets():
    """Fails app startup loudly if two schedulers in
    _SCHEDULER_OFFSET_MODULES share the same OFFSET_SECONDS — the exact
    bug behind a real production incident (2026-10-06):
    partner_contact_scheduler.py and mssql_site_onair_scheduler.py both
    used offset_seconds=110 with the same 300s interval, so they launched
    at the identical instant every cycle, piled up writing to the shared
    SQLite cache at once, and several OTHER schedulers' writes queued up
    behind that collision and failed outright ("database is locked")
    after 58-123s instead of the normal <1s. That went undetected for
    weeks because nothing checked it.

    Called unconditionally from create_app() — including under pytest,
    not just a real app boot — so a repeat of this exact mistake fails
    the test suite immediately instead of silently reaching production
    again."""
    seen = {}
    for module_path in _SCHEDULER_OFFSET_MODULES:
        offset = import_module(module_path).OFFSET_SECONDS
        if offset in seen:
            raise RuntimeError(
                f"Scheduler offset collision: {module_path!r} and {seen[offset]!r} "
                f"both use OFFSET_SECONDS={offset}. Two schedulers sharing an "
                "offset launch at the exact same instant every cycle and pile up "
                "writing to the same SQLite cache file at once — this caused a "
                "real production incident on 2026-10-06 (partner_contact_scheduler.py "
                "vs mssql_site_onair_scheduler.py, both offset=110). Pick a value "
                "not already used by any other entry in _SCHEDULER_OFFSET_MODULES."
            )
        seen[offset] = module_path


# (scheduler module, config key holding its interval in seconds) — every
# entry here used to be its own near-identical _init_*_cache() function
# (~100 lines total) repeating the same testing/debug-reloader skip-guard
# by hand. Collapsed into _start_background_jobs() below; add a domain's
# background sync here instead of writing a new function for it.
_BACKGROUND_JOBS = (
    ("app.services.alarm.alarm_scheduler", "MSSQL_SYNC_INTERVAL_SECONDS"),
    ("app.services.alarm.congestion_history_scheduler", "CONGESTION_SYNC_INTERVAL_SECONDS"),
    ("app.services.site.site_scheduler", "SITE_SYNC_INTERVAL_SECONDS"),
    ("app.services.site.site_lookup_scheduler", "SITE_LOOKUP_SYNC_INTERVAL_SECONDS"),
    ("app.services.incident.incident_scheduler", "INCIDENT_SYNC_INTERVAL_SECONDS"),
    ("app.services.ape_alarm.ape_alarm_scheduler", "APE_ALARM_SYNC_INTERVAL_SECONDS"),
    ("app.services.vip.vip_alarm_scheduler", "VIP_ALARM_SYNC_INTERVAL_SECONDS"),
    ("app.services.vip.vip_site_scheduler", "VIP_SITE_SYNC_INTERVAL_SECONDS"),
    ("app.services.pop.pop_scheduler", "POP_SYNC_INTERVAL_SECONDS"),
    ("app.services.site.mssql_site_onair_scheduler", "MSSQL_SITE_ONAIR_SYNC_INTERVAL_SECONDS"),
    ("app.services.partner_contact.partner_contact_scheduler", "PARTNER_CONTACT_SYNC_INTERVAL_SECONDS"),
    ("app.services.incident.site_down_24h_alert_scheduler", "SITE_DOWN_24H_ALERT_INTERVAL_SECONDS"),
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
