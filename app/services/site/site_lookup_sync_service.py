"""Pulls site_lookup_mv from PostgreSQL and writes it into the local cache
(instance/localstorage.db). Mirrors app/services/site/site_sync_service.py.

This is the lookup table Postgres's own get_processed_site() PL/pgSQL
function used to query internally (once per row of object_138) — see
app/utils/get_processed_site.py for the Python port of that function's logic, which
reads this cache instead of Postgres doing the lookup per-row.
"""
from app.repositories.site.site_lookup_cache_repository import SiteLookupCacheRepository
from app.repositories.site.site_lookup_repository import SiteLookupRepository
from app.services.postgres_sync_utils import retry_fetch
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = "site_lookup_cache"


class SiteLookupSyncService:
    def __init__(self, site_lookup_repository=None, cache_repository=None):
        self.site_lookup_repository = site_lookup_repository or SiteLookupRepository()
        self.cache_repository = cache_repository or SiteLookupCacheRepository()

    def sync(self):
        """Refresh the local site_lookup cache from PostgreSQL. Wrapped in
        try/except-per-step, same reasoning as every other sync service:
        this runs inside an infinite background loop, so any uncaught
        exception here would silently kill that loop forever. Returns the
        row count synced, or None on failure."""
        rows = retry_fetch(self.site_lookup_repository.fetch_all, "site_lookup")
        if rows is None:
            return None

        normalized = [{c: row.get(c) for c in SiteLookupCacheRepository.columns} for row in rows]
        try:
            self.cache_repository.replace_all(_TABLE, normalized)
        except Exception as e:
            logger.error(f"site_lookup cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_TABLE}")
        return len(normalized)
