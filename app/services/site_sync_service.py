"""Pulls Site records from PostgreSQL (object_160) and writes them into the
local cache (instance/localstorage.db). Mirrors the MSSQL alarm sync in
app/services/alarm_sync_service.py, but for the Postgres-backed Site table —
kept separate since the two sources are unrelated.
"""
from app.repositories.site_cache_repository import SiteCacheRepository
from app.repositories.site_repository import SiteRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = "site_cache"


class SiteSyncService:
    def __init__(self, site_repository=None, cache_repository=None):
        self.site_repository = site_repository or SiteRepository()
        self.cache_repository = cache_repository or SiteCacheRepository()

    def sync(self):
        """Refresh the local Site cache from PostgreSQL.

        Both steps below are wrapped in their own try/except and `return`
        on failure instead of raising — this runs inside an infinite
        background loop (see site_scheduler.py), so any uncaught exception
        here would silently kill that loop forever.
        """
        try:
            rows = self.site_repository.fetch_all()
        except Exception as e:
            logger.error(f"Postgres Site sync failed: {e}")
            return

        normalized = [{c: row.get(c) for c in SiteCacheRepository.columns} for row in rows]
        try:
            self.cache_repository.replace_all(_TABLE, normalized)
        except Exception as e:
            logger.error(f"Site cache write failed: {e}")
            return
        logger.info(f"Synced {len(normalized)} row(s) into {_TABLE}")
