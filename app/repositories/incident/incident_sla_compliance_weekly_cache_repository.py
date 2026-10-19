"""Read/write access to the local incident_sla_compliance_weekly cache
(instance/localstorage.db) — SLA Compliance Weekly Trends, real data
from object_322 (see app/database/queries/incident_sla_compliance_weekly.sql)."""

from app.database.cache import INCIDENT_SLA_COMPLIANCE_WEEKLY_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class IncidentSlaComplianceWeeklyCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_SLA_COMPLIANCE_WEEKLY_CACHE_TABLES
    columns = (
        "iso_week",
        "category",
        "priority",
        "incident_count",
        "response_met_count",
        "response_sla_pct",
        "resolution_known_count",
        "resolution_met_count",
        "resolution_sla_pct",
    )
    order_by = "iso_week"
