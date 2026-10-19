"""Read/write access to the local vip_site_cache (instance/localstorage.db)."""

from app.database.cache import VIP_SITE_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class VipSiteCacheRepository(BaseCacheRepository):
    valid_tables = VIP_SITE_CACHE_TABLES
    columns = (
        "site_code",
        "site_name",
        "status",
        "province",
        "district",
        "village",
        "lat",
        "long",
        "bts_room",
        "link_type",
        "site_grade",
        "site_type",
        "location",
        "site_strategic",
        "vendor",
    )
    order_by = "site_name"
