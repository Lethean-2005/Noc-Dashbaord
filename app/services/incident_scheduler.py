"""Background thread that keeps the local Incident cache
(instance/localstorage.db) in sync with PostgreSQL (object_322). Mirrors
app/services/site_scheduler.py — same reasoning applies here.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""
from app.services.incident_sync_service import IncidentSyncService
from app.services.scheduler_utils import start_singleton_loop


def start(app, interval_seconds):
    service = IncidentSyncService()

    def _work():
        service.sync_by_status()
        service.sync_inc_wo_by_status()
        service.sync_inc_wo_site_down()
        service.sync_inc_wo_resolved()
        service.sync_vip_customer_complaint()
        service.sync_incident_site_down()

    start_singleton_loop(
        app, _work, interval_seconds,
        thread_name="incident-cache-sync",
        log_message=f"Incident cache sync started (every {interval_seconds}s)",
    )
