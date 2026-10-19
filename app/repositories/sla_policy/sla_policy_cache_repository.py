"""Read/write access to the local sla_policy cache (instance/localstorage.db)
— the SLA Compliance card's "View SLA Policy" reference table (see
app/database/queries/sla_policy.sql). 80 rarely-changing rows, no TTL
needed unlike the per-request weekly/details caches."""

from app.database.cache import SLA_POLICY_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class SlaPolicyCacheRepository(BaseCacheRepository):
    valid_tables = SLA_POLICY_CACHE_TABLES
    columns = (
        "id",
        "category",
        "priority",
        "support_level",
        "site_grade",
        "response_time",
        "measure_response_time",
        "resolution_time",
        "measure_resolution_time",
    )
    order_by = "category, support_level, priority, site_grade"
