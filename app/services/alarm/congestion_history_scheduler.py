"""Background thread that keeps congestion_history_cache
(instance/localstorage.db) in sync — Congestion (bandwidth+congestion
TCT alarms) over the last CONGESTION_HISTORY_WEEKS weeks, pulled from
MSSQL via AlarmSyncService.sync_congestion_history(). A standalone
scheduler (not folded into alarm_scheduler.py's own 10s active-only
loop) because this query reads a much wider, slower-changing historical
window and has no need for that fast a cadence — same reasoning
incident_scheduler.py's own 300s cadence uses for incident trend data,
vs. alarm_scheduler.py's 10s cadence for live alarm badges.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.services.alarm.alarm_sync_service import AlarmSyncService
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop

# Module-level so app/__init__.py's _validate_scheduler_offsets() can
# check it at startup — see that function's own docstring.
OFFSET_SECONDS = 135


def start(app, interval_seconds):
    service = AlarmSyncService()
    tz_name = app.config["TIMEZONE"]

    def _work():
        return service.sync_congestion_history()

    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="congestion-history-sync",
        log_message=f"Congestion history sync scheduler started (every {interval_seconds}s)",
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
    )
