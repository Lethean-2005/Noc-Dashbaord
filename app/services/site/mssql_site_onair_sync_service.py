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

        # mssql_site.sql's own SELECT DISTINCT is meant to guarantee one row
        # per SITE_CODE (documented there: "every real site's NEs agree on
        # one VENDOR... so this stays one row per site") — but that only
        # covers VENDOR; a site with 2+ NE records whose OTHER fields differ
        # (confirmed live: site 8185 has an Indoor/MW NE and a separate
        # Outdoor/FO NE, same vendor, different BTS_ROOM/LINK_TYPE/LAT/LONG)
        # still produces 2 distinct rows, which then collided on
        # site_code's UNIQUE constraint and failed the ENTIRE cache write —
        # not just that one site, every sync attempt since. Deduping here
        # (first-seen per site_code, same "keep going despite one bad site"
        # stance as the rest of this file) keeps one row per site
        # regardless of how many NE records it has.
        seen_site_codes = set()
        deduped = []
        for r in rows:
            code = r.get("SITE_CODE")
            if code in seen_site_codes:
                continue
            seen_site_codes.add(code)
            deduped.append(r)

        normalized = [self._normalize(r) for r in deduped]
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
