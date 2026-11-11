"""Read/write access to the local inc_wo_resolved cache
(instance/localstorage.db) — the joined INC-WO/Incident/Site/NMS drilldown
detail behind the "INC-WO Resolved" card on the Custom Dashboard."""

from app.database.cache import INC_WO_RESOLVED_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class IncWoResolvedCacheRepository(BaseCacheRepository):
    valid_tables = INC_WO_RESOLVED_CACHE_TABLES
    columns = (
        "incident_id",
        "incident_numeric_id",
        "incident_status",
        "wo_id",
        "wo_numeric_id",
        "wo_created_at",
        "wo_status",
        "resolved_at",
        "resolution",
        "site_name",
        "site_code",
        "overdue",
        "support_level",
        "responsible_team",
        "fault_description",
        "nms",
        "hub_site",
        "site_grade",
        "province",
        "district",
        "commune",
    )
    order_by = "wo_created_at DESC"
