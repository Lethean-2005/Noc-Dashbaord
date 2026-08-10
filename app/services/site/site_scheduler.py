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
        n3 = service.sync_ne_nms()
        return (n1 or 0) + (n2 or 0) + (n3 or 0)

    # first_run_delay applies this same offset to the very first run too —
    # without it, a fresh app restart fires every job's first cycle
    # immediately with no stagger at all (next_delay_fn only staggers
    # cycles after the first), which is actually a bigger pile-up than the
    # recurring one this offset was built to fix.
    first_run_delay = seconds_until_next_aligned_time(interval_seconds, tz_name, offset_seconds=0)
    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="site-cache-sync",
        log_message=str(interval_seconds),
        first_run_delay=first_run_delay,
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=0
        ),
    )
