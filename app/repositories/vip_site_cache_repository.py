"""Read/write access to the local vip_site_cache (instance/localstorage.db)."""
from app.database.cache import VIP_SITE_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class VipSiteCacheRepository(BaseCacheRepository):
    valid_tables = VIP_SITE_CACHE_TABLES
    columns = ("id", "site_code", "site_name", "bts_name", "vip", "province", "district",
               "commune", "village", "location", "site_grade", "on_air", "product",
               "tech", "site_id", "lat", "long")
    order_by = "site_name"
