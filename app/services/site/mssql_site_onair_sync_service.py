"""Pulls On-Air site master data from MSSQL (TBL_SITE joined to TBL_NE for
VENDOR) and writes it into the local cache (instance/localstorage.db).
Mirrors pop_sync_service.py — same reasoning applies here. Independent
from site_sync_service.py (Postgres's object_160): see
app/database/queries/mssql_site.sql for why the two sources aren't
interchangeable.
"""

from app.repositories.site.mssql_site_onair_cache_repository import (
    MssqlSiteOnairCacheRepository,
)
from app.repositories.site.mssql_site_onair_repository import MssqlSiteOnairRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = "mssql_site_onair"


class MssqlSiteOnairSyncService:
    def __init__(self, mssql_repository=None, cache_repository=None):
        self.mssql_repository = mssql_repository or MssqlSiteOnairRepository()
        self.cache_repository = cache_repository or MssqlSiteOnairCacheRepository()

    def sync(self):
        """Refresh the local MSSQL On-Air site cache. Returns the row count
        synced, or None on failure.

        Both steps below are wrapped in their own try/except and `return`
        on failure instead of raising — this is meant to run inside a
        background loop like the other *_sync_service.py's do, where an
        uncaught exception would silently kill that loop forever.
        """
        try:
            rows = self.mssql_repository.fetch_all()
        except Exception as e:
            logger.error(f"MSSQL Site On-Air sync failed: {e}")
            return None

        normalized = [self._normalize(r) for r in rows]
        try:
            self.cache_repository.replace_all(_TABLE, normalized)
        except Exception as e:
            logger.error(f"MSSQL Site On-Air cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_TABLE}")
        return len(normalized)

    @staticmethod
    def _normalize(row):
        return {
            "site_code": row.get("SITE_CODE") or "",
            "site_name": row.get("SITE_NAME") or "",
            "status": row.get("STATUS") or "",
            "province": row.get("PROVINCE") or "",
            "district": row.get("DISTRICT") or "",
            "village": row.get("VILLAGE") or "",
            "lat": row.get("LAT"),
            "long": row.get("LONG"),
            "bts_room": row.get("BTS_ROOM") or "",
            "link_type": row.get("LINK_TYPE") or "",
            "site_grade": row.get("SITE_GRADE") or "",
            "site_type": row.get("SITE_TYPE") or "",
            "location": row.get("LOCATION") or "",
            "vendor": row.get("VENDOR") or "",
        }
