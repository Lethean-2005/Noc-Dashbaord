"""Read/write access to the local incident_duration_weekly cache
(instance/localstorage.db) — closed incidents (every category) from the
last 30 days, with enough timestamps to bucket duration per weekday."""

from app.database.cache import INCIDENT_DURATION_WEEKLY_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class IncidentDurationWeeklyCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_DURATION_WEEKLY_CACHE_TABLES
    columns = (
        "incident_id",
        "incident_numeric_id",
        "category",
        "site",
        "site_code",
        "occurred_at",
        "resolved_at",
        "closed_at",
    )
    order_by = "closed_at"
