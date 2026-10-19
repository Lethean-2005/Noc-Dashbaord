"""Read/write access to the local POP cache (instance/localstorage.db)."""

from app.database.cache import POP_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class PopCacheRepository(BaseCacheRepository):
    valid_tables = POP_CACHE_TABLES
    columns = (
        "id",
        "name",
        "code",
        "owner",
        "owner_code",
        "lat",
        "long",
        "province",
        "district",
        "commune",
        "location",
        "type",
        "network_type",
        "con_name",
        "con_num",
        "pre_owner",
        "pro_owner",
        "remark",
        "is_removed",
        "cd",
        "md",
        "aircon",
        "edc",
        "dg",
        "solar",
        "rectifier",
        "inverter",
        "ups",
        "colocated",
        "active",
        "cus",
        "ncode",
        "backup_status",
    )
    order_by = "name"
