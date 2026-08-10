"""Background thread that keeps the local ape_alarm cache
(instance/localstorage.db) in sync with PostgreSQL (object_138). Mirrors
app/services/incident/incident_scheduler.py — same reasoning applies here.

Runs on its own, longer interval (APE_ALARM_SYNC_INTERVAL_SECONDS) rather
than sharing INCIDENT_SYNC_INTERVAL_SECONDS's 300s default — object_138 is
a 10M-row foreign table with no supporting index, so every sync does a
full unindexed scan on a live production replica. A longer interval keeps
that cost infrequent instead of hitting it as often as the much cheaper
Incident/Site queries.

If a cycle fails outright (replica conflict exhausts ape_alarm_sync_service's
retry budget), next_delay_fn below retries again in 45s instead of waiting
for the next clock-aligned tick — recovers a stale cache sooner instead of
possibly waiting up to a full interval_seconds for the next boundary. When
sync() succeeds, the delay instead stays pinned to a clean clock boundary
(00:00, 00:05, 00:10, ... for a 300s interval — see
scheduler_utils.seconds_until_next_aligned_time()), same as every other
cache-sync scheduler, so a healthy replica sees no extra load and doesn't
drift off the shared boundary cycle after cycle.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.services.ape_alarm.ape_alarm_sync_service import ApeAlarmSyncService
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop

_RETRY_DELAY_SECONDS = 45


def start(app, interval_seconds):
    service = ApeAlarmSyncService()
    tz_name = app.config["TIMEZONE"]
    last_ok = {"value": True}

    def _work():
        result = service.sync()
        last_ok["value"] = result is not None
        return result

    def _next_delay():
        if last_ok["value"]:
            return seconds_until_next_aligned_time(interval_seconds, tz_name, offset_seconds=45)
        return _RETRY_DELAY_SECONDS

    # first_run_delay applies the same offset to the first run too, not
    # just later cycles — see site_scheduler.py's start() for why.
    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="ape-alarm-cache-sync",
        log_message=str(interval_seconds),
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=45
        ),
        next_delay_fn=_next_delay,
    )
