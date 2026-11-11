"""Read/write access to the local site -> RAN/SRAN baseband name cache
(instance/localstorage.db)."""

from app.database.cache import SITE_RAN_NAME_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class SiteRanNameCacheRepository(BaseCacheRepository):
    valid_tables = SITE_RAN_NAME_CACHE_TABLES
    columns = ("site_code", "ran_name")
    order_by = "site_code"
