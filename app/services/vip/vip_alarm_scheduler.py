"""Background thread that keeps the local vip_alarm cache
(instance/localstorage.db) in sync — rebuilt from the already-synced
ape_alarm cache (filtered to VIP/VVIP sites), not from its own PostgreSQL
query. Runs on its own interval (VIP_ALARM_SYNC_INTERVAL_SECONDS) even
though it's a purely local derivation, so it stays fresh independent of
ape_alarm's own sync cadence.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.services.vip.vip_alarm_sync_service import VipAlarmSyncService


def start(app, interval_seconds):
    service = VipAlarmSyncService()
    tz_name = app.config["TIMEZONE"]

    def _work():
        return service.sync()

    start_singleton_loop(
        app, _work, interval_seconds,
        thread_name="vip-alarm-cache-sync",
        log_message=str(interval_seconds),
        next_delay_fn=lambda: seconds_until_next_aligned_time(interval_seconds, tz_name),
    )
