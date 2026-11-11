"""Read/write access to the local incident_sla_compliance_details cache
(instance/localstorage.db) — per-incident rows behind the SLA Compliance
card's per-week popup (see
app/database/queries/incident_sla_compliance_details.sql)."""

from app.database.cache import INCIDENT_SLA_COMPLIANCE_DETAILS_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository
from app.utils.ttl_cache import ttl_cache


class IncidentSlaComplianceDetailsCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_SLA_COMPLIANCE_DETAILS_CACHE_TABLES
    columns = (
        "incident_id",
        "incident_numeric_id",
        "iso_week",
        "response_iso_week",
        "resolution_iso_week",
        "category",
        "priority",
        "support_level",
        "site_grade",
        "occurred_at",
        "overdue_response",
        "overdue",
        "root_cause_category",
    )
    order_by = "occurred_at DESC"

    @ttl_cache(15)
    def fetch_all(self, table):
        """Cached for 15s — same reasoning as
        IncidentResponseTimeDetailsCacheRepository's own override: the
        module-level repository instance is a singleton shared across
        requests, so this makes a filter Apply/Clear click reuse the
        same read instead of re-fetching the whole table every time."""
        return super().fetch_all(table)
