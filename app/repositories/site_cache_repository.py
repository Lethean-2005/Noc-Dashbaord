"""Read/write access to the local Site cache (instance/localstorage.db)."""
from app.database.cache import SITE_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class SiteCacheRepository(BaseCacheRepository):
    valid_tables = SITE_CACHE_TABLES
    columns = ("id", "name", "status", "type", "site_grade", "fra_site_name", "standard_code",
               "site_priority", "province", "district", "commune", "village",
               "physical_location", "p_lat", "p_lon", "hub_site")
    order_by = "id"
