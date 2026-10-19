"""Read/write access to the local site-level actual RAN vendor cache
(instance/localstorage.db)."""

from app.database.cache import SITE_RAN_VENDOR_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class SiteRanVendorCacheRepository(BaseCacheRepository):
    valid_tables = SITE_RAN_VENDOR_CACHE_TABLES
    columns = ("site_code", "actual_ran_vendor")
    order_by = "site_code"
