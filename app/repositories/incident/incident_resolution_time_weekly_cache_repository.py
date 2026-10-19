"""Read/write access to the local incident_resolution_time_weekly cache
(instance/localstorage.db) — Resolution Time Week-over-Week, real data
from object_322 (see app/database/queries/incident_resolution_time_weekly.sql)."""

from app.database.cache import INCIDENT_RESOLUTION_TIME_WEEKLY_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class IncidentResolutionTimeWeeklyCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_RESOLUTION_TIME_WEEKLY_CACHE_TABLES
    columns = ("iso_week", "category", "incident_count", "min_minutes", "avg_minutes", "max_minutes")
    order_by = "iso_week"
