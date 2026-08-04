"""Pulls active alarms from MSSQL and writes them into the local cache
(instance/localstorage.db). This is the only place that talks to MSSQL for
the ISP POP / EZE / TCT / IT NODE cards — app/services/alarm/alarm_service.py
reads the cache that this writes, so request-time pages never wait on MSSQL.
"""

from app.repositories.alarm.alarm_cache_repository import AlarmCacheRepository
from app.repositories.alarm.alarm_repository import AlarmRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

# One entry per card. Each is: (cache table to write into, the
# AlarmRepository method that fetches its MSSQL rows, which raw MSSQL
# column holds "the alarm type" for that card — ISP POP/IT NODE use
# AlarmName directly, EZE/TCT derive alarm_type from it in the SQL query
# itself).
_JOBS = (
    ("isp_pop_alarm_cache", "fetch_isp_pop_active", "AlarmName"),
    ("eze_alarm_cache", "fetch_eze_active", "alarm_type"),
    ("tct_alarm_cache", "fetch_tct_active", "alarm_type"),
    ("it_node_alarm_cache", "fetch_it_node_active", "AlarmName"),
)


class AlarmSyncService:
    def __init__(self, mssql_repository=None, cache_repository=None):
        self.mssql_repository = mssql_repository or AlarmRepository()
        self.cache_repository = cache_repository or AlarmCacheRepository()

    def sync_all(self):
        """Refresh all 4 cache tables from MSSQL. Called every
        MSSQL_SYNC_INTERVAL_SECONDS by app/services/alarm/alarm_scheduler.py.
        Returns the total row count synced across all 4 tables (a table
        that failed contributes 0, same as an empty result — its own error
        is already logged by _sync_one() below) so the scheduler can report
        one combined "Total" line for the whole cycle."""
        total = 0
        for table, fetch_name, alarm_field in _JOBS:
            total += self._sync_one(table, fetch_name, alarm_field) or 0
        return total

    def _sync_one(self, table, fetch_name, alarm_field):
        """Fetch one card's rows from MSSQL and overwrite its cache table.
        Returns the row count synced, or None on failure.

        Both steps below are wrapped in their own try/except and `return`
        on failure instead of raising — this runs inside an infinite
        background loop (see alarm_scheduler.py), so any uncaught exception
        here would silently kill that loop forever. Logging and returning
        keeps this cycle a no-op (existing cache stays as-is, so a card
        shows slightly stale data rather than none) while leaving the loop
        itself free to try again next interval.
        """
        try:
            rows = getattr(self.mssql_repository, fetch_name)()
        except Exception as e:
            logger.error(f"MSSQL sync failed for {table}: {e}")
            return None

        normalized = [self._normalize(r, alarm_field) for r in rows]
        try:
            self.cache_repository.replace_all(table, normalized)
        except Exception as e:
            logger.error(f"Cache write failed for {table}: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {table}")
        return len(normalized)

    @staticmethod
    def _normalize(row, alarm_field):
        """Map MSSQL's column names (PascalCase, inconsistent across the 3
        queries) onto one consistent lowercase shape that the cache table,
        AlarmService, and the drilldown templates all agree on.

        `alarm` is the DERIVED type (e.g. 'port', 'congestion' for TCT — no
        prefix, lowercased) used internally for badge counting and the
        `type` drilldown filter; it must keep matching EZE_TYPES/TCT_TYPES.
        `alarm_name` is the RAW AlarmName column (e.g. 'TCT_PORT') used only
        for display in the drilldown table's Alarm Name column — never used
        for matching/filtering, so changing its format elsewhere is safe.
        """
        return {
            "id": str(row.get("ID") or ""),
            "alarm": row.get(alarm_field) or row.get("AlarmName") or "",
            "alarm_name": row.get("AlarmName") or "",
            "device_name": row.get("DeviceName") or "",
            "ip_address": row.get("IPAddress") or "",
            "pop_name": row.get("pop_name") or "",
            "pop_code": row.get("pop_code") or "",
            "province": row.get("Province") or "",
            "down_time": str(row.get("DownTime") or ""),
            "root_cause": row.get("PROBLEM_DETAILS") or row.get("PROBABLE_CAUSE") or "",
            "rtid": row.get("RTID") or "",
            "interface": row.get("INTERFACE") or "",
            "source_group": row.get("SourceGroup") or "",
            "additional_info": row.get("ADD_INFO") or "",
            "note": row.get("NOTE") or "",
            "ack": str(row.get("ACK") or ""),
            "ab": row.get("AB") or "",
            "mb": row.get("MB") or "",
            "md": str(row.get("MD") or ""),
        }
