"""Read/write access to the local incident_by_status cache
(instance/localstorage.db) — the joined Incident/INC-WO/Site/NMS drilldown
detail behind every Incident-column badge."""
from app.database.cache import INCIDENT_STATUS_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class IncidentStatusCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_STATUS_CACHE_TABLES
    columns = ("incident_id", "incident_status", "wo_id", "wo_created_at", "wo_status",
               "site_name", "site_code", "occurred_at", "overdue", "category",
               "l1_noc_investigation_result", "nms", "hub_site", "site_grade",
               "province", "district", "commune")
    order_by = "occurred_at DESC"
