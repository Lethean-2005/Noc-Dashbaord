"""Shared read/write logic for the local SQLite cache repositories.
Every *_cache_repository.py used to repeat the same ~60 lines
(replace_all/fetch_all/last_synced_at) — this pulls that logic into one
place so each repository just declares its own three attributes.
"""

import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app

from app.database.cache import cache_conn_scope, get_cache_conn
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ~11 independent background schedulers (app/__init__.py's
# _BACKGROUND_JOBS) all write to this same SQLite file, each on its own
# timer — get_cache_conn()'s own 10s busy_timeout usually absorbs a
# brief overlap on its own, but a burst where several threads all try to
# write at once (confirmed live: every job resuming together right after
# the host was paused/suspended for several minutes) can still exceed
# that single wait and fail outright with "database is locked". A few
# short retries gives a transient burst like that more chances to clear
# before a table's whole sync cycle is given up on for this run.
_WRITE_MAX_ATTEMPTS = 4
_WRITE_RETRY_DELAY_SECONDS = 0.5


class BaseCacheRepository:
    """Subclasses set:
    valid_tables — tuple of table names this repository is allowed to
                    touch (from app/database/cache.py)
    columns      — tuple of column names, matching the table's schema,
                    used to build the INSERT in replace_all()
    order_by     — the ORDER BY clause fetch_all() uses (no "ORDER BY"
                    prefix), e.g. "occurred_at DESC" or "site_name"
    """

    valid_tables = ()
    columns = ()
    order_by = "rowid"

    def _validate_table(self, table):
        """`table` is never user input, but every method here builds SQL
        by interpolating it — this whitelist makes that provably safe."""
        if table not in self.valid_tables:
            raise ValueError(f"Unknown cache table for {type(self).__name__}: {table!r}")

    def _retry_write(self, table, work):
        """Runs `work(conn)` (any number of statements, no commit) inside
        the same attempt/backoff/rollback loop replace_all() used to run
        inline — pulled out so update_one()/delete_one() below (added for
        the Acknowledge/Clear single-row cache patch, replacing a full
        sync_scope() resync) share it instead of repeating the loop a
        third time. See _WRITE_MAX_ATTEMPTS's own comment for why this
        retries at all."""
        self._validate_table(table)
        for attempt in range(1, _WRITE_MAX_ATTEMPTS + 1):
            conn = get_cache_conn()
            try:
                work(conn)
                conn.commit()
                return
            except sqlite3.OperationalError as e:
                conn.rollback()
                if attempt < _WRITE_MAX_ATTEMPTS and "locked" in str(e).lower():
                    logger.warning(
                        f"{table} write attempt {attempt}/{_WRITE_MAX_ATTEMPTS} hit "
                        f"'{e}', retrying in {_WRITE_RETRY_DELAY_SECONDS * attempt}s"
                    )
                    time.sleep(_WRITE_RETRY_DELAY_SECONDS * attempt)
                    continue
                raise
            finally:
                conn.close()

    def replace_all(self, table, rows):
        """Overwrite `table` with `rows` (list of dicts using `columns` keys).
        Retries a few times with short backoff (see _WRITE_MAX_ATTEMPTS
        above) if every attempt still hits "database is locked" — any
        other error raises immediately, same as before."""
        def _work(conn):
            conn.execute(f"DELETE FROM {table}")
            if rows:
                placeholders = ", ".join(f":{c}" for c in self.columns)
                conn.executemany(
                    f"INSERT INTO {table} ({', '.join(self.columns)}) VALUES ({placeholders})",
                    rows,
                )
            conn.execute(
                "INSERT INTO sync_meta (table_name, last_synced_at) VALUES (?, ?) "
                "ON CONFLICT(table_name) DO UPDATE SET last_synced_at = excluded.last_synced_at",
                (table, datetime.now(ZoneInfo(current_app.config["TIMEZONE"])).isoformat(timespec="seconds")),
            )

        self._retry_write(table, _work)

    def update_one(self, table, row_id, fields):
        """Updates just one row's given columns by id, instead of
        replace_all()'s full-table rewrite — lets a write-back to MSSQL
        whose new values are already known (e.g. acknowledge_note()'s own
        trailing SELECT) patch the local cache instantly, without the
        extra live MSSQL round-trip sync_scope() used to need (confirmed
        live: every Acknowledge/Clear click was paying for a full table
        re-fetch just to refresh the ONE row it touched)."""
        set_clause = ", ".join(f"{col} = ?" for col in fields)

        def _work(conn):
            conn.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?", (*fields.values(), row_id))

        self._retry_write(table, _work)

    def delete_one(self, table, row_id):
        """Removes one row by id — used after a Clear action: once an
        alarm is cleared (Status=0 in MSSQL) it no longer belongs in this
        active-only cache table at all, so deleting it locally is correct
        whether OUR clear_alarm() call is what actually cleared it or the
        device beat us to it (clear_alarm()'s own WHERE RestoredTime IS
        NULL check already tolerates that race — either way, the row
        shouldn't be in an active-only cache anymore)."""
        def _work(conn):
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))

        self._retry_write(table, _work)

    def fetch_all(self, table):
        self._validate_table(table)
        with cache_conn_scope() as conn:
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY {self.order_by}").fetchall()
            return [dict(r) for r in rows]

    def fetch_columns(self, table, columns):
        """Same as fetch_all(), but SELECTs only `columns` instead of
        every column — worth it on a wide, many-row table where the
        caller only reads a couple of fields (e.g.
        get_congestion_top_devices() only ever reads device_name/
        down_time out of congestion_history_cache's 19 columns; measured
        live: SELECT * + full dict-per-row on that table's ~9-10k rows
        was ~210ms of that card's ~235ms, most of it building dict keys
        that were immediately discarded). `columns` is a fixed literal
        list of column names, never built from raw user input. `order_by`
        doesn't need to be in `columns` — SQLite can ORDER BY a column
        of the underlying table even when it isn't SELECTed."""
        self._validate_table(table)
        col_list = ", ".join(columns)
        with cache_conn_scope() as conn:
            rows = conn.execute(f"SELECT {col_list} FROM {table} ORDER BY {self.order_by}").fetchall()
            return [dict(r) for r in rows]

    def fetch_where(self, table, where_clause, params):
        """Same as fetch_all(), but with `where_clause` (a literal SQL
        fragment, e.g. "device_name = ?" — never built from raw user
        input) pushed into SQLite instead of read-then-filtered in
        Python. Only worth reaching for on a cache table big enough that
        reading every row just to discard most of them is measurable —
        see app/database/cache.py's own idx_{table}_device_name index,
        added for exactly this (congestion_history_cache's ~9-10k
        historical rows vs. the few hundred one device's own drilldown
        actually needs)."""
        self._validate_table(table)
        with cache_conn_scope() as conn:
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE {where_clause} ORDER BY {self.order_by}", params
            ).fetchall()
            return [dict(r) for r in rows]

    def last_synced_at(self, table):
        self._validate_table(table)
        with cache_conn_scope() as conn:
            row = conn.execute(
                "SELECT last_synced_at FROM sync_meta WHERE table_name = ?", (table,)
            ).fetchone()
            return row["last_synced_at"] if row else None
