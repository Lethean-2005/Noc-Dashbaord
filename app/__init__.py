"""Application factory."""

import os

from dotenv import load_dotenv

# Must run before `app.config` is imported — Config reads os.environ at
# class-definition time, so .env values loaded any later are silently ignored.
load_dotenv()

from flask import Flask, request  # noqa: E402 — must come after load_dotenv() above

from app.config import config_map  # noqa: E402
from app.extensions import compress, csrf, db, login_manager  # noqa: E402


def create_app(env=None, instance_path=None, *, process_role="web"):
    """`instance_path`, if given, overrides Flask's default instance folder
    (where instance/localstorage.db lives — see app/database/cache.py). Both
    tests and the worker use this; each test gets its own SQLite cache
    instead of reading whatever real data happens to be synced into the
    dev machine's instance/localstorage.db."""
    if process_role not in {"web", "worker"}:
        raise ValueError("process_role must be web or worker")
    env = env or os.environ.get("APP_ENV", "default")
    
    app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    app.config.from_object(config_map[env])
    app.config["PROCESS_ROLE"] = process_role

    os.makedirs(app.instance_path, exist_ok=True)

    _register_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_template_filters(app)
    _register_context_processors(app)
    _register_static_cache_headers(app)
    _register_request_timing_log(app)
    runtime = None
    if process_role == "worker" and not app.testing:
        from app.worker_runtime import WorkerRuntime

        runtime = WorkerRuntime(app)
        runtime.acquire()
    try:
        _init_cache_db(app)
        if runtime is not None:
            runtime.start()
    except BaseException:
        if runtime is not None:
            runtime.abort_startup()
        raise

    return app


def _register_extensions(app):
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    compress.init_app(app)


def _register_blueprints(app):
    from app.routes.congestion_blacklist import congestion_blacklist_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.help import help_bp
    from app.routes.incident_report import incident_report_bp
    from app.routes.map_view import map_view_bp
    from app.routes.mentor import mentor_bp
    from app.routes.partner_contact import partner_contact_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(congestion_blacklist_bp)
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(mentor_bp, url_prefix="/mentor")
    app.register_blueprint(map_view_bp, url_prefix="/map")
    app.register_blueprint(partner_contact_bp)
    app.register_blueprint(incident_report_bp, url_prefix="/incident-report")
    app.register_blueprint(help_bp)

    from app.routes.api import register_api

    register_api(app)


def _register_template_filters(app):
    from app.utils.formatter import badge_color, status_badge_class, site_code_display

    app.jinja_env.filters["site_code_display"] = site_code_display
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
    def _add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Existing inline scripts, styles, maps and exports remain supported.
        response.headers.setdefault("Content-Security-Policy", "base-uri 'self'; object-src 'none'; frame-ancestors 'self'")
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

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


def _register_request_timing_log(app):
    """One line per HTTP request (method, path, status, duration,
    remote address) into logs/requests.log — added so a reported "slow
    dashboard reload" can be correlated against a specific endpoint or a
    burst of concurrent requests, instead of guessing from Werkzeug's
    own access-log line (which has no duration)."""
    import time

    from app.utils.logger import get_logger

    logger = get_logger("app.request_timing")

    @app.before_request
    def _start_request_timer():
        request._started_at = time.perf_counter()

    @app.after_request
    def _log_request_timing(response):
        started_at = getattr(request, "_started_at", None)
        duration_ms = (time.perf_counter() - started_at) * 1000 if started_at else -1
        logger.info(
            f"{request.method} {request.path} -> {response.status_code} "
            f"({duration_ms:.0f}ms) from {request.remote_addr}"
        )
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


def _register_error_handlers(app):
    from app.http_errors import register_error_handlers

    register_error_handlers(app)
