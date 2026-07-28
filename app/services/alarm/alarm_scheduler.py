"""Background thread that keeps the local alarm cache
(instance/localstorage.db) in sync with MSSQL for the ISP POP / EZE / TCT /
IT NODE cards, plus the VIP/VVIP Site cache (SITE_INFO) — the same
near-real-time mirror role Autonoc-Dashboard's scheduler.py plays for its
own alarm caches, minus the extra dependency: a single interval loop is
enough for these jobs.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""
from app.services.alarm.alarm_sync_service import AlarmSyncService
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.services.vip.vip_site_sync_service import VipSiteSyncService


def start(app, interval_seconds):
    service = AlarmSyncService()
    vip_site_service = VipSiteSyncService()
    tz_name = app.config["TIMEZONE"]

    def _work():
        n1 = service.sync_all()
        n2 = vip_site_service.sync()
        return (n1 or 0) + (n2 or 0)

    start_singleton_loop(
        app, _work, interval_seconds,
        thread_name="alarm-cache-sync",
        log_message=str(interval_seconds),
        next_delay_fn=lambda: seconds_until_next_aligned_time(interval_seconds, tz_name),
    )
