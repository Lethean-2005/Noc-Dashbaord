"""Read/write access to the local incident_created_trend cache
(instance/localstorage.db) — one row per Incident created in the last 15
days, behind the "Incident Volume – Week over Week" dashboard card."""

from app.database.cache import INCIDENT_CREATED_TREND_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository
from app.utils.ttl_cache import ttl_cache


class IncidentCreatedTrendCacheRepository(BaseCacheRepository):
    valid_tables = INCIDENT_CREATED_TREND_CACHE_TABLES
    columns = (
        "incident_id",
        "incident_numeric_id",
        "created_at",
        "incident_status",
        "category",
        "severity",
        "site_name",
        "site_code",
        "vendor",
        "province",
        "district",
        "commune",
    )
    order_by = "created_at DESC"

    @ttl_cache(15)
    def fetch_all(self, table):
        """Cached for 15s — same reasoning as
        IncidentResponseTimeDetailsCacheRepository's own override: this
        ~12-15k row table backs the Incident Volume card's trend chart
        AND all 8 of its category/severity/province/vendor breakdowns
        (dashboard.py's _graph_cards_context() already fetches it once
        per request and reuses those rows via `rows=` — this makes
        repeat requests within 15s, e.g. the page's own auto-reload or
        another NOC staff member's browser, skip the fetch entirely
        instead of re-reading + re-dict-converting every row again)."""
        return super().fetch_all(table)
