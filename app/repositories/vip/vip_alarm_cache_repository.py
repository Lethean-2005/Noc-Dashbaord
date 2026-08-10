"""Read/write access to the local vip_alarm cache (instance/localstorage.db)
— every alarm type at VIP/VVIP sites."""

from app.database.cache import VIP_ALARM_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class VipAlarmCacheRepository(BaseCacheRepository):
    valid_tables = VIP_ALARM_CACHE_TABLES
    columns = (
        "occurred_at",
        "event_name",
        "additional_info",
        "nms",
        "technology",
        "site_code",
        "site_name",
        "site_strategic_type",
        "occurrence_count",
    )
    order_by = "occurred_at DESC"
