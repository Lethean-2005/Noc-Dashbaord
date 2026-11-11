"""Pulls Site records from PostgreSQL (object_160) and writes them into the
local cache (instance/localstorage.db). Mirrors the MSSQL alarm sync in
app/services/alarm/alarm_sync_service.py, but for the Postgres-backed Site table —
kept separate since the two sources are unrelated.
"""

from app.repositories.site.counterparty_cache_repository import CounterpartyCacheRepository
from app.repositories.site.counterparty_repository import CounterpartyRepository
from app.repositories.site.ne_nms_lookup_cache_repository import NeNmsLookupCacheRepository
from app.repositories.site.ne_nms_lookup_repository import NeNmsLookupRepository
from app.repositories.site.mssql_site_ran_name_repository import MssqlSiteRanNameRepository
from app.repositories.site.mssql_site_technology_repository import MssqlSiteTechnologyRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.repositories.site.site_ran_name_cache_repository import SiteRanNameCacheRepository
from app.repositories.site.site_ran_vendor_cache_repository import SiteRanVendorCacheRepository
from app.repositories.site.site_ran_vendor_repository import SiteRanVendorRepository
from app.repositories.site.site_repository import SiteRepository
from app.repositories.site.site_technology_cache_repository import SiteTechnologyCacheRepository
from app.services.postgres_sync_utils import retry_fetch
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = "site_cache"
_TECHNOLOGY_TABLE = "site_technology_cache"
_NE_NMS_LOOKUP_TABLE = "ne_nms_lookup_cache"
_SITE_RAN_VENDOR_TABLE = "site_ran_vendor_cache"
_RAN_NAME_TABLE = "site_ran_name_cache"
_COUNTERPARTY_TABLE = "counterparty_cache"


