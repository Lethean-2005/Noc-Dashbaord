"""Read/write access to the local MSSQL On-Air site cache
(instance/localstorage.db)."""

from app.database.cache import MSSQL_SITE_ONAIR_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class MssqlSiteOnairCacheRepository(BaseCacheRepository):
    valid_tables = MSSQL_SITE_ONAIR_CACHE_TABLES
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
        "vendor",
    )
    order_by = "site_code"
