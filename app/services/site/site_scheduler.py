"""Background thread that keeps the local Site cache
(instance/localstorage.db) in sync with PostgreSQL (object_160). Same role
as app/services/alarm/alarm_scheduler.py plays for the MSSQL alarm caches, kept as
its own loop since the two sources are unrelated.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.services.site.site_sync_service import SiteSyncService


def start(app, interval_seconds):
    service = SiteSyncService()
    tz_name = app.config["TIMEZONE"]

    def _work():
        n1 = service.sync()
        n2 = service.sync_technology()
        return (n1 or 0) + (n2 or 0)

    start_singleton_loop(
        app, _work, interval_seconds,
        thread_name="site-cache-sync",
        log_message=str(interval_seconds),
        next_delay_fn=lambda: seconds_until_next_aligned_time(interval_seconds, tz_name),
    )
