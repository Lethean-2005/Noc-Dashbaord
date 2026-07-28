"""Read/write access to the local vip_incident_alarm cache
(instance/localstorage.db) — VIP/VVIP alarms joined to their site's
current Incident/INC-WO, if any. Purely a local join of already-synced
tables (vip_alarm, incident_by_status, site_cache) — see
app/services/vip/vip_incident_alarm_sync_service.py."""
from app.database.cache import VIP_INCIDENT_ALARM_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class VipIncidentAlarmCacheRepository(BaseCacheRepository):
    valid_tables = VIP_INCIDENT_ALARM_CACHE_TABLES
    columns = (
        "incident_id", "wo_id", "wo_created_at", "wo_status", "resolved_at",
        "site_name", "site_code", "occurred_at", "event_name", "category",
        "nms", "hub_site", "site_grade", "province",
    )
    order_by = "occurred_at DESC"
