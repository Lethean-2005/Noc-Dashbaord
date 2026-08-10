"""Read/write access to the local site_lookup cache (instance/localstorage.db)
— mirrors PostgreSQL's site_lookup_mv."""

from app.database.cache import SITE_LOOKUP_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class SiteLookupCacheRepository(BaseCacheRepository):
    valid_tables = SITE_LOOKUP_CACHE_TABLES
    columns = ("sran_id", "nodeb_id", "bts_id", "site_name")
    order_by = "rowid"
