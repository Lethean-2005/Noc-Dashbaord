"""Background thread that logs one combined "Total" line across every
background sync job, every ALL_TASKS_SUMMARY_INTERVAL_SECONDS (5 minutes
by default) — a single purple summary, displayed as job name "Total all
sync" (see app/utils/logger.py's TOTAL/_ALL_TASKS_THREAD_NAME handling),
showing the total row count currently cached across the whole dashboard
without needing to read every other job's individual COMPLETED lines to
get the same picture.

Reads sync_meta (app/database/cache.py) for the list of every table any
sync service has ever written to, rather than hardcoding that list here —
it's already the single source of truth for "which tables get synced",
kept up to date by every repository's replace_all().

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.database.cache import get_cache_conn
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _total_rows():
    """(total row count, number of tables) across every table sync_meta
    knows about. Table names come only from our own sync_meta rows (never
    user input — see BaseCacheRepository._validate_table()'s same
    reasoning), so interpolating them into COUNT(*) is safe.

    sync_meta rows are never deleted when a table is renamed/retired (only
    init_cache_db()'s _RETIRED_TABLES drop the table itself, not its
    sync_meta row) — so this cross-checks against sqlite_master and skips
    any table_name that no longer actually exists, instead of erroring."""
    conn = get_cache_conn()
    try:
        existing = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        tables = [
            r["table_name"]
            for r in conn.execute("SELECT table_name FROM sync_meta").fetchall()
            if r["table_name"] in existing
        ]
        total = sum(
            conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] for table in tables
        )
        return total, len(tables)
    finally:
        conn.close()


def start(app, interval_seconds):
    tz_name = app.config["TIMEZONE"]

    def _work():
        total, _count = _total_rows()
        return total

    # first_run_delay applies the same offset to the first run too, not
    # just later cycles — see site_scheduler.py's start() for why.
    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="all-tasks-summary",
        log_message=str(interval_seconds),
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=90
        ),
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=90
        ),
    )
