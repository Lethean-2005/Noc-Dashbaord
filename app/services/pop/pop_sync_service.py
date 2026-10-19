"""Pulls POP master data from MSSQL (noc.TBL_POP) and writes it into the
local cache (instance/localstorage.db). Mirrors vip_site_sync_service.py —
same reasoning applies here.
"""

from app.repositories.pop.pop_cache_repository import PopCacheRepository
from app.repositories.pop.pop_repository import PopRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = "pop_cache"


class PopSyncService:
    def __init__(self, mssql_repository=None, cache_repository=None):
        self.mssql_repository = mssql_repository or PopRepository()
        self.cache_repository = cache_repository or PopCacheRepository()

    def sync(self):
        """Refresh the local POP cache from MSSQL. Returns the row count
        synced, or None on failure.

        Both steps below are wrapped in their own try/except and `return`
        on failure instead of raising — this is meant to run inside a
        background loop like the other *_sync_service.py's do, where an
        uncaught exception would silently kill that loop forever.
        """
        try:
            rows = self.mssql_repository.fetch_pops()
        except Exception as e:
            logger.error(f"MSSQL POP sync failed: {e}")
            return None

        normalized = [self._normalize(r) for r in rows]
        try:
            self.cache_repository.replace_all(_TABLE, normalized)
        except Exception as e:
            logger.error(f"POP cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_TABLE}")
        return len(normalized)

    @staticmethod
    def _normalize(row):
        return {
            "id": str(row.get("ID") or ""),
            "name": row.get("NAME") or "",
            "code": row.get("CODE") or "",
            "owner": row.get("OWNER") or "",
            "owner_code": row.get("OWNER_CODE") or "",
            "lat": row.get("LAT"),
            "long": row.get("LONG"),
            "province": row.get("PROVINCE") or "",
            "district": row.get("DISTRICT") or "",
            "commune": row.get("COMMUNE") or "",
            "location": row.get("LOCATION") or "",
            "type": row.get("TYPE") or "",
            "network_type": row.get("NETWORK_TYPE") or "",
            "con_name": row.get("CON_NAME") or "",
            "con_num": row.get("CON_NUM") or "",
            "pre_owner": row.get("PRE_OWNER") or "",
            "pro_owner": row.get("PRO_OWNER") or "",
            "remark": row.get("REMARK") or "",
            "is_removed": str(row.get("IS_REMOVED") or ""),
            "cd": str(row.get("CD") or ""),
            "md": str(row.get("MD") or ""),
            "aircon": str(row.get("AIRCON") or ""),
            "edc": str(row.get("EDC") or ""),
            "dg": str(row.get("DG") or ""),
            "solar": str(row.get("SOLAR") or ""),
            "rectifier": str(row.get("RECTIFIER") or ""),
            "inverter": str(row.get("INVERTER") or ""),
            "ups": str(row.get("UPS") or ""),
            "colocated": row.get("COLOCATED") or "",
            "active": str(row.get("ACTIVE") or ""),
            "cus": str(row.get("CUS") or ""),
            "ncode": row.get("NCODE") or "",
            "backup_status": row.get("BACKUP_STATUS") or "",
        }
