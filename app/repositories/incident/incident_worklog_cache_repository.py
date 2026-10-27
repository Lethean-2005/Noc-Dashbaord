"""Read/write access to the local incident_worklog cache
(instance/localstorage.db) — worklog entries for currently-open Site
Down incidents only, behind "Site Down by Age"'s worklog popup."""

from app.database.cache import INCIDENT_WORKLOG_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class IncidentWorklogCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_WORKLOG_CACHE_TABLES
    columns = ("incident_numeric_id", "incident_id", "entry_text", "created_at", "created_by")
    order_by = "created_at DESC"
