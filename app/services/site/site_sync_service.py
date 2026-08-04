"""Pulls Site records from PostgreSQL (object_160) and writes them into the
local cache (instance/localstorage.db). Mirrors the MSSQL alarm sync in
app/services/alarm/alarm_sync_service.py, but for the Postgres-backed Site table —
kept separate since the two sources are unrelated.
"""
from app.repositories.site.ne_nms_lookup_cache_repository import NeNmsLookupCacheRepository
from app.repositories.site.ne_nms_lookup_repository import NeNmsLookupRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.repositories.site.site_repository import SiteRepository
from app.repositories.site.site_technology_cache_repository import SiteTechnologyCacheRepository
from app.repositories.site.site_technology_repository import SiteTechnologyRepository
from app.services.postgres_sync_utils import retry_fetch
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = "site_cache"
_TECHNOLOGY_TABLE = "site_technology_cache"
_NE_NMS_LOOKUP_TABLE = "ne_nms_lookup_cache"


class SiteSyncService:
    def __init__(self, site_repository=None, cache_repository=None,
                 site_technology_repository=None, site_technology_cache_repository=None,
                 ne_nms_lookup_repository=None, ne_nms_lookup_cache_repository=None):
        self.site_repository = site_repository or SiteRepository()
        self.cache_repository = cache_repository or SiteCacheRepository()
        self.site_technology_repository = site_technology_repository or SiteTechnologyRepository()
        self.site_technology_cache_repository = (
            site_technology_cache_repository or SiteTechnologyCacheRepository()
        )
        self.ne_nms_lookup_repository = ne_nms_lookup_repository or NeNmsLookupRepository()
        self.ne_nms_lookup_cache_repository = (
            ne_nms_lookup_cache_repository or NeNmsLookupCacheRepository()
        )

    def sync(self):
        """Refresh the local Site cache from PostgreSQL. Returns the row
        count synced, or None on failure.

        Both steps below are wrapped in their own try/except and `return`
        on failure instead of raising — this runs inside an infinite
        background loop (see site_scheduler.py), so any uncaught exception
        here would silently kill that loop forever.
        """
        try:
            rows = self.site_repository.fetch_all()
        except Exception as e:
            logger.error(f"Postgres Site sync failed: {e}")
            return None

        normalized = [{c: row.get(c) for c in SiteCacheRepository.columns} for row in rows]
        try:
            self.cache_repository.replace_all(_TABLE, normalized)
        except Exception as e:
            logger.error(f"Site cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_TABLE}")
        return len(normalized)

    def sync_technology(self):
        """Refresh the local site technology inventory cache from
        object_227 — confirmed prone to "conflict with recovery" (see
        incident_sync_service.py's module docstring), so this goes through
        retry_fetch() same as every other object_227-touching sync. Returns
        the row count synced, or None on failure."""
        rows = retry_fetch(self.site_technology_repository.fetch_all, "Site-technology")
        if rows is None:
            return None

        normalized = [
            {"site_code": row.get("Site Code"), "technology": row.get("Technology")} for row in rows
        ]
        try:
            self.site_technology_cache_repository.replace_all(_TECHNOLOGY_TABLE, normalized)
        except Exception as e:
            logger.error(f"Site-technology cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_TECHNOLOGY_TABLE}")
        return len(normalized)

    def sync_ne_nms(self):
        """Refresh the local site -> NMS vendor code cache from object_227 —
        same retry_fetch() reasoning as sync_technology() above (object_227
        is confirmed prone to "conflict with recovery"). This replaces the
        `single_ne`/`sne` window function that used to be duplicated inside
        6 separate query files (incident_by_status.sql and friends) — those
        now just join against this one shared cache in Python instead.
        Returns the row count synced, or None on failure."""
        rows = retry_fetch(self.ne_nms_lookup_repository.fetch_all, "NE-NMS-lookup")
        if rows is None:
            return None

        normalized = [
            {"site_code": row.get("Site Code"), "nms_code": row.get("NMS Code")} for row in rows
        ]
        try:
            self.ne_nms_lookup_cache_repository.replace_all(_NE_NMS_LOOKUP_TABLE, normalized)
        except Exception as e:
            logger.error(f"NE-NMS-lookup cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_NE_NMS_LOOKUP_TABLE}")
        return len(normalized)
