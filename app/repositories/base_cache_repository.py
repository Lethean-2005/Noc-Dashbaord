"""Shared read/write logic for the local SQLite cache repositories
(instance/localstorage.db). Every *_cache_repository.py file was the same
~60 lines (replace_all/fetch_all/last_synced_at) with only the table
whitelist, insert columns, and fetch_all() ordering actually differing —
this pulls that shared logic into one place so each repository is just a
handful of lines declaring its own three attributes.
"""

from datetime import datetime

from app.database.cache import get_cache_conn


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
        """`table` is always one of `valid_tables`, passed by the sync
        service that owns this repository — never user input — but every
        method here builds SQL by interpolating it, so this whitelist check
        makes that provably safe rather than safe only by convention."""
        if table not in self.valid_tables:
            raise ValueError(f"Unknown cache table for {type(self).__name__}: {table!r}")

    def replace_all(self, table, rows):
        """Overwrite `table` with `rows` (list of dicts using `columns` keys)."""
        self._validate_table(table)
        conn = get_cache_conn()
        try:
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
                (table, datetime.now().isoformat(timespec="seconds")),
            )
            conn.commit()
        finally:
            conn.close()

    def fetch_all(self, table):
        self._validate_table(table)
        conn = get_cache_conn()
        try:
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY {self.order_by}").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def last_synced_at(self, table):
        self._validate_table(table)
        conn = get_cache_conn()
        try:
            row = conn.execute(
                "SELECT last_synced_at FROM sync_meta WHERE table_name = ?", (table,)
            ).fetchone()
            return row["last_synced_at"] if row else None
        finally:
            conn.close()
