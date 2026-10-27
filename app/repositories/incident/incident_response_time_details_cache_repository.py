"""Read/write access to the local incident_response_time_details cache
(instance/localstorage.db) — per-incident rows behind Response Time's
duration-bucket breakdown (see
app/database/queries/incident_response_time_details.sql)."""

from app.database.cache import INCIDENT_RESPONSE_TIME_DETAILS_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository
from app.utils.ttl_cache import ttl_cache


class IncidentResponseTimeDetailsCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_RESPONSE_TIME_DETAILS_CACHE_TABLES
    columns = (
        "incident_id",
        "incident_numeric_id",
        "iso_week",
        "category",
        "occurred_at",
        "took_in_progress_at",
        "response_minutes",
        "creation_method",
    )
    order_by = "occurred_at DESC"

    @ttl_cache(15)
    def fetch_all(self, table):
        """Cached for 15s — same reasoning as ApeAlarmCacheRepository's
        own override: dashboard.py's _response_time_duration_by_week()
        reads this whole ~12k-row table (uncached, this cost ~75ms) on
        every single dashboard render/filter click, since the module-
        level repository instance is a singleton shared across
        requests — this makes that a once-per-15s cost instead."""
        return super().fetch_all(table)
