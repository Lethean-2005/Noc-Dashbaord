"""Pulls VIP/VVIP, On Air Site master data from MSSQL (TBL_SITE joined to
TBL_NE for VENDOR) and writes it into the local cache
(instance/localstorage.db). Mirrors the alarm sync in
app/services/alarm/alarm_sync_service.py — same reasoning applies here.
"""

from app.repositories.vip.vip_site_cache_repository import VipSiteCacheRepository
from app.repositories.vip.vip_site_repository import VipSiteRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = "vip_site_cache"


class VipSiteSyncService:
    def __init__(self, mssql_repository=None, cache_repository=None):
        self.mssql_repository = mssql_repository or VipSiteRepository()
        self.cache_repository = cache_repository or VipSiteCacheRepository()

    def sync(self):
        """Refresh the local VIP/VVIP Site cache from MSSQL. Returns the
        row count synced, or None on failure.

        Both steps below are wrapped in their own try/except and `return`
        on failure instead of raising — this runs inside an infinite
        background loop (see alarm_scheduler.py), so any uncaught exception
        here would silently kill that loop forever.
        """
        try:
            rows = self.mssql_repository.fetch_vip_sites()
        except Exception as e:
            logger.error(f"MSSQL VIP Site sync failed: {e}")
            return None

        normalized = [self._normalize(r) for r in rows]
        try:
            self.cache_repository.replace_all(_TABLE, normalized)
        except Exception as e:
            logger.error(f"VIP Site cache write failed: {e}")
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
            "site_strategic": row.get("SITE_STRATEGIC") or "",
            "vendor": row.get("VENDOR") or "",
        }
