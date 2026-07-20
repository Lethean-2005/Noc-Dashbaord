"""Background thread that keeps the local Site cache
(instance/localstorage.db) in sync with PostgreSQL (object_160). Same role
as app/services/alarm_scheduler.py plays for the MSSQL alarm caches, kept as
its own loop since the two sources are unrelated.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""
from app.services.scheduler_utils import start_singleton_loop
from app.services.site_sync_service import SiteSyncService


def start(app, interval_seconds):
    service = SiteSyncService()

    start_singleton_loop(
        app, service.sync, interval_seconds,
        thread_name="site-cache-sync",
        log_message=f"Site cache sync started (every {interval_seconds}s)",
    )
