"""Read/write access to the local incident_resolution_time_details cache
(instance/localstorage.db) — per-incident rows behind Resolution Time's
duration-bucket breakdown (see
app/database/queries/incident_resolution_time_details.sql)."""

from app.database.cache import INCIDENT_RESOLUTION_TIME_DETAILS_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository
from app.utils.ttl_cache import ttl_cache


class IncidentResolutionTimeDetailsCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_RESOLUTION_TIME_DETAILS_CACHE_TABLES
    columns = (
        "incident_id",
        "incident_numeric_id",
        "iso_week",
        "category",
        "occurred_at",
        "resolved_at",
        "resolution_minutes",
    )
    order_by = "occurred_at DESC"

    @ttl_cache(15)
    def fetch_all(self, table):
        """Cached for 15s — same reasoning as
        IncidentResponseTimeDetailsCacheRepository's own override:
        dashboard.py's _resolution_time_duration_by_week() reads this
        whole table (uncached, this cost ~120ms) on every single
        dashboard render/filter click, since the module-level
        repository instance is a singleton shared across requests —
        this makes that a once-per-15s cost instead."""
        return super().fetch_all(table)
