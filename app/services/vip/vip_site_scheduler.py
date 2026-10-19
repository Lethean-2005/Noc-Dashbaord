"""Background thread that keeps the local vip_site_cache
(instance/localstorage.db) in sync — pulled straight from MSSQL's
SITE_INFO (see vip_site_sync_service.py), same as alarm_scheduler.py does
for its own source table. Runs on its own interval
(VIP_SITE_SYNC_INTERVAL_SECONDS).

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.services.vip.vip_site_sync_service import VipSiteSyncService

# Module-level so app/__init__.py's _validate_scheduler_offsets() can
# check it at startup — see that function's own docstring.
OFFSET_SECONDS = 75


def start(app, interval_seconds):
    service = VipSiteSyncService()
    tz_name = app.config["TIMEZONE"]

    def _work():
        return service.sync()

    # first_run_delay applies the same offset to the first run too, not
    # just later cycles — see site_scheduler.py's start() for why.
    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="vip-site-cache-sync",
        log_message=f"VIP site cache sync scheduler started (every {interval_seconds}s)",
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
    )
