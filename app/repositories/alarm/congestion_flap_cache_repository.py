"""Read/write access to the local Congestion flap-count cache
(instance/localstorage.db) — see app/database/cache.py's own
CONGESTION_FLAP_CACHE_TABLES comment for what a "flap count" is and why
it's stored but not (yet) read by any route/template."""

from app.database.cache import CONGESTION_FLAP_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class CongestionFlapCacheRepository(BaseCacheRepository):
    valid_tables = CONGESTION_FLAP_CACHE_TABLES
    columns = ("device_name", "interface", "flap_count", "updated_at")
    order_by = "flap_count DESC"
