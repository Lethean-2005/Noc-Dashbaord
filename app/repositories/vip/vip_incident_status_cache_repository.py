"""Read/write access to the local vip_incident_status cache — same
shape as incident_by_status, scoped to VIP/VVIP sites with
status != 'closed' (so Resolved stays). Used only by VipAlarmService's
enrichment."""

from app.database.cache import VIP_INCIDENT_STATUS_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class VipIncidentStatusCacheRepository(BaseCacheRepository):
    valid_tables = VIP_INCIDENT_STATUS_CACHE_TABLES
    columns = (
        "incident_id",
        "incident_numeric_id",
        "incident_status",
        "wo_id",
        "wo_numeric_id",
        "wo_created_at",
        "wo_status",
        "resolved_at",
        "responsible_team",
        "support_level",
        "site_name",
        "site_code",
        "occurred_at",
        "overdue",
        "category",
        "l1_noc_investigation_result",
        "nms",
        "hub_site",
        "site_grade",
        "province",
        "district",
        "commune",
    )
    order_by = "occurred_at DESC"
