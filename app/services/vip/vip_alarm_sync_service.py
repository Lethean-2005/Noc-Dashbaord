"""Builds the vip_alarm cache (instance/localstorage.db) by filtering the
already-synced ape_alarm cache down to VIP/VVIP sites — a purely local
derivation, no Postgres call.

ape_alarm.sql and vip_alarm.sql used to run as two independent,
near-identical full scans of object_138 on separate schedules (both "every
alarm type opened, no date window") — vip_alarm's rows were always a
strict subset of what ape_alarm already fetches for the same sites, so
re-querying Postgres a second time for the same underlying data was
redundant load on a table already prone to "conflict with recovery". This
reads ape_alarm's cache instead — a pure local derivation of an already-
synced table, no retry needed since there's no foreign table or replica
involved at this layer. ape_alarm already resolves Site Code locally too
(app/utils/get_processed_site.py, see ape_alarm_sync_service.py), so this benefits
from that for free — no get_processed_site() call anywhere in this path.
"""

from app.repositories.ape_alarm.ape_alarm_cache_repository import ApeAlarmCacheRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.repositories.vip.vip_alarm_cache_repository import VipAlarmCacheRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

_APE_ALARM_TABLE = "ape_alarm"
_VIP_ALARM_TABLE = "vip_alarm"
_SITE_TABLE = "site_cache"
_VIP_TYPES = {"vip", "vvip"}


class VipAlarmSyncService:
    def __init__(
        self, ape_alarm_cache_repository=None, cache_repository=None, site_cache_repository=None
    ):
        self.ape_alarm_cache_repository = ape_alarm_cache_repository or ApeAlarmCacheRepository()
        self.cache_repository = cache_repository or VipAlarmCacheRepository()
        self.site_cache_repository = site_cache_repository or SiteCacheRepository()

    def sync(self):
        """Rebuild vip_alarm from the already-synced ape_alarm cache table.
        Wrapped in try/except-per-step, same reasoning as every other sync
        service: this runs inside an infinite background loop, so any
        uncaught exception here would silently kill that loop forever.
        Returns the row count synced, or None on failure."""
        try:
            alarm_rows = self.ape_alarm_cache_repository.fetch_all(_APE_ALARM_TABLE)
        except Exception as e:
            logger.error(f"Reading {_APE_ALARM_TABLE} for vip_alarm failed: {e}")
            return None

        site_by_code = {
            row["standard_code"]: row
            for row in self.site_cache_repository.fetch_all(_SITE_TABLE)
            if row.get("standard_code")
        }
        vip_rows = [r for r in alarm_rows if self._is_vip_site(r.get("site_code"), site_by_code)]
        normalized = [self._normalize_row(r, site_by_code) for r in vip_rows]
        try:
            self.cache_repository.replace_all(_VIP_ALARM_TABLE, normalized)
        except Exception as e:
            logger.error(f"vip_alarm cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_VIP_ALARM_TABLE}")
        return len(normalized)

    @staticmethod
    def _is_vip_site(site_code, site_by_code):
        site = site_by_code.get(site_code or "")
        if not site:
            return False
        return (site.get("site_strategic_type") or "").lower() in _VIP_TYPES

    @staticmethod
    def _normalize_row(row, site_by_code):
        """ape_alarm cache rows are already normalized (snake_case keys,
        Site Name already resolved) — carried through unchanged, plus
        site_strategic_type from the same site_cache lookup used to filter
        for VIP/VVIP above."""
        site_code = row.get("site_code") or ""
        site = site_by_code.get(site_code) or {}
        return {
            "occurred_at": row.get("occurred_at") or "",
            "event_name": row.get("event_name") or "",
            "additional_info": row.get("additional_info") or "",
            "nms": row.get("nms") or "",
            "technology": row.get("technology") or "",
            "site_code": site_code,
            "site_name": row.get("site_name") or "",
            "site_strategic_type": site.get("site_strategic_type") or "",
            "occurrence_count": row.get("occurrence_count") or 1,
        }
