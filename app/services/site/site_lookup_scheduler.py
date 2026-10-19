"""Background thread that keeps the local site_lookup cache
(instance/localstorage.db) in sync with PostgreSQL (site_lookup_mv). Same
role as app/services/site/site_scheduler.py plays for object_160, kept as
its own loop since it's a different source view on its own schedule.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.services.site.site_lookup_sync_service import SiteLookupSyncService

# Module-level so app/__init__.py's _validate_scheduler_offsets() can
# check it at startup — see that function's own docstring.
OFFSET_SECONDS = 15


def start(app, interval_seconds):
    service = SiteLookupSyncService()
    tz_name = app.config["TIMEZONE"]

    # first_run_delay applies the same offset to the first run too, not
    # just later cycles — see site_scheduler.py's start() for why.
    start_singleton_loop(
        app,
        service.sync,
        interval_seconds,
        thread_name="site-lookup-cache-sync",
        log_message=f"Site lookup cache sync scheduler started (every {interval_seconds}s)",
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
    )
