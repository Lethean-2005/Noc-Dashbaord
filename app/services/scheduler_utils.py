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
    `offset_seconds`, default 0) — e.g. with a 300s (5 min) interval:
    00:00, 00:05, 00:10, ... Pure modular arithmetic on seconds-since-
    midnight, so it needs no special-casing for the day boundary.
    Originally telegram_alert.py's own _seconds_until_next_aligned_time()
    — moved here once every other scheduler needed the same "stay pinned
    to the clock, don't drift" behavior, not just the Telegram alert loop.

    `offset_seconds` staggers a job's own landing point within the shared
    cycle (e.g. offset=30 lands on 00:00:30, 00:05:30, ... instead of
    00:00:00, 00:05:00) — every 300s-interval job used to target the exact
    same instant, which meant they (and every open browser tab's own
    auto-reload, see dashboard.py's index()) could all start real work at
    once, real staff traffic hitting the page right as several background
    jobs' local database writes collided. Distinct offsets per job spread
    that work across the cycle instead of concentrating it in one moment.
    """
    now = datetime.now(ZoneInfo(tz_name))
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seconds_since_midnight = (now - midnight).total_seconds()
    return interval_seconds - ((seconds_since_midnight - offset_seconds) % interval_seconds)


def start_singleton_loop(
    app, work, interval_seconds, thread_name, log_message, first_run_delay=None, next_delay_fn=None
):
    """Run `work()` forever on a daemon thread named `thread_name`, every
    `interval_seconds`, guarded so a second call with the same `thread_name`
    in this process is a no-op.

    `work` is called inside `app.app_context()` and wrapped in a catch-all
    try/except — each sync service already catches its own per-job errors
    (so a bad MSSQL/Postgres response doesn't reach here), but this is a last
    -resort backstop so a future uncaught exception logs and skips a cycle
    instead of silently killing the loop forever.

    Every cycle logs a bare "START" line right before `work()` runs and a
    "COMPLETED (X.XXs)" / "FAILED (X.XXs): ..." line right after it returns
    (each record already carries its own timestamp and job name via the
    logging formatter — see app/utils/logger.py — so there's no need to
    repeat `thread_name` inside the message itself).

    If `work()` also returns an int (every sync service's own sync method
    does — the row count synced this cycle, summed across every table it
    touches), an additional "Total: synced N row(s) in X.XXs" line is
    logged right after COMPLETED (styled purple in the console — see
    app/utils/logger.py's TOTAL handling). `work()` returning None
    (Telegram's alert loop) just skips that extra line. Every job except
    all-tasks-summary itself also records its own duration into
    _last_durations above, so all-tasks-summary's own Total line can report
    total_duration() — the combined time every other job's last cycle took
    — instead of its own (trivially fast) row-counting time.

    `first_run_delay`, if given, waits that many seconds before the first run
    instead of running immediately (used by the Telegram alert loop, both so
    restarting the dev server can't immediately resend an alert, and so the
    first run lands on a clean clock-aligned time — see
    seconds_until_next_aligned_time() above).

    `next_delay_fn`, if given, is called to compute the sleep after every
    run instead of the plain `interval_seconds`. Without this, that sleep is
    measured from the moment `work()` returns, so `work()`'s own runtime
    (network calls, disk I/O, etc.) shifts every following run later — and
    that shift compounds every cycle since nothing re-aligns to the clock.
    Every cache-sync scheduler (plus Telegram's alert) passes
    seconds_until_next_aligned_time() here to stay pinned to clean clock
    boundaries (00:00, 00:05, 00:10, ... for a 300s interval) instead of
    drifting later each cycle.
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
