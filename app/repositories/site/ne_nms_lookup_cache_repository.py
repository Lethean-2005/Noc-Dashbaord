"""Read/write access to the local site -> NMS vendor code cache
(instance/localstorage.db)."""

from app.database.cache import NE_NMS_LOOKUP_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class NeNmsLookupCacheRepository(BaseCacheRepository):
    valid_tables = NE_NMS_LOOKUP_CACHE_TABLES
    columns = ("site_code", "nms_code")
    order_by = "site_code"
