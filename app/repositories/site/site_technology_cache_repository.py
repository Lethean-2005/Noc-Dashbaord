"""Read/write access to the local site technology inventory cache
(instance/localstorage.db) — which of 2g/3g/4g/5g each site actually has."""

from app.database.cache import SITE_TECHNOLOGY_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class SiteTechnologyCacheRepository(BaseCacheRepository):
    valid_tables = SITE_TECHNOLOGY_CACHE_TABLES
    columns = ("site_code", "technology")
    order_by = "site_code"
