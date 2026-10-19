"""Read/write access to the local Counterparty catalog cache
(instance/localstorage.db)."""

from app.database.cache import COUNTERPARTY_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class CounterpartyCacheRepository(BaseCacheRepository):
    valid_tables = COUNTERPARTY_CACHE_TABLES
    columns = ("id", "name", "type")
    order_by = "id"
