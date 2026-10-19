"""Read/write access to the local incident_site_down_root_cause cache
(instance/localstorage.db) — per-incident Site Down detail (last 30
days) with a best-effort, unverified Root Cause Category guess."""

from app.database.cache import INCIDENT_SITE_DOWN_ROOT_CAUSE_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class IncidentSiteDownRootCauseCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_SITE_DOWN_ROOT_CAUSE_CACHE_TABLES
    columns = ("incident_id", "site", "actual_root_cause", "root_cause_category", "times", "occurred_at")
    order_by = "site, times"
