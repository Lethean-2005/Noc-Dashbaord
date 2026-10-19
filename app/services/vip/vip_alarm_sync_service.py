"""Builds the vip_alarm cache (instance/localstorage.db) by filtering the
already-synced ape_alarm cache down to VIP/VVIP sites — a purely local
derivation, no Postgres call.

ape_alarm.sql and vip_alarm.sql used to run as two independent,
near-identical full scans of object_138 on separate schedules — vip_alarm's
rows were always a strict subset of what ape_alarm already fetches for the
same sites, so re-querying Postgres a second time was redundant load on a
table already prone to "conflict with recovery". This reads ape_alarm's
cache instead — a pure local derivation, no retry needed since no foreign
table/replica is involved at this layer. ape_alarm already resolves Site
Code locally too (get_processed_site.py), so this benefits from that for
free — no get_processed_site() call anywhere in this path.

A site counts as VIP/VVIP if EITHER Postgres's own site_cache.site_strategic_type
OR MSSQL's TBL_SITE.SITE_STRATEGIC (vip_site_cache, synced separately by
vip_site_sync_service.py) says so — the two systems' VIP designations can
drift apart (confirmed live for site 1517/CHI_PECH on 2026-09-22: MSSQL
says 'VIP', Postgres says 'none_strategic', and the site had a real open
Site Down incident that never reached this card because Postgres alone was
trusted). OR, not AND: this only ever pulls a site IN, never excludes one
the other system already includes.
"""

from app.repositories.ape_alarm.ape_alarm_cache_repository import ApeAlarmCacheRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.repositories.vip.vip_alarm_cache_repository import VipAlarmCacheRepository
from app.repositories.vip.vip_site_cache_repository import VipSiteCacheRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

_APE_ALARM_TABLE = "ape_alarm"
_VIP_ALARM_TABLE = "vip_alarm"
_SITE_TABLE = "site_cache"
_VIP_SITE_TABLE = "vip_site_cache"
_VIP_TYPES = {"vip", "vvip"}


class VipAlarmSyncService:
    def __init__(
        self,
        ape_alarm_cache_repository=None,
        cache_repository=None,
        site_cache_repository=None,
        vip_site_cache_repository=None,
    ):
        self.ape_alarm_cache_repository = ape_alarm_cache_repository or ApeAlarmCacheRepository()
        self.cache_repository = cache_repository or VipAlarmCacheRepository()
        self.site_cache_repository = site_cache_repository or SiteCacheRepository()
        self.vip_site_cache_repository = vip_site_cache_repository or VipSiteCacheRepository()

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
        # MSSQL's own VIP designation (TBL_SITE.SITE_STRATEGIC) — a second,
        # independent source checked alongside Postgres's, see module
        # docstring. Keyed by site_code -> its SITE_STRATEGIC value, so
        # _normalize_row() can also use it to fill in a real value instead
        # of Postgres's stale "none_strategic" for a site only MSSQL flags.
        mssql_vip_type_by_code = {
            row["site_code"]: row.get("site_strategic") or ""
            for row in self.vip_site_cache_repository.fetch_all(_VIP_SITE_TABLE)
            if row.get("site_code")
        }
        vip_rows = [
            r
            for r in alarm_rows
            if self._is_vip_site(r.get("site_code"), site_by_code, mssql_vip_type_by_code)
        ]
        normalized = [
            self._normalize_row(r, site_by_code, mssql_vip_type_by_code) for r in vip_rows
        ]
        try:
            self.cache_repository.replace_all(_VIP_ALARM_TABLE, normalized)
        except Exception as e:
            logger.error(f"vip_alarm cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_VIP_ALARM_TABLE}")
        return len(normalized)

    @staticmethod
    def _is_vip_site(site_code, site_by_code, mssql_vip_type_by_code):
        site_code = site_code or ""
        if (mssql_vip_type_by_code.get(site_code) or "").lower() in _VIP_TYPES:
            return True
        site = site_by_code.get(site_code)
        if not site:
            return False
        return (site.get("site_strategic_type") or "").lower() in _VIP_TYPES

    @staticmethod
    def _normalize_row(row, site_by_code, mssql_vip_type_by_code):
        """ape_alarm cache rows are already normalized (snake_case keys,
        Site Name already resolved) — carried through unchanged, plus
        site_strategic_type from whichever source actually flagged this
        site VIP/VVIP (Postgres's site_cache lookup preferred since it's
        the card's usual source; MSSQL's vip_site_cache only used to fill
        this in when Postgres's own value isn't VIP/VVIP)."""
        site_code = row.get("site_code") or ""
        site = site_by_code.get(site_code) or {}
        strategic_type = site.get("site_strategic_type") or ""
        if strategic_type.lower() not in _VIP_TYPES:
            mssql_type = mssql_vip_type_by_code.get(site_code) or ""
            if mssql_type.lower() in _VIP_TYPES:
                strategic_type = mssql_type
        return {
            "alarm_numeric_id": row.get("alarm_numeric_id"),
            "alarm_id": row.get("alarm_id") or "",
            "occurred_at": row.get("occurred_at") or "",
            "event_name": row.get("event_name") or "",
            "additional_info": row.get("additional_info") or "",
            "nms": row.get("nms") or "",
            "technology": row.get("technology") or "",
            "site_code": site_code,
            "site_name": row.get("site_name") or "",
            "site_strategic_type": strategic_type,
            "occurrence_count": row.get("occurrence_count") or 1,
        }
