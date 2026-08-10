"""Background thread that keeps the local alarm cache
(instance/localstorage.db) in sync with MSSQL for the ISP POP / EZE / TCT /
IT NODE cards — the same near-real-time mirror role Autonoc-Dashboard's
scheduler.py plays for its own alarm caches.

VIP/VVIP Site data (SITE_INFO) is NOT synced here — that used to be an
extra call inline in this same loop, meaning it was refreshed every
MSSQL_SYNC_INTERVAL_SECONDS (10s) here AND every VIP_SITE_SYNC_INTERVAL_SECONDS
(5 min) again by app/services/vip/vip_site_scheduler.py — the same data
written twice by two independent jobs for no reason, confirmed live via
logs/app.log. Removed here; vip_site_scheduler.py is the one job that owns
this now.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.services.alarm.alarm_sync_service import AlarmSyncService
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop


def start(app, interval_seconds):
    service = AlarmSyncService()
    tz_name = app.config["TIMEZONE"]

    def _work():
        return service.sync_all()

    # first_run_delay applies the same offset to the first run too, not
    # just later cycles — see site_scheduler.py's start() for why.
    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="alarm-cache-sync",
        log_message=str(interval_seconds),
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=3
        ),
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=3
        ),
    )
