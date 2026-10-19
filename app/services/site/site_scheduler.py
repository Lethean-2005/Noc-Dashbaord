"""Background thread that keeps the local Site cache
(instance/localstorage.db) in sync with PostgreSQL (object_160). Same role
as app/services/alarm/alarm_scheduler.py plays for the MSSQL alarm caches, kept as
its own loop since the two sources are unrelated.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.services.site.site_sync_service import SiteSyncService

# Module-level so app/__init__.py's _validate_scheduler_offsets() can
# check it at startup — see that function's own docstring.
OFFSET_SECONDS = 0


def start(app, interval_seconds):
    service = SiteSyncService()
    tz_name = app.config["TIMEZONE"]

    def _work():
        n1 = service.sync()
        n2 = service.sync_technology()
        n3 = service.sync_ne_nms()
        n4 = service.sync_ran_vendor()
        n5 = service.sync_counterparty()
        return (n1 or 0) + (n2 or 0) + (n3 or 0) + (n4 or 0) + (n5 or 0)

    # first_run_delay applies this same offset to the very first run too —
    # without it, a fresh app restart fires every job's first cycle
    # immediately with no stagger at all (next_delay_fn only staggers
    # cycles after the first), which is actually a bigger pile-up than the
    # recurring one this offset was built to fix.
    first_run_delay = seconds_until_next_aligned_time(
        interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
    )
    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="site-cache-sync",
        log_message=f"Site cache sync scheduler started (every {interval_seconds}s)",
        first_run_delay=first_run_delay,
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
    )
