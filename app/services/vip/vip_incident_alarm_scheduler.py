"""Background thread that keeps the local vip_incident_alarm cache
(instance/localstorage.db) in sync — a purely local re-join of vip_alarm/
incident_by_status/site_cache (see vip_incident_alarm_sync_service.py), so
unlike every other scheduler here this never touches Postgres and carries
no "conflict with recovery" risk — safe to run on a short interval.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.services.vip.vip_incident_alarm_sync_service import VipIncidentAlarmSyncService


def start(app, interval_seconds):
    service = VipIncidentAlarmSyncService()
    tz_name = app.config["TIMEZONE"]

    def _work():
        return service.sync()

    start_singleton_loop(
        app, _work, interval_seconds,
        thread_name="vip-incident-alarm-cache-sync",
        log_message=str(interval_seconds),
        next_delay_fn=lambda: seconds_until_next_aligned_time(interval_seconds, tz_name),
    )
