"""Read/write access to the local incident_by_status cache
(instance/localstorage.db) — the joined Incident/INC-WO/Site/NMS drilldown
detail behind every Incident-column badge."""

from app.database.cache import INCIDENT_STATUS_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class IncidentStatusCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_STATUS_CACHE_TABLES
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

    @staticmethod
    def latest_by_site(rows):
        """site_code -> its most recent row, given rows already ordered
        occurred_at DESC (see order_by above). A site can have more than
        one active Incident at once — keeping only the first row seen per
        site_code keeps the latest one, instead of a plain dict
        comprehension which would silently keep the last-iterated (oldest)
        one instead."""
        result = {}
        for r in rows:
            code = r.get("site_code")
            if code and code not in result:
                result[code] = r
        return result
