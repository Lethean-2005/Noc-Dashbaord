"""Read/write access to the local incident_site_down_duration_weekly
cache (instance/localstorage.db) — closed Site Down incidents from the
last 30 days, with enough timestamps to bucket duration per week."""

from app.database.cache import INCIDENT_SITE_DOWN_DURATION_WEEKLY_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class IncidentSiteDownDurationWeeklyCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_SITE_DOWN_DURATION_WEEKLY_CACHE_TABLES
    columns = (
        "incident_id",
        "incident_numeric_id",
        "site",
        "site_code",
        "occurred_at",
        "resolved_at",
        "closed_at",
    )
    order_by = "closed_at"
