"""One incident per complete all-WOs-resolved source snapshot."""
from app.repositories.base_cache_repository import BaseCacheRepository


class IncWoAllResolvedCacheRepository(BaseCacheRepository):
    valid_tables = ("inc_wo_all_resolved",)
    columns = ("incident_id", "incident_numeric_id", "incident_status", "incident_category",
               "site_code", "occurred_at", "wo_count", "resolved_wo_count", "resolved_at", "all_wo_is_resolved")
    order_by = "resolved_at DESC, incident_numeric_id"
