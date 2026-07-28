"""Read/write access to the local ape_alarm cache (instance/localstorage.db)
— the broader VVIP/Mentor/RAN alarm feed from object_138."""
from app.database.cache import APE_ALARM_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class ApeAlarmCacheRepository(BaseCacheRepository):
    valid_tables = APE_ALARM_CACHE_TABLES
    columns = (
        "occurred_at", "event_name", "additional_info", "nms", "technology",
        "site_code", "site_name", "occurrence_count",
    )
    order_by = "occurred_at DESC"
