"""Background thread that keeps the local alarm cache
(instance/localstorage.db) in sync with MSSQL for the ISP POP / EZE / TCT /
IT NODE cards, plus the VIP/VVIP Site cache (SITE_INFO) — the same
near-real-time mirror role Autonoc-Dashboard's scheduler.py plays for its
own alarm caches, minus the extra dependency: a single interval loop is
enough for these jobs.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""
from app.services.alarm_sync_service import AlarmSyncService
from app.services.scheduler_utils import start_singleton_loop
from app.services.vip_site_sync_service import VipSiteSyncService


def start(app, interval_seconds):
    service = AlarmSyncService()
    vip_site_service = VipSiteSyncService()

    def _work():
        service.sync_all()
        vip_site_service.sync()

    start_singleton_loop(
        app, _work, interval_seconds,
        thread_name="alarm-cache-sync",
        log_message=f"Alarm cache sync started (every {interval_seconds}s)",
    )