class SiteSyncService:
    def __init__(
        self,
        site_repository=None,
        cache_repository=None,
        site_technology_repository=None,
        site_technology_cache_repository=None,
        ne_nms_lookup_repository=None,
        ne_nms_lookup_cache_repository=None,
        site_ran_vendor_repository=None,
        site_ran_vendor_cache_repository=None,
        site_ran_name_repository=None,
        site_ran_name_cache_repository=None,
        counterparty_repository=None,
        counterparty_cache_repository=None,
    ):
        self.site_repository = site_repository or SiteRepository()
        self.cache_repository = cache_repository or SiteCacheRepository()
        self.site_technology_repository = (
            site_technology_repository or MssqlSiteTechnologyRepository()
        )
        self.site_technology_cache_repository = (
            site_technology_cache_repository or SiteTechnologyCacheRepository()
        )
        self.ne_nms_lookup_repository = ne_nms_lookup_repository or NeNmsLookupRepository()
        self.ne_nms_lookup_cache_repository = (
            ne_nms_lookup_cache_repository or NeNmsLookupCacheRepository()
        )
        self.site_ran_vendor_repository = site_ran_vendor_repository or SiteRanVendorRepository()
        self.site_ran_vendor_cache_repository = (
            site_ran_vendor_cache_repository or SiteRanVendorCacheRepository()
        )
        self.site_ran_name_repository = site_ran_name_repository or MssqlSiteRanNameRepository()
        self.site_ran_name_cache_repository = (
            site_ran_name_cache_repository or SiteRanNameCacheRepository()
        )
        self.counterparty_repository = counterparty_repository or CounterpartyRepository()
        self.counterparty_cache_repository = (
            counterparty_cache_repository or CounterpartyCacheRepository()
        )

    def sync(self):
        """Refresh the local Site cache from PostgreSQL. Returns the row
        count synced, or None on failure.

        Both steps below are wrapped in their own try/except and `return`
        on failure instead of raising — this runs inside an infinite
        background loop (see site_scheduler.py), so any uncaught exception
        here would silently kill that loop forever.
        """
        try:
            rows = self.site_repository.fetch_all()
        except Exception as e:
            logger.error(f"Postgres Site sync failed: {e}")
            return None

        normalized = [{c: row.get(c) for c in SiteCacheRepository.columns} for row in rows]
        try:
            self.cache_repository.replace_all(_TABLE, normalized)
        except Exception as e:
            logger.error(f"Site cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_TABLE}")
        return len(normalized)

    def sync_technology(self):
        """Refresh the local site technology inventory cache from MSSQL
        (TBL_NE). Returns the row count synced, or None on failure."""
        try:
            rows = self.site_technology_repository.fetch_all()
        except Exception as e:
            logger.error(f"MSSQL Site-technology sync failed: {e}")
            return None

        normalized = [
            {"site_code": row.get("Site Code"), "technology": row.get("Technology")} for row in rows
        ]
        try:
            self.site_technology_cache_repository.replace_all(_TECHNOLOGY_TABLE, normalized)
        except Exception as e:
            logger.error(f"Site-technology cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_TECHNOLOGY_TABLE}")
        return len(normalized)

    def sync_ran_name(self):
        """Refresh the local site -> RAN/SRAN baseband name cache from
        MSSQL (TBL_NE) — "RAN_NAME" on the Site Down 24h alert's
        multi-site Excel attachment. A site can have >1 NE row; first-seen
        per site_code wins (15 of ~3772 sites, confirmed live, carry 2
        distinct SRAN values for their NEs) — same dedup convention
        mssql_site_onair_sync_service.py's own sync() already uses for its
        own multi-NE-per-site edge case. Returns the row count synced, or
        None on failure."""
        try:
            rows = self.site_ran_name_repository.fetch_all()
        except Exception as e:
            logger.error(f"MSSQL Site-RAN-name sync failed: {e}")
            return None

        seen_site_codes = set()
        normalized = []
        for row in rows:
            code = row.get("Site Code")
            if not code or code in seen_site_codes:
                continue
            seen_site_codes.add(code)
            normalized.append({"site_code": code, "ran_name": row.get("RAN Name") or ""})
        try:
            self.site_ran_name_cache_repository.replace_all(_RAN_NAME_TABLE, normalized)
        except Exception as e:
            logger.error(f"Site-RAN-name cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_RAN_NAME_TABLE}")
        return len(normalized)

    def sync_ne_nms(self):
        """Refresh the local site -> NMS vendor code cache from object_227 —
        same retry_fetch() reasoning as sync_technology() above (object_227
        is confirmed prone to "conflict with recovery"). This replaces the
        `single_ne`/`sne` window function that used to be duplicated inside
        6 separate query files (incident_by_status.sql and friends) — those
        now just join against this one shared cache in Python instead.
        Returns the row count synced, or None on failure."""
        rows = retry_fetch(self.ne_nms_lookup_repository.fetch_all, "NE-NMS-lookup")
        if rows is None:
            return None

        normalized = [
            {"site_code": row.get("Site Code"), "nms_code": row.get("NMS Code")} for row in rows
        ]
        try:
            self.ne_nms_lookup_cache_repository.replace_all(_NE_NMS_LOOKUP_TABLE, normalized)
        except Exception as e:
            logger.error(f"NE-NMS-lookup cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_NE_NMS_LOOKUP_TABLE}")
        return len(normalized)

    def sync_ran_vendor(self):
        """Refresh the local site-level actual_ran_vendor cache from
        object_160 (see app/database/queries/site_ran_vendor.sql). Not
        object_227, so no retry_fetch() "conflict with recovery" concern
        here the way sync_technology()/sync_ne_nms() have. Returns the
        row count synced, or None on failure."""
        try:
            rows = self.site_ran_vendor_repository.fetch_all()
        except Exception as e:
            logger.error(f"Postgres Site-RAN-vendor sync failed: {e}")
            return None

        normalized = [
            {"site_code": row.get("Site Code"), "actual_ran_vendor": row.get("Actual RAN Vendor")}
            for row in rows
        ]
        try:
            self.site_ran_vendor_cache_repository.replace_all(_SITE_RAN_VENDOR_TABLE, normalized)
        except Exception as e:
            logger.error(f"Site-RAN-vendor cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_SITE_RAN_VENDOR_TABLE}")
        return len(normalized)

    def sync_counterparty(self):
        """Refresh the local Counterparty catalog cache from object_170
        (see app/database/queries/counterparty.sql) — small (127 rows),
        so a plain full replace like sync()/sync_ran_vendor() above, no
        retry_fetch() needed. Reference/lookup data only — nothing in
        this app currently treats it as authoritative for decoding
        site_ran_vendor_cache's actual_ran_vendor codes (see that
        query's header for why). Returns the row count synced, or None
        on failure."""
        try:
            rows = self.counterparty_repository.fetch_all()
        except Exception as e:
            logger.error(f"Postgres Counterparty sync failed: {e}")
            return None

        normalized = [{c: row.get(c) for c in CounterpartyCacheRepository.columns} for row in rows]
        try:
            self.counterparty_cache_repository.replace_all(_COUNTERPARTY_TABLE, normalized)
        except Exception as e:
            logger.error(f"Counterparty cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_COUNTERPARTY_TABLE}")
        return len(normalized)

