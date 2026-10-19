"""Read/write access to the local incident_closed_trend cache
(instance/localstorage.db) — one row per Incident closed in the last 15
days, behind the "Incidents Closed – Week over Week" dashboard card."""

from app.database.cache import INCIDENT_CLOSED_TREND_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository
from app.utils.ttl_cache import ttl_cache


class IncidentClosedTrendCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_CLOSED_TREND_CACHE_TABLES
    columns = (
        "incident_id",
        "incident_numeric_id",
        "closed_at",
        "incident_status",
        "category",
        "site_name",
        "site_code",
        "province",
        "district",
        "commune",
    )
    order_by = "closed_at DESC"

    @ttl_cache(15)
    def fetch_all(self, table):
        """Cached for 15s — same reasoning as
        IncidentCreatedTrendCacheRepository's own override."""
        return super().fetch_all(table)
