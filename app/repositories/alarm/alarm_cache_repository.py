"""Read/write access to the local alarm cache tables (instance/localstorage.db)."""
from app.database.cache import ALARM_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class AlarmCacheRepository(BaseCacheRepository):
    valid_tables = ALARM_CACHE_TABLES
    columns = ("alarm", "alarm_name", "device_name", "ip_address", "pop_name", "pop_code",
               "province", "down_time", "root_cause", "rtid", "interface",
               "source_group", "additional_info", "note")
    order_by = "down_time DESC"
