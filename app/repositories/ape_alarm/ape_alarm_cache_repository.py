"""Read/write access to the local ape_alarm cache (instance/localstorage.db)
— the broader VVIP/Mentor/RAN alarm feed from object_138."""

from app.database.cache import APE_ALARM_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository
from app.utils.ttl_cache import ttl_cache


class ApeAlarmCacheRepository(BaseCacheRepository):
    valid_tables = APE_ALARM_CACHE_TABLES
    columns = (
        "alarm_numeric_id",
        "alarm_id",
        "occurred_at",
        "event_name",
        "additional_info",
        "nms",
        "technology",
        "site_code",
        "site_name",
        "occurrence_count",
    )
    order_by = "occurred_at DESC"

    @ttl_cache(15)
    def fetch_all(self, table):
        """Cached for 15s (matches every service's own get_counts()/
        get_details() ttl_cache) so the RAN/VIP/Mentor/Alarm-* services that
        each read this table on every dashboard render — dashboard.py wires
        them all to one shared instance of this repository — hit SQLite
        once instead of once per service."""
        return super().fetch_all(table)
