"""Background thread that keeps the local ape_alarm cache in sync with
PostgreSQL (object_138). Mirrors incident_scheduler.py — same reasoning
applies here.

Runs on its own, longer interval (APE_ALARM_SYNC_INTERVAL_SECONDS)
rather than sharing the 300s default — object_138 is a 10M-row foreign
table with no supporting index, so every sync does a full unindexed scan
on a live production replica. A longer interval keeps that cost
infrequent.

If a cycle fails outright (retry budget exhausted), next_delay_fn
retries again in 45s instead of waiting for the next clock-aligned tick,
recovering a stale cache sooner; on success the delay stays pinned to a
clean clock boundary, same as every other cache-sync scheduler.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.services.ape_alarm.ape_alarm_sync_service import ApeAlarmSyncService
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop

_RETRY_DELAY_SECONDS = 45

# Module-level so app/__init__.py's _validate_scheduler_offsets() can
# check it at startup — see that function's own docstring. Coincidentally
# the same number as _RETRY_DELAY_SECONDS above — unrelated to it, that's
# a failure-retry delay, this is the clock-alignment offset.
OFFSET_SECONDS = 45


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
            return seconds_until_next_aligned_time(interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS)
        return _RETRY_DELAY_SECONDS

    # first_run_delay applies the same offset to the first run too, not
    # just later cycles — see site_scheduler.py's start() for why.
    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="ape-alarm-cache-sync",
        log_message=f"APE alarm cache sync scheduler started (every {interval_seconds}s)",
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
        next_delay_fn=_next_delay,
    )
