"""Pulls the broader NE/connectivity alarm feed from PostgreSQL (object_138)
and writes it into the local cache (instance/localstorage.db). Mirrors
incident_sync_service.py — same reasoning applies here.

Site Code used to be computed by Postgres's own get_processed_site()
PL/pgSQL function, called once per row inside the query itself — see
ape_alarm.sql's header for why that per-row procedural call was removed.
This service now resolves Site Code locally via
app/utils/get_processed_site.py's get_processed_site() (a direct Python
port of that same function), using the site_lookup cache (mirrors
PostgreSQL's site_lookup_mv) for the lookups the Postgres function used
to do internally. Site Name is still resolved locally against
site_cache, same as before.

object_138 is a 10M-row foreign table with no supporting index, so this
query can still lose the race against the replica's WAL replay
("conflict with recovery" — see ape_alarm.sql's header); the
retry/backoff that mitigates it lives in postgres_sync_utils.py (shared
with vip_alarm_sync_service.py and incident_sync_service.py).
"""

from app.repositories.ape_alarm.ape_alarm_cache_repository import ApeAlarmCacheRepository
from app.repositories.ape_alarm.ape_alarm_repository import ApeAlarmRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.repositories.site.site_lookup_cache_repository import SiteLookupCacheRepository
from app.services.postgres_sync_utils import build_site_lookup, retry_fetch, to_local_seconds
from app.utils.logger import get_logger
from app.utils.get_processed_site import get_processed_site, index_site_lookup

logger = get_logger(__name__)

_APE_ALARM_TABLE = "ape_alarm"
_SITE_TABLE = "site_cache"
_SITE_LOOKUP_TABLE = "site_lookup_cache"


class ApeAlarmSyncService:
    def __init__(
        self,
        ape_alarm_repository=None,
        cache_repository=None,
        site_cache_repository=None,
        site_lookup_cache_repository=None,
    ):
        self.ape_alarm_repository = ape_alarm_repository or ApeAlarmRepository()
        self.cache_repository = cache_repository or ApeAlarmCacheRepository()
        self.site_cache_repository = site_cache_repository or SiteCacheRepository()
        self.site_lookup_cache_repository = (
            site_lookup_cache_repository or SiteLookupCacheRepository()
        )

    def sync(self):
        """Refresh ape_alarm from PostgreSQL. Wrapped in try/except-per-step,
        same reasoning as incident_sync_service.py: an uncaught exception
        here would silently kill the infinite background loop this runs in.

        object_138's unindexed 10M-row scan loses the replica-conflict race
        more often than the lighter incident/vip_alarm queries, so this uses
        a larger retry budget than postgres_sync_utils.py's shared default
        (max_attempts=8, max_delay_seconds=30 -> worst case ~120s of sleep,
        safely inside the 300s sync interval) instead of raising the shared
        default and slowing down every other caller of retry_fetch() too.

        Returns the row count synced, or None on failure — ape_alarm_scheduler.py
        checks which of the two it got (not the count) to decide whether to
        retry sooner than normal after a failed cycle."""
        alarm_rows = retry_fetch(
            self.ape_alarm_repository.fetch_active,
            "ape_alarm",
            max_attempts=8,
            max_delay_seconds=30,
        )
        if alarm_rows is None:
            return None

        site_by_code = build_site_lookup(self.site_cache_repository, _SITE_TABLE)
        by_sran_id, by_nodeb_id, by_bts_id = index_site_lookup(self._fetch_site_lookup_rows())
        normalized = [
            self._normalize_row(r, site_by_code, by_sran_id, by_nodeb_id, by_bts_id)
            for r in alarm_rows
        ]
        try:
            self.cache_repository.replace_all(_APE_ALARM_TABLE, normalized)
        except Exception as e:
            logger.error(f"ape_alarm cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_APE_ALARM_TABLE}")
        return len(normalized)

    def _fetch_site_lookup_rows(self):
        try:
            return self.site_lookup_cache_repository.fetch_all(_SITE_LOOKUP_TABLE)
        except Exception as e:
            logger.error(f"Reading {_SITE_LOOKUP_TABLE} failed: {e}")
            return []

    @staticmethod
    def _normalize_row(row, site_by_code, by_sran_id, by_nodeb_id, by_bts_id):
        """Maps ape_alarm.sql's quoted, mixed-case column aliases onto
        clean snake_case keys matching the ape_alarm cache table. Site Code
        is resolved here (see module docstring) instead of by Postgres;
        Site Name is then resolved locally from that Site Code (see
        build_site_lookup())."""
        site_code = get_processed_site(
            row.get("Raw Site"), row.get("Additional Info"), by_sran_id, by_nodeb_id, by_bts_id
        )
        matched_site = site_by_code.get(site_code) if site_code else None

        return {
            "alarm_numeric_id": row.get("ID"),
            "alarm_id": row.get("Alarm ID") or "",
            "occurred_at": to_local_seconds(row.get("Occurred At")),
            "event_name": row.get("Event Name") or "",
            "additional_info": row.get("Additional Info") or "",
            "nms": row.get("NMS Code") or "",
            "technology": row.get("Technology") or "",
            "site_code": site_code,
            "site_name": (matched_site.get("physical_location_name") or "") if matched_site else "",
            "occurrence_count": row.get("Occurrence Count") or 1,
        }
