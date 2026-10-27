"""Background thread that keeps the local Incident cache
(instance/localstorage.db) in sync with PostgreSQL (object_322). Mirrors
app/services/site/site_scheduler.py — same reasoning applies here.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.services.incident.incident_sync_service import IncidentSyncService
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.services.sla_policy.sla_policy_sync_service import SlaPolicySyncService

# Module-level so app/__init__.py's _validate_scheduler_offsets() can
# check it at startup — see that function's own docstring.
OFFSET_SECONDS = 30


def start(app, interval_seconds):
    service = IncidentSyncService()
    sla_policy_service = SlaPolicySyncService()
    tz_name = app.config["TIMEZONE"]

    def _work():
        total = 0
        total += service.sync_by_status() or 0
        total += service.sync_incident_closed_trend() or 0
        total += service.sync_incident_created_trend() or 0
        total += service.sync_inc_wo_by_status() or 0
        total += service.sync_inc_wo_site_down() or 0
        total += service.sync_inc_wo_category_power() or 0
        total += service.sync_inc_wo_resolved() or 0
        total += service.sync_incident_site_down() or 0
        total += service.sync_site_down_worklog() or 0
        total += service.sync_site_down_root_cause() or 0
        total += service.sync_site_down_duration_weekly() or 0
        total += service.sync_duration_weekly() or 0
        total += service.sync_response_time_weekly() or 0
        total += service.sync_response_time_details() or 0
        total += service.sync_resolution_time_weekly() or 0
        total += service.sync_resolution_time_details() or 0
        total += service.sync_sla_compliance_weekly() or 0
        total += service.sync_sla_compliance_details() or 0
        total += service.sync_vip_incident_status() or 0
        total += sla_policy_service.sync() or 0
        return total

    # first_run_delay applies the same offset to the first run too, not
    # just later cycles — see site_scheduler.py's start() for why.
    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="incident-cache-sync",
        log_message=f"Incident cache sync scheduler started (every {interval_seconds}s)",
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
    )
