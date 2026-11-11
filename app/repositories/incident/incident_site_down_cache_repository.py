"""Read/write access to the local incident_site_down cache
(instance/localstorage.db) — behind the "Incident Site Down" card on the
Custom Dashboard."""

from app.database.cache import INCIDENT_SITE_DOWN_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class IncidentSiteDownCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_SITE_DOWN_CACHE_TABLES
    columns = (
        "incident_id",
        "incident_numeric_id",
        "incident_status",
        "wo_id",
        "wo_numeric_id",
        "wo_created_at",
        "wo_status",
        "site_name",
        "site_code",
        "occurred_at",
        "l1_noc_investigation_result",
        "actual_root_cause",
        "last_comments",
        "source",
        "nms",
        "hub_site",
        "site_grade",
        "province",
        "district",
        "commune",
    )
    order_by = "occurred_at DESC"
