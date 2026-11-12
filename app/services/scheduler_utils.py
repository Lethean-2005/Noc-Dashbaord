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
    if app.config.get("PROCESS_ROLE") == "web":
        raise RuntimeError("Web processes cannot start scheduled sync or alert jobs")
    if interval_seconds <= 0:
        raise ValueError("Scheduler interval must be positive")
    with _guards_lock:
        guard = _guards.setdefault(thread_name, {"started": False, "lock": threading.Lock()})

    with guard["lock"]:
        if guard["started"]:
            return
        guard["started"] = True

    stop_event = app.extensions.setdefault("scheduler_stop_event", threading.Event())
    runtime = app.extensions.get("sync_worker")
    if runtime is not None:
        runtime.register_job(thread_name, interval_seconds)

    def _loop():
        logger.info(log_message)
        try:
            if first_run_delay is not None and stop_event.wait(first_run_delay):
                return
            while not stop_event.is_set():
                with app.app_context():
                    start = time.monotonic()
                    logger.info("START")
                    if runtime is not None:
                        runtime.record_job(thread_name, state="running", last_attempt_at=_utc_now())
                    try:
                        result = work()
                    except Exception as error:
                        logger.error(f"FAILED ({time.monotonic() - start:.2f}s): {error}")
                        if runtime is not None:
                            runtime.record_job(thread_name, state="failed", last_error=type(error).__name__,
                                               last_finished_at=_utc_now(), duration_seconds=round(time.monotonic() - start, 3))
                    else:
                        elapsed = time.monotonic() - start
                        logger.info(f"COMPLETED ({elapsed:.2f}s)")
                        if runtime is not None:
                            runtime.record_job(thread_name, state="waiting", last_error=None,
                                               last_success_at=_utc_now(), last_finished_at=_utc_now(),
                                               duration_seconds=round(elapsed, 3))
                        if thread_name != "all-tasks-summary":
                            with _last_durations_lock:
                                _last_durations[thread_name] = elapsed
                        if isinstance(result, int):
                            if thread_name == "all-tasks-summary":
                                logger.info(f"Total: Synced {result:,} row(s) in {total_duration():.2f}s")
                            else:
                                logger.info(f"Total: synced {result} row(s) in {elapsed:.2f}s")
                if stop_event.wait(next_delay_fn() if next_delay_fn else interval_seconds):
                    return
        finally:
            with guard["lock"]:
                guard["started"] = False

    thread = threading.Thread(target=_loop, daemon=True, name=thread_name)
    app.extensions.setdefault("scheduler_threads", []).append(thread)
    thread.start()
    return thread


def _utc_now():
    from datetime import timezone

    return datetime.now(timezone.utc).isoformat()


def join_scheduler_threads(app, timeout):
    """Join only this application's loops, using one shared timeout budget."""
    deadline = time.monotonic() + timeout
    threads = app.extensions.get("scheduler_threads", [])
    for thread in threads:
        thread.join(max(0, deadline - time.monotonic()))
    return not any(thread.is_alive() for thread in threads)
