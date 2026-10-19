"""Read/write access to the local incident_response_time_weekly cache
(instance/localstorage.db) — Response Time Week-over-Week, real data
from object_322 (see app/database/queries/incident_response_time_weekly.sql)."""

from app.database.cache import INCIDENT_RESPONSE_TIME_WEEKLY_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class IncidentResponseTimeWeeklyCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_RESPONSE_TIME_WEEKLY_CACHE_TABLES
    columns = ("iso_week", "category", "incident_count", "min_minutes", "avg_minutes", "max_minutes")
    order_by = "iso_week"
