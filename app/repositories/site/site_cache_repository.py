"""Read/write access to the local Site cache (instance/localstorage.db)."""

from app.database.cache import SITE_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository
from app.utils.ttl_cache import ttl_cache


class SiteCacheRepository(BaseCacheRepository):
    valid_tables = SITE_CACHE_TABLES
    columns = (
        "id",
        "name",
        "status",
        "type",
        "site_grade",
        "fra_site_name",
        "standard_code",
        "site_priority",
        "site_strategic_type",
        "province",
        "district",
        "commune",
        "village",
        "physical_location",
        "physical_location_name",
        "physical_location_address",
        "p_lat",
        "p_lon",
        "hub_site",
        "actual_ran_vendor",
    )
    order_by = "id"

    @ttl_cache(15)
    def fetch_all(self, table):
        """Cached for 15s — see ApeAlarmCacheRepository.fetch_all()'s own
        note; this table has the same "one shared instance, many services"
        redundant-read pattern on the dashboard."""
        return super().fetch_all(table)
