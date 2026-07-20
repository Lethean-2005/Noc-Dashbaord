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

from app.utils.logger import get_logger

logger = get_logger(__name__)

_guards = {}
_guards_lock = threading.Lock()


def start_singleton_loop(app, work, interval_seconds, thread_name, log_message, sleep_first=False):
    """Run `work()` forever on a daemon thread named `thread_name`, every
    `interval_seconds`, guarded so a second call with the same `thread_name`
    in this process is a no-op.

    `work` is called inside `app.app_context()` and wrapped in a catch-all
    try/except — each sync service already catches its own per-job errors
    (so a bad MSSQL/Postgres response doesn't reach here), but this is a last
    -resort backstop so a future uncaught exception logs and skips a cycle
    instead of silently killing the loop forever.

    `sleep_first=True` waits one interval before the first run instead of
    running immediately (used by the Telegram alert loop, so restarting the
    dev server can't immediately resend an alert).
    """
    with _guards_lock:
        guard = _guards.setdefault(thread_name, {"started": False, "lock": threading.Lock()})

    with guard["lock"]:
        if guard["started"]:
            return
        guard["started"] = True

    def _loop():
        if sleep_first:
            time.sleep(interval_seconds)
        while True:
            with app.app_context():
                try:
                    work()
                except Exception as e:
                    logger.error(f"{thread_name} iteration failed: {e}")
            time.sleep(interval_seconds)

    threading.Thread(target=_loop, daemon=True, name=thread_name).start()
    logger.info(log_message)
