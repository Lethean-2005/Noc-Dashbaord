"""Background thread that keeps the local mssql_site_onair cache
(instance/localstorage.db) in sync — pulled straight from MSSQL's
TBL_SITE/TBL_NE (see mssql_site_onair_sync_service.py), same as
pop_scheduler.py does for its own source table. Runs on its own interval
(MSSQL_SITE_ONAIR_SYNC_INTERVAL_SECONDS).

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.services.site.mssql_site_onair_sync_service import MssqlSiteOnairSyncService

# Module-level so app/__init__.py's _validate_scheduler_offsets() can
# check it at startup — see that function's own docstring. This is the
# scheduler partner_contact_scheduler.py used to collide with
# (both were 110) in the 2026-10-06 production incident — see that
# file's own OFFSET_SECONDS comment for the full story.
OFFSET_SECONDS = 110


def start(app, interval_seconds):
    service = MssqlSiteOnairSyncService()
    tz_name = app.config["TIMEZONE"]

    def _work():
        return service.sync()

    # first_run_delay applies the same offset to the first run too, not
    # just later cycles — see site_scheduler.py's start() for why.
    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="mssql-site-onair-cache-sync",
        log_message=f"MSSQL site on-air cache sync scheduler started (every {interval_seconds}s)",
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
    )
