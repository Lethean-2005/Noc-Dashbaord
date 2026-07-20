"""Read/write access to the local inc_wo_by_status cache
(instance/localstorage.db) — the joined INC-WO/Incident/Site/NMS drilldown
detail behind every INC-WO-column badge."""
from app.database.cache import INC_WO_STATUS_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class IncWoStatusCacheRepository(BaseCacheRepository):
    valid_tables = INC_WO_STATUS_CACHE_TABLES
    columns = ("incident_id", "wo_id", "wo_created_at", "wo_status",
               "site_name", "site_code", "overdue", "support_level",
               "fault_description", "nms", "hub_site", "site_grade",
               "province", "district", "commune")
    order_by = "wo_created_at DESC"
