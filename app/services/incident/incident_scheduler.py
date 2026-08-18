"""Background thread that keeps the local Incident cache
(instance/localstorage.db) in sync with PostgreSQL (object_322). Mirrors
app/services/site/site_scheduler.py — same reasoning applies here.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.services.incident.incident_sync_service import IncidentSyncService
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop


def start(app, interval_seconds):
    service = IncidentSyncService()
    tz_name = app.config["TIMEZONE"]

    def _work():
        total = 0
        total += service.sync_by_status() or 0
        total += service.sync_inc_wo_by_status() or 0
        total += service.sync_inc_wo_site_down() or 0
        total += service.sync_inc_wo_category_power() or 0
        total += service.sync_inc_wo_resolved() or 0
        total += service.sync_incident_site_down() or 0
        total += service.sync_vip_incident_status() or 0
        return total

    # first_run_delay applies the same offset to the first run too, not
    # just later cycles — see site_scheduler.py's start() for why.
    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="incident-cache-sync",
        log_message=str(interval_seconds),
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=30
        ),
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=30
        ),
    )
