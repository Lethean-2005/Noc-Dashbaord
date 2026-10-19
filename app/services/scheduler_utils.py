"""Shared "run this on a background loop, once per process" helper.

Every scheduler (alarm_scheduler.py, site_scheduler.py, incident_scheduler.py,
telegram_alert.py) used to repeat the same ~15 lines: a start-once guard (so
Flask's debug reloader can't accidentally start the loop twice in the same
process), a thread wrapping the work in `app.app_context()` (needed because
the loop runs on its own thread, outside any request, so Flask has no
"current app" otherwise), and a sleep between iterations. This factors that
shared shape into one place — each scheduler file now only says *what* to run
and *how often*, not how to run it forever.
"""

import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.utils.logger import get_logger

logger = get_logger(__name__)

_guards = {}
_guards_lock = threading.Lock()

# Every job's most recently completed cycle duration (thread_name ->
# seconds), updated after every COMPLETED below. all_tasks_scheduler.py's
# grand total reads this via total_duration() to report how much combined
# time every job's *last* cycle actually took, instead of its own
# near-instant COUNT(*) aggregation time.
_last_durations = {}
_last_durations_lock = threading.Lock()


def total_duration():
    """Sum of every job's most recently recorded cycle duration — see
    _last_durations above."""
    with _last_durations_lock:
        return sum(_last_durations.values())


def seconds_until_next_aligned_time(interval_seconds, tz_name, offset_seconds=0):
    """Seconds from now until the next clock time that's a multiple of
    `interval_seconds` since local midnight in `tz_name` (plus
    `offset_seconds`) — e.g. a 300s interval lands on 00:00, 00:05, ...
    Pure modular arithmetic, no special-casing for the day boundary.

    `offset_seconds` staggers a job's landing point within the shared
    cycle — every 300s-interval job used to target the exact same
    instant, so several jobs' local database writes could collide at
    once (plus real staff traffic from dashboard.py's own auto-reload).
    Distinct offsets per job spread that work across the cycle instead.
    """
    now = datetime.now(ZoneInfo(tz_name))
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seconds_since_midnight = (now - midnight).total_seconds()
    return interval_seconds - ((seconds_since_midnight - offset_seconds) % interval_seconds)


def start_singleton_loop(
    app, work, interval_seconds, thread_name, log_message, first_run_delay=None, next_delay_fn=None
):
    """Run `work()` forever on a daemon thread named `thread_name`, every
    `interval_seconds`, guarded so a second call with the same
    `thread_name` in this process is a no-op.

    `work` runs inside `app.app_context()` wrapped in a catch-all
    try/except backstop so one uncaught exception skips a cycle instead of
    killing the loop. Logs START/COMPLETED/FAILED, plus a "Total: synced
    N row(s)" line if `work()` returns an int; every job but
    all-tasks-summary records its duration into _last_durations so
    all-tasks-summary can report total_duration() instead of its own
    near-instant counting time.

    `first_run_delay` skips the immediate first run (Telegram alert loop,
    so a dev-server restart can't resend an alert). `next_delay_fn`, if
    given, computes each sleep instead of a plain `interval_seconds` — all
    schedulers pass seconds_until_next_aligned_time() here to stay pinned
    to clean clock boundaries instead of drifting.
    """
    with _guards_lock:
        guard = _guards.setdefault(thread_name, {"started": False, "lock": threading.Lock()})

    with guard["lock"]:
        if guard["started"]:
            return
        guard["started"] = True

    def _loop():
        # Logged from inside this thread (not the caller) so the job-name
        # column in logs/app.log shows `thread_name`, not "MainThread".
        logger.info(log_message)
        if first_run_delay is not None:
            time.sleep(first_run_delay)
        while True:
            with app.app_context():
                start = time.monotonic()
                logger.info("START")
                try:
                    result = work()
                except Exception as e:
                    logger.error(f"FAILED ({time.monotonic() - start:.2f}s): {e}")
                else:
                    elapsed = time.monotonic() - start
                    logger.info(f"COMPLETED ({elapsed:.2f}s)")
                    if thread_name != "all-tasks-summary":
                        with _last_durations_lock:
                            _last_durations[thread_name] = elapsed
                    if isinstance(result, int):
                        if thread_name == "all-tasks-summary":
                            logger.info(
                                f"Total: Synced {result:,} row(s) in {total_duration():.2f}s"
                            )
                        else:
                            logger.info(f"Total: synced {result} row(s) in {elapsed:.2f}s")
            time.sleep(next_delay_fn() if next_delay_fn else interval_seconds)

    threading.Thread(target=_loop, daemon=True, name=thread_name).start()
