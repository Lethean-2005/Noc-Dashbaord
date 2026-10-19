"""Pulls Incident and INC-WO records from PostgreSQL into the local
cache (instance/localstorage.db). Mirrors site_sync_service.py.

9 tables synced here, all on incident_scheduler.py's schedule:
  - incident_by_status     — Incident drilldown, new/in_progress only.
  - incident_closed_trend  — Incidents closed in the last 30 days, one
                             row per incident — "Incidents Closed" card.
  - incident_created_trend — Incidents created in the last 30 days, any
                             status — "Incident Volume" card.
  - inc_wo_by_status       — INC-WO drilldown, not yet closed.
  - inc_wo_site_down       — inc_wo_by_status, category=site_down, not
                             resolved/closed — "INC-WO Site Down" card.
  - inc_wo_category_power  — inc_wo_by_status, category=power, not
                             resolved/closed — feeds the power Telegram
                             alert only.
  - inc_wo_resolved        — INC-WO Resolved while its Incident is still
                             In-Progress — "INC-WO Resolved" card.
  - incident_site_down     — Site Down incidents not Closed whose alarm
                             hasn't cleared — card + Telegram alert.
  - vip_incident_status    — same shape as incident_by_status, scoped to
                             VIP/VVIP + not-yet-Closed (keeps Resolved).

Only new/in_progress (Incident) and not-yet-closed (INC-WO) get synced;
vip_incident_status is the one deliberate exception.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.repositories.incident.incident_closed_trend_cache_repository import (
    IncidentClosedTrendCacheRepository,
)
from app.repositories.incident.incident_created_trend_cache_repository import (
    IncidentCreatedTrendCacheRepository,
)
from app.repositories.incident.incident_repository import IncidentRepository
from app.repositories.incident.incident_site_down_cache_repository import (
    IncidentSiteDownCacheRepository,
)
from app.repositories.incident.incident_site_down_duration_weekly_cache_repository import (
    IncidentSiteDownDurationWeeklyCacheRepository,
)
from app.repositories.incident.incident_duration_weekly_cache_repository import (
    IncidentDurationWeeklyCacheRepository,
)
from app.repositories.incident.incident_site_down_root_cause_cache_repository import (
    IncidentSiteDownRootCauseCacheRepository,
)
from app.repositories.incident.incident_resolution_time_weekly_cache_repository import (
    IncidentResolutionTimeWeeklyCacheRepository,
)
from app.repositories.incident.incident_resolution_time_details_cache_repository import (
    IncidentResolutionTimeDetailsCacheRepository,
)
from app.repositories.incident.incident_sla_compliance_weekly_cache_repository import (
    IncidentSlaComplianceWeeklyCacheRepository,
)
from app.repositories.incident.incident_sla_compliance_details_cache_repository import (
    IncidentSlaComplianceDetailsCacheRepository,
)
from app.repositories.incident.incident_response_time_weekly_cache_repository import (
    IncidentResponseTimeWeeklyCacheRepository,
)
from app.repositories.incident.incident_response_time_details_cache_repository import (
    IncidentResponseTimeDetailsCacheRepository,
)
from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository
from app.repositories.incwo.incwo_repository import IncWoRepository
from app.repositories.incwo.incwo_resolved_cache_repository import IncWoResolvedCacheRepository
from app.repositories.incwo.incwo_status_cache_repository import IncWoStatusCacheRepository
from app.repositories.site.mssql_site_onair_cache_repository import (
    MssqlSiteOnairCacheRepository,
)
from app.repositories.site.ne_nms_lookup_cache_repository import NeNmsLookupCacheRepository
from app.repositories.site.site_ran_vendor_cache_repository import SiteRanVendorCacheRepository
from app.repositories.vip.vip_incident_status_cache_repository import (
    VipIncidentStatusCacheRepository,
)
from app.repositories.vip.vip_site_cache_repository import VipSiteCacheRepository
from app.services.incident.incident_service import _WEEKS_AVAILABLE
from app.services.postgres_sync_utils import retry_fetch, to_local_seconds
from app.utils.logger import get_logger
from app.utils.nms import ACTUAL_RAN_VENDOR_TO_NMS_CODE, NMS_NAMES, resolve_nms_code_by_site

logger = get_logger(__name__)

_LOCAL_TZ = ZoneInfo("Asia/Phnom_Penh")


def _oldest_available_monday():
    """The Monday of the oldest week _available_weeks() (incident_
    service.py) can ever offer in a "Filter by Week"/"Compare Weeks"
    checkbox list — _WEEKS_AVAILABLE is imported (not copied) from
    there since it's a real number that changes, not a trivial leaf
    helper; duplicating its VALUE here is exactly the kind of drift
    _WEEKS_AVAILABLE's own docstring already warns about for
    _SERIES_COLORS. Used as the sync-side cutoff for any cache table
    whose rows need to cover every week that filter could select —
    see sync_site_down_duration_weekly()."""
    today = datetime.now(_LOCAL_TZ).date()
    this_monday = today - timedelta(days=today.weekday())
    return this_monday - timedelta(days=7 * (_WEEKS_AVAILABLE - 1))

_STATUS_TABLE = "incident_by_status"
_CLOSED_TREND_TABLE = "incident_closed_trend"
_CREATED_TREND_TABLE = "incident_created_trend"
_INC_WO_STATUS_TABLE = "inc_wo_by_status"
_INC_WO_SITE_DOWN_TABLE = "inc_wo_site_down"
_INC_WO_CATEGORY_POWER_TABLE = "inc_wo_category_power"
_INC_WO_RESOLVED_TABLE = "inc_wo_resolved"
_INCIDENT_SITE_DOWN_TABLE = "incident_site_down"
_SITE_DOWN_ROOT_CAUSE_TABLE = "incident_site_down_root_cause"
_SITE_DOWN_DURATION_WEEKLY_TABLE = "incident_site_down_duration_weekly"
_DURATION_WEEKLY_TABLE = "incident_duration_weekly"
_RESPONSE_TIME_WEEKLY_TABLE = "incident_response_time_weekly"
_RESPONSE_TIME_DETAILS_TABLE = "incident_response_time_details"
_RESOLUTION_TIME_WEEKLY_TABLE = "incident_resolution_time_weekly"
_RESOLUTION_TIME_DETAILS_TABLE = "incident_resolution_time_details"
_SLA_COMPLIANCE_WEEKLY_TABLE = "incident_sla_compliance_weekly"
_SLA_COMPLIANCE_DETAILS_TABLE = "incident_sla_compliance_details"
_VIP_INCIDENT_STATUS_TABLE = "vip_incident_status"
_NE_NMS_LOOKUP_TABLE = "ne_nms_lookup_cache"
_MSSQL_SITE_ONAIR_TABLE = "mssql_site_onair"
_SITE_RAN_VENDOR_TABLE = "site_ran_vendor_cache"

# object_322/324/160/227/162/308 are all subject to "conflict with
# recovery" (the replica's WAL-replay race) — every fetch below goes
# through retry_fetch(). Each sync_* method's cache write is wrapped in
# its own try/except (runs inside an infinite background loop; an
# uncaught exception would kill it).


class IncidentSyncService:
    def __init__(
        self,
        incident_repository=None,
        status_cache_repository=None,
        incwo_repository=None,
        incwo_status_cache_repository=None,
        incwo_resolved_cache_repository=None,
        incident_site_down_cache_repository=None,
        incident_site_down_root_cause_cache_repository=None,
        site_down_duration_weekly_cache_repository=None,
        duration_weekly_cache_repository=None,
        response_time_weekly_cache_repository=None,
        response_time_details_cache_repository=None,
        resolution_time_weekly_cache_repository=None,
        resolution_time_details_cache_repository=None,
        sla_compliance_weekly_cache_repository=None,
        sla_compliance_details_cache_repository=None,
        vip_incident_status_cache_repository=None,
        vip_site_cache_repository=None,
        ne_nms_lookup_cache_repository=None,
        site_ran_vendor_cache_repository=None,
        mssql_site_onair_cache_repository=None,
        closed_trend_cache_repository=None,
        created_trend_cache_repository=None,
    ):
        self.incident_repository = incident_repository or IncidentRepository()
        self.status_cache_repository = status_cache_repository or IncidentStatusCacheRepository()
        self.closed_trend_cache_repository = (
            closed_trend_cache_repository or IncidentClosedTrendCacheRepository()
        )
        self.created_trend_cache_repository = (
            created_trend_cache_repository or IncidentCreatedTrendCacheRepository()
        )
        self.incwo_repository = incwo_repository or IncWoRepository()
        self.incwo_status_cache_repository = (
            incwo_status_cache_repository or IncWoStatusCacheRepository()
        )
        self.incwo_resolved_cache_repository = (
            incwo_resolved_cache_repository or IncWoResolvedCacheRepository()
        )
        self.incident_site_down_cache_repository = (
            incident_site_down_cache_repository or IncidentSiteDownCacheRepository()
        )
        self.incident_site_down_root_cause_cache_repository = (
            incident_site_down_root_cause_cache_repository
            or IncidentSiteDownRootCauseCacheRepository()
        )
        self.site_down_duration_weekly_cache_repository = (
            site_down_duration_weekly_cache_repository or IncidentSiteDownDurationWeeklyCacheRepository()
        )
        self.duration_weekly_cache_repository = (
            duration_weekly_cache_repository or IncidentDurationWeeklyCacheRepository()
        )
        self.response_time_weekly_cache_repository = (
            response_time_weekly_cache_repository or IncidentResponseTimeWeeklyCacheRepository()
        )
        self.response_time_details_cache_repository = (
            response_time_details_cache_repository or IncidentResponseTimeDetailsCacheRepository()
        )
        self.resolution_time_weekly_cache_repository = (
            resolution_time_weekly_cache_repository or IncidentResolutionTimeWeeklyCacheRepository()
        )
        self.resolution_time_details_cache_repository = (
            resolution_time_details_cache_repository or IncidentResolutionTimeDetailsCacheRepository()
        )
        self.sla_compliance_weekly_cache_repository = (
            sla_compliance_weekly_cache_repository or IncidentSlaComplianceWeeklyCacheRepository()
        )
        self.sla_compliance_details_cache_repository = (
            sla_compliance_details_cache_repository or IncidentSlaComplianceDetailsCacheRepository()
        )
        self.vip_incident_status_cache_repository = (
            vip_incident_status_cache_repository or VipIncidentStatusCacheRepository()
        )
        self.vip_site_cache_repository = vip_site_cache_repository or VipSiteCacheRepository()
        self.ne_nms_lookup_cache_repository = (
            ne_nms_lookup_cache_repository or NeNmsLookupCacheRepository()
        )
        self.site_ran_vendor_cache_repository = (
            site_ran_vendor_cache_repository or SiteRanVendorCacheRepository()
        )
        self.mssql_site_onair_cache_repository = (
            mssql_site_onair_cache_repository or MssqlSiteOnairCacheRepository()
        )

    def _nms_by_site(self):
        """site_code -> raw NMS vendor code. Read fresh from cache on
        every call (both sources are tiny). Merge priority (confirmed
        actual_ran_vendor codes > NE-based fallback) lives in
        app/utils/nms.py's resolve_nms_code_by_site()."""
        ne_rows = self.ne_nms_lookup_cache_repository.fetch_all(_NE_NMS_LOOKUP_TABLE)
        vendor_rows = self.site_ran_vendor_cache_repository.fetch_all(_SITE_RAN_VENDOR_TABLE)
        return resolve_nms_code_by_site(ne_rows, vendor_rows)

    def _onair_vendor_by_site_code(self):
        """site_code -> real vendor name, straight from mssql_site_onair's
        own VENDOR column (MSSQL TBL_SITE/TBL_NE — real NE inventory, no
        code-guessing) — the same source map_view_service.py's On-Air
        sites already trust for their "nms" field. Only covers On-Air
        sites (that cache table's own scope); Incident Volume's "By
        Vendor" breakdown falls back to the actual_ran_vendor 3-code
        check (_resolve_vendor_name() below) for anything not in here —
        mainly incidents on Planned/Off-Air sites."""
        rows = self.mssql_site_onair_cache_repository.fetch_all(_MSSQL_SITE_ONAIR_TABLE)
        return {r["site_code"]: r["vendor"] for r in rows if r.get("site_code") and r.get("vendor")}

    @staticmethod
    def _is_newer(candidate, current):
        """True if candidate should replace current as the "latest" WO
        — same tie-break as `ORDER BY created_at DESC NULLS LAST`."""
        if current is None:
            return True
        new_created = candidate.get("INC-WO Created At")
        current_created = current.get("INC-WO Created At")
        if current_created is None and new_created is not None:
            return True
        return (
            new_created is not None
            and current_created is not None
            and new_created > current_created
        )

    def _latest_wo_by_incident_site(self, rows):
        """(incident numeric id, site numeric id) -> latest INC-WO row,
        fetched in one batched round-trip (inc_wo_by_incident_ids.sql).

        WO rows with no site are skipped for the (incident, site) keys
        — Python's `None == None` is true (unlike SQL NULL), so without
        this guard one WO could wrongly attach to every siteless row of
        a multi-site incident. "Other Site" incidents (no Site Numeric
        ID) are matched by incident id alone instead, only when
        unambiguous (confirmed against INC-0000122533/INC-0000118176)."""
        incident_ids = sorted(
            {r["Incident Numeric ID"] for r in rows if r.get("Incident Numeric ID") is not None}
        )
        wo_rows = retry_fetch(
            lambda: self.incident_repository.fetch_wo_by_incident_ids(incident_ids),
            "INC-WO-by-incident-ids",
        )
        if wo_rows is None:
            wo_rows = []

        latest = {}
        for wo in wo_rows:
            if wo.get("Site Numeric ID") is None:
                continue
            key = (wo.get("Incident Numeric ID"), wo.get("Site Numeric ID"))
            if self._is_newer(wo, latest.get(key)):
                latest[key] = wo

        incident_row_counts = {}
        for r in rows:
            iid = r.get("Incident Numeric ID")
            if iid is not None:
                incident_row_counts[iid] = incident_row_counts.get(iid, 0) + 1
        unambiguous_siteless_ids = {
            r["Incident Numeric ID"]
            for r in rows
            if r.get("Site Numeric ID") is None
            and r.get("Incident Numeric ID") is not None
            and incident_row_counts.get(r["Incident Numeric ID"]) == 1
        }
        latest_by_incident_only = {}
        for wo in wo_rows:
            if wo.get("Site Numeric ID") is not None:
                continue
            iid = wo.get("Incident Numeric ID")
            if iid not in unambiguous_siteless_ids:
                continue
            if self._is_newer(wo, latest_by_incident_only.get(iid)):
                latest_by_incident_only[iid] = wo
        for iid, wo in latest_by_incident_only.items():
            latest[(iid, None)] = wo

        return latest

    def sync_by_status(self):
        """Refresh incident_by_status from PostgreSQL."""
        rows = retry_fetch(self.incident_repository.fetch_by_status, "Incident-by-status")
        if rows is None:
            return None

        nms_by_site = self._nms_by_site()
        wo_by_key = self._latest_wo_by_incident_site(rows)
        normalized = [self._normalize_status_row(r, nms_by_site, wo_by_key) for r in rows]
        try:
            self.status_cache_repository.replace_all(_STATUS_TABLE, normalized)
        except Exception as e:
            logger.error(f"Incident-by-status cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_STATUS_TABLE}")
        return len(normalized)

    def sync_incident_closed_trend(self):
        """Refresh incident_closed_trend via two cheap queries instead
        of one join (same "conflict with recovery" reasoning as
        sync_incident_created_trend()).

        Step 1 reads object_322's own closed_at directly, not the work
        order's resolved_at — an earlier version used resolved_at and
        silently missed every Incident closed without a WO (57% of one
        day's closures had none). Step 2 batch-resolves
        category/site/location for those ids, deduping any multi-site
        fan-out to one row per Incident."""
        since = _oldest_available_monday()
        base_rows = retry_fetch(
            lambda: self.incident_repository.fetch_closed_trend(since), "Incident-closed-trend"
        )
        if base_rows is None:
            return None

        closed_at_by_numeric_id = {
            r.get("Incident Numeric ID"): r.get("Closed At")
            for r in base_rows
            if r.get("Incident Numeric ID") is not None
        }

        detail_rows = retry_fetch(
            lambda: self.incident_repository.fetch_closed_trend_by_ids(
                list(closed_at_by_numeric_id.keys())
            ),
            "Incident-closed-trend-by-ids",
        )
        if detail_rows is None:
            return None

        # Keep only the first row seen per Incident Numeric ID — the
        # site-text LATERAL can fan a multi-site Incident out to more
        # than one row, and incident_id is this table's PRIMARY KEY.
        first_row_by_numeric_id = {}
        for r in detail_rows:
            numeric_id = r.get("Incident Numeric ID")
            if numeric_id is not None and numeric_id not in first_row_by_numeric_id:
                first_row_by_numeric_id[numeric_id] = r

        normalized = [
            {
                "incident_id": r.get("Incident ID"),
                "incident_numeric_id": numeric_id,
                "closed_at": to_local_seconds(closed_at_by_numeric_id.get(numeric_id)),
                "incident_status": r.get("Incident Status") or "",
                "category": r.get("Category") or "",
                "site_name": r.get("Site Name") or "",
                "site_code": r.get("Site Code") or "",
                "province": r.get("Province") or "",
                "district": r.get("District") or "",
                "commune": r.get("Commune") or "",
            }
            for numeric_id, r in first_row_by_numeric_id.items()
            if r.get("Incident ID")
        ]
        try:
            self.closed_trend_cache_repository.replace_all(_CLOSED_TREND_TABLE, normalized)
        except Exception as e:
            logger.error(f"Incident-closed-trend cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_CLOSED_TREND_TABLE}")
        return len(normalized)

    @staticmethod
    def _resolve_vendor_name(site_code, actual_ran_vendor, onair_vendor_by_site_code):
        """An incident's real vendor name. Tier 1: mssql_site_onair's own
        VENDOR column keyed by site_code (see _onair_vendor_by_site_code()
        above) — real NE inventory data, covers the vast majority of
        incidents since most occur on live On-Air sites (confirmed
        against the local cache: only 6 of 3,751 On-Air sites have no
        vendor there). Tier 2 (site not in that table — Planned/Off-Air):
        the site's actual_ran_vendor code, but ONLY the 3 codes confirmed
        correct against Streamline's own data (see
        ACTUAL_RAN_VENDOR_TO_NMS_CODE's own header for how each was
        verified) — everything else, including a missing site/code
        entirely, shows "Unknown" rather than guessing at the rest."""
        onair_vendor = onair_vendor_by_site_code.get(site_code)
        if onair_vendor:
            return onair_vendor
        nms_code = ACTUAL_RAN_VENDOR_TO_NMS_CODE.get(actual_ran_vendor)
        return NMS_NAMES.get(nms_code, "Unknown") if nms_code else "Unknown"

    def sync_incident_created_trend(self):
        """Refresh incident_created_trend via two cheap queries — step 1
        is a plain filtered SELECT against object_322 alone, step 2
        batch-resolves detail for just those ids. Unlike
        sync_incident_closed_trend(), every id from step 1 is kept —
        Incident Volume counts every Incident created recently
        regardless of current status."""
        since = _oldest_available_monday()
        base_rows = retry_fetch(
            lambda: self.incident_repository.fetch_created_trend(since), "Incident-created-trend"
        )
        if base_rows is None:
            return None

        created_at_by_numeric_id = {
            r.get("Incident Numeric ID"): r.get("Created At")
            for r in base_rows
            if r.get("Incident Numeric ID") is not None
        }

        detail_rows = retry_fetch(
            lambda: self.incident_repository.fetch_created_trend_by_ids(
                list(created_at_by_numeric_id.keys())
            ),
            "Incident-created-trend-by-ids",
        )
        if detail_rows is None:
            return None

        # Keep only the first row seen per Incident Numeric ID — see
        # sync_incident_closed_trend()'s same dedup.
        first_row_by_numeric_id = {}
        for r in detail_rows:
            numeric_id = r.get("Incident Numeric ID")
            if numeric_id is not None and numeric_id not in first_row_by_numeric_id:
                first_row_by_numeric_id[numeric_id] = r

        onair_vendor_by_site_code = self._onair_vendor_by_site_code()
        normalized = [
            {
                "incident_id": r.get("Incident ID"),
                "incident_numeric_id": numeric_id,
                "created_at": to_local_seconds(created_at_by_numeric_id.get(numeric_id)),
                "incident_status": r.get("Incident Status") or "",
                "category": r.get("Category") or "",
                "severity": r.get("Severity") or "Unknown",
                "site_name": r.get("Site Name") or "",
                "site_code": r.get("Site Code") or "",
                "vendor": self._resolve_vendor_name(
                    r.get("Site Code"), r.get("Actual Ran Vendor"), onair_vendor_by_site_code
                ),
                "province": r.get("Province") or "",
                "district": r.get("District") or "",
                "commune": r.get("Commune") or "",
            }
            for numeric_id, r in first_row_by_numeric_id.items()
            if r.get("Incident ID")
        ]
        try:
            self.created_trend_cache_repository.replace_all(_CREATED_TREND_TABLE, normalized)
        except Exception as e:
            logger.error(f"Incident-created-trend cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_CREATED_TREND_TABLE}")
        return len(normalized)

    def sync_inc_wo_by_status(self):
        """Refresh inc_wo_by_status from PostgreSQL."""
        rows = retry_fetch(self.incwo_repository.fetch_by_status, "INC-WO-by-status")
        if rows is None:
            return None

        nms_by_site = self._nms_by_site()
        normalized = [self._normalize_incwo_row(r, nms_by_site) for r in rows]
        try:
            self.incwo_status_cache_repository.replace_all(_INC_WO_STATUS_TABLE, normalized)
        except Exception as e:
            logger.error(f"INC-WO-by-status cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_INC_WO_STATUS_TABLE}")
        return len(normalized)

    def sync_inc_wo_site_down(self):
        """Refresh inc_wo_site_down — same row shape as
        inc_wo_by_status, so _normalize_incwo_row() is reused as-is."""
        rows = retry_fetch(self.incwo_repository.fetch_site_down, "INC-WO-site-down")
        if rows is None:
            return None

        nms_by_site = self._nms_by_site()
        normalized = [self._normalize_incwo_row(r, nms_by_site) for r in rows]
        try:
            self.incwo_status_cache_repository.replace_all(_INC_WO_SITE_DOWN_TABLE, normalized)
        except Exception as e:
            logger.error(f"INC-WO-site-down cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_INC_WO_SITE_DOWN_TABLE}")
        return len(normalized)

    def sync_inc_wo_category_power(self):
        """Refresh inc_wo_category_power — same row shape as
        inc_wo_by_status/inc_wo_site_down. No dashboard card reads
        this; it only feeds telegram_inc_wo_power_alert.py."""
        rows = retry_fetch(self.incwo_repository.fetch_category_power, "INC-WO-category-power")
        if rows is None:
            return None

        nms_by_site = self._nms_by_site()
        normalized = [self._normalize_incwo_row(r, nms_by_site) for r in rows]
        try:
            self.incwo_status_cache_repository.replace_all(_INC_WO_CATEGORY_POWER_TABLE, normalized)
        except Exception as e:
            logger.error(f"INC-WO-category-power cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_INC_WO_CATEGORY_POWER_TABLE}")
        return len(normalized)

    def sync_inc_wo_resolved(self):
        """Refresh inc_wo_resolved from PostgreSQL."""
        rows = retry_fetch(self.incwo_repository.fetch_resolved, "INC-WO-resolved")
        if rows is None:
            return None

        nms_by_site = self._nms_by_site()
        normalized = [self._normalize_incwo_resolved_row(r, nms_by_site) for r in rows]
        try:
            self.incwo_resolved_cache_repository.replace_all(_INC_WO_RESOLVED_TABLE, normalized)
        except Exception as e:
            logger.error(f"INC-WO-resolved cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_INC_WO_RESOLVED_TABLE}")
        return len(normalized)

    def sync_incident_site_down(self):
        """Refresh incident_site_down — reuses fetch_site_down(), same
        query the Telegram alert shares."""
        rows = retry_fetch(self.incident_repository.fetch_site_down, "Incident-site-down")
        if rows is None:
            return None

        nms_by_site = self._nms_by_site()
        wo_by_key = self._latest_wo_by_incident_site(rows)
        normalized = [
            self._normalize_incident_site_down_row(r, nms_by_site, wo_by_key) for r in rows
        ]
        try:
            self.incident_site_down_cache_repository.replace_all(
                _INCIDENT_SITE_DOWN_TABLE, normalized
            )
        except Exception as e:
            logger.error(f"Incident-site-down cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_INCIDENT_SITE_DOWN_TABLE}")
        return len(normalized)

    def sync_site_down_root_cause(self):
        """Refresh incident_site_down_root_cause — per-incident Site
        Down detail for the last 30 days, with the real Root Cause
        Category Streamline assigns (see incident_site_down_root_cause.sql
        for the object_10 join). Filtered to incident_category ==
        'site_down' here in Python, not via SQL's WHERE — that one extra
        clause makes this exact query fail "conflict with recovery" on
        every single attempt, 6/6, confirmed live twice; the unfiltered
        fetch succeeds every time. "Times" (how many times this site has
        gone down in the window) is ranked here in Python too, not via
        SQL's ROW_NUMBER() — same "conflict with recovery" exposure.
        Rows are sorted by (site, occurred_at) first so the per-site
        counter below comes out in the same oldest-first order the old
        SQL ROW_NUMBER() produced."""
        since = _oldest_available_monday()
        rows = retry_fetch(
            lambda: self.incident_repository.fetch_site_down_root_cause(since),
            "Incident-site-down-root-cause",
        )
        if rows is None:
            return None

        filtered = [
            r for r in rows
            if r.get("Incident ID") and r.get("Incident Category") == "site_down"
        ]
        filtered.sort(key=lambda r: (r.get("Site") or "", r.get("Occurred At") or ""))
        site_counters = {}
        normalized = []
        for r in filtered:
            site = r.get("Site") or ""
            site_counters[site] = site_counters.get(site, 0) + 1
            normalized.append(
                {
                    "incident_id": r.get("Incident ID") or "",
                    "site": site,
                    "actual_root_cause": r.get("Actual Root Cause") or "",
                    "root_cause_category": r.get("Root Cause Category") or "None",
                    "times": site_counters[site],
                    "occurred_at": to_local_seconds(r.get("Occurred At")),
                }
            )
        try:
            self.incident_site_down_root_cause_cache_repository.replace_all(
                _SITE_DOWN_ROOT_CAUSE_TABLE, normalized
            )
        except Exception as e:
            logger.error(f"Incident-site-down-root-cause cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_SITE_DOWN_ROOT_CAUSE_TABLE}")
        return len(normalized)


    def sync_site_down_duration_weekly(self):
        """Refresh incident_site_down_duration_weekly via two cheap
        queries instead of one join (same "conflict with recovery"
        reasoning as sync_incident_closed_trend() — confirmed live that
        joining object_160/308 directly onto this step's ~5,500-row/
        30-day scan fails every time).

        Step 1 reads object_322 alone for occurred_at/resolved_at/
        closed_at. Step 2 batch-resolves Site Name/Code for those ids —
        UNLIKE sync_incident_closed_trend(), a multi-site incident's
        fan-out is kept (one row per site), not deduped to one row per
        incident — this card's drilldown is about which site(s) were
        actually down."""
        since = _oldest_available_monday()
        base_rows = retry_fetch(
            lambda: self.incident_repository.fetch_site_down_duration_weekly(since),
            "Incident-site-down-duration",
        )
        if base_rows is None:
            return None

        base_by_numeric_id = {
            r.get("Incident Numeric ID"): r
            for r in base_rows
            if r.get("Incident Numeric ID") is not None
        }

        site_rows = retry_fetch(
            lambda: self.incident_repository.fetch_site_down_duration_by_ids(
                list(base_by_numeric_id.keys())
            ),
            "Incident-site-down-duration-by-ids",
        )
        if site_rows is None:
            return None

        normalized = []
        for r in site_rows:
            numeric_id = r.get("Incident Numeric ID")
            base = base_by_numeric_id.get(numeric_id)
            if base is None or not base.get("Incident ID"):
                continue
            site_code = r.get("Site Code") or ""
            normalized.append({
                "incident_id": base["Incident ID"],
                "incident_numeric_id": numeric_id,
                "site": r.get("Site Name") or site_code,
                "site_code": site_code,
                "occurred_at": to_local_seconds(base.get("Occurred At")),
                "resolved_at": to_local_seconds(base.get("Resolved At")),
                "closed_at": to_local_seconds(base.get("Closed At")),
            })
        try:
            self.site_down_duration_weekly_cache_repository.replace_all(
                _SITE_DOWN_DURATION_WEEKLY_TABLE, normalized
            )
        except Exception as e:
            logger.error(f"Incident-site-down-duration cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_SITE_DOWN_DURATION_WEEKLY_TABLE}")
        return len(normalized)

    def sync_duration_weekly(self):
        """Refresh incident_duration_weekly — same two-step shape as
        sync_site_down_duration_weekly() (see that method's own
        docstring for why it's split this way), just every category
        instead of Site Down only. Step 2
        (fetch_site_down_duration_by_ids()) is reused unchanged — it was
        already generic, scoped only to a batch of ids, not to any one
        category."""
        since = _oldest_available_monday()
        base_rows = retry_fetch(
            lambda: self.incident_repository.fetch_duration_weekly(since), "Incident-duration"
        )
        if base_rows is None:
            return None

        base_by_numeric_id = {
            r.get("Incident Numeric ID"): r
            for r in base_rows
            if r.get("Incident Numeric ID") is not None
        }

        site_rows = retry_fetch(
            lambda: self.incident_repository.fetch_site_down_duration_by_ids(
                list(base_by_numeric_id.keys())
            ),
            "Incident-duration-by-ids",
        )
        if site_rows is None:
            return None

        # site_rows fans a multi-site incident out to one row per site
        # (see incident_site_down_duration_weekly_by_ids.sql's own
        # header — this step is reused from the Site-Down-specific
        # duration card, which deliberately wants one row per site).
        # This table counts INCIDENTS per category/weekday, not sites,
        # so keep only the first site seen per incident — same "keep
        # only the first row seen" dedup as sync_incident_closed_trend()/
        # sync_incident_created_trend() — otherwise a multi-site
        # incident gets counted 2-3x here, inflating a weekday's
        # duration-bucket totals above that same weekday's plain
        # "created" count (confirmed live: 1,535 Site-Down incidents
        # alone were double/triple-counted before this fix).
        first_site_row_by_incident = {}
        for r in site_rows:
            numeric_id = r.get("Incident Numeric ID")
            if numeric_id is not None and numeric_id not in first_site_row_by_incident:
                first_site_row_by_incident[numeric_id] = r

        normalized = []
        for numeric_id, r in first_site_row_by_incident.items():
            base = base_by_numeric_id.get(numeric_id)
            if base is None or not base.get("Incident ID"):
                continue
            site_code = r.get("Site Code") or ""
            normalized.append({
                "incident_id": base["Incident ID"],
                "incident_numeric_id": numeric_id,
                "category": base.get("Category") or "Uncategorized",
                "site": r.get("Site Name") or site_code,
                "site_code": site_code,
                "occurred_at": to_local_seconds(base.get("Occurred At")),
                "resolved_at": to_local_seconds(base.get("Resolved At")),
                "closed_at": to_local_seconds(base.get("Closed At")),
            })
        try:
            self.duration_weekly_cache_repository.replace_all(_DURATION_WEEKLY_TABLE, normalized)
        except Exception as e:
            logger.error(f"Incident-duration cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_DURATION_WEEKLY_TABLE}")
        return len(normalized)

    def sync_response_time_weekly(self):
        """Refresh incident_response_time_weekly — Response Time Week-
        over-Week (Performance page), real data straight from
        object_322 (take_in_progress_at - issue_occurred_at), no join
        — see incident_response_time_weekly.sql. ISO-week grouped,
        last 4 weeks; the most recent week is partial. Postgres
        returns min/avg/max as Decimal, which sqlite3 can't bind
        directly — cast to float before writing."""
        rows = retry_fetch(
            self.incident_repository.fetch_response_time_weekly, "Incident-response-time-weekly"
        )
        if rows is None:
            return None

        normalized = [
            {
                "iso_week": r.get("iso_week"),
                "category": r.get("category") or "Uncategorized",
                "incident_count": r.get("incident_count"),
                "min_minutes": float(r["min_minutes"]) if r.get("min_minutes") is not None else None,
                "avg_minutes": float(r["avg_minutes"]) if r.get("avg_minutes") is not None else None,
                "max_minutes": float(r["max_minutes"]) if r.get("max_minutes") is not None else None,
            }
            for r in rows
            if r.get("iso_week")
        ]
        try:
            self.response_time_weekly_cache_repository.replace_all(
                _RESPONSE_TIME_WEEKLY_TABLE, normalized
            )
        except Exception as e:
            logger.error(f"Incident-response-time-weekly cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_RESPONSE_TIME_WEEKLY_TABLE}")
        return len(normalized)

    def sync_response_time_details(self):
        """Refresh incident_response_time_details — per-incident rows
        behind Response Time's duration-bucket breakdown, same window/
        filter as sync_response_time_weekly() but one row per incident
        (no GROUP BY) — see incident_response_time_details.sql. Same
        Decimal-to-float cast as the weekly sync for sqlite3."""
        rows = retry_fetch(
            self.incident_repository.fetch_response_time_details, "Incident-response-time-details"
        )
        if rows is None:
            return None

        normalized = [
            {
                "incident_id": r.get("incident_id"),
                "incident_numeric_id": r.get("incident_numeric_id"),
                "iso_week": r.get("iso_week"),
                "category": r.get("category") or "Uncategorized",
                "occurred_at": to_local_seconds(r.get("occurred_at")),
                "took_in_progress_at": to_local_seconds(r.get("took_in_progress_at")),
                "response_minutes": (
                    float(r["response_minutes"]) if r.get("response_minutes") is not None else None
                ),
            }
            for r in rows
            if r.get("incident_id")
        ]
        try:
            self.response_time_details_cache_repository.replace_all(
                _RESPONSE_TIME_DETAILS_TABLE, normalized
            )
        except Exception as e:
            logger.error(f"Incident-response-time-details cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_RESPONSE_TIME_DETAILS_TABLE}")
        return len(normalized)

    def sync_resolution_time_weekly(self):
        """Refresh incident_resolution_time_weekly — Resolution Time
        Week-over-Week (Performance page), real data straight from
        object_322 (resolved_at - issue_occurred_at), no join — see
        incident_resolution_time_weekly.sql. Same shape as
        sync_response_time_weekly() above, same Decimal-to-float cast
        for sqlite3."""
        rows = retry_fetch(
            self.incident_repository.fetch_resolution_time_weekly,
            "Incident-resolution-time-weekly",
        )
        if rows is None:
            return None

        normalized = [
            {
                "iso_week": r.get("iso_week"),
                "category": r.get("category") or "Uncategorized",
                "incident_count": r.get("incident_count"),
                "min_minutes": float(r["min_minutes"]) if r.get("min_minutes") is not None else None,
                "avg_minutes": float(r["avg_minutes"]) if r.get("avg_minutes") is not None else None,
                "max_minutes": float(r["max_minutes"]) if r.get("max_minutes") is not None else None,
            }
            for r in rows
            if r.get("iso_week")
        ]
        try:
            self.resolution_time_weekly_cache_repository.replace_all(
                _RESOLUTION_TIME_WEEKLY_TABLE, normalized
            )
        except Exception as e:
            logger.error(f"Incident-resolution-time-weekly cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_RESOLUTION_TIME_WEEKLY_TABLE}")
        return len(normalized)

    def sync_resolution_time_details(self):
        """Refresh incident_resolution_time_details — per-incident rows
        behind Resolution Time's duration-bucket breakdown, same window/
        filter as sync_resolution_time_weekly() but one row per incident
        (no GROUP BY) — see incident_resolution_time_details.sql. Same
        Decimal-to-float cast as the weekly sync for sqlite3."""
        rows = retry_fetch(
            self.incident_repository.fetch_resolution_time_details, "Incident-resolution-time-details"
        )
        if rows is None:
            return None

        normalized = [
            {
                "incident_id": r.get("incident_id"),
                "incident_numeric_id": r.get("incident_numeric_id"),
                "iso_week": r.get("iso_week"),
                "category": r.get("category") or "Uncategorized",
                "occurred_at": to_local_seconds(r.get("occurred_at")),
                "resolved_at": to_local_seconds(r.get("resolved_at")),
                "resolution_minutes": (
                    float(r["resolution_minutes"]) if r.get("resolution_minutes") is not None else None
                ),
            }
            for r in rows
            if r.get("incident_id")
        ]
        try:
            self.resolution_time_details_cache_repository.replace_all(
                _RESOLUTION_TIME_DETAILS_TABLE, normalized
            )
        except Exception as e:
            logger.error(f"Incident-resolution-time-details cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_RESOLUTION_TIME_DETAILS_TABLE}")
        return len(normalized)

    def sync_sla_compliance_weekly(self):
        """Refresh incident_sla_compliance_weekly — SLA Compliance
        Weekly Trends (Performance page), real data straight from
        object_322 (overdue_response / overdue), no join — see
        incident_sla_compliance_weekly.sql. response_sla_pct/
        resolution_sla_pct are Postgres ROUND(...) results (Decimal),
        cast to float for sqlite3 same as the other two weekly caches."""
        rows = retry_fetch(
            self.incident_repository.fetch_sla_compliance_weekly, "Incident-sla-compliance-weekly"
        )
        if rows is None:
            return None

        normalized = [
            {
                "iso_week": r.get("iso_week"),
                "category": r.get("category") or "Uncategorized",
                "priority": r.get("priority") or "Unknown",
                "incident_count": r.get("incident_count"),
                "response_met_count": r.get("response_met_count"),
                "response_sla_pct": (
                    float(r["response_sla_pct"]) if r.get("response_sla_pct") is not None else None
                ),
                "resolution_known_count": r.get("resolution_known_count"),
                "resolution_met_count": r.get("resolution_met_count"),
                "resolution_sla_pct": (
                    float(r["resolution_sla_pct"])
                    if r.get("resolution_sla_pct") is not None
                    else None
                ),
            }
            for r in rows
            if r.get("iso_week")
        ]
        try:
            self.sla_compliance_weekly_cache_repository.replace_all(
                _SLA_COMPLIANCE_WEEKLY_TABLE, normalized
            )
        except Exception as e:
            logger.error(f"Incident-sla-compliance-weekly cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_SLA_COMPLIANCE_WEEKLY_TABLE}")
        return len(normalized)

    def sync_sla_compliance_details(self):
        """Refresh incident_sla_compliance_details — per-incident rows
        behind the SLA Compliance card's per-week popup AND its
        drilldown's "SLA" target column, same window/filter as
        sync_sla_compliance_weekly() but one row per incident (no
        GROUP BY) — see incident_sla_compliance_details.sql.

        incident_sla_compliance_details.sql joins Site (for site_grade)
        via the same site_text LATERAL as incident_by_status.sql, which
        fans a multi-site incident out to more than one row — deduped
        back to one row per incident_id below (this table's PRIMARY
        KEY), same "keep first row seen" pattern as
        sync_incident_closed_trend(). support_level comes straight off
        the Incident's own column (see that query's header for why —
        NOT the latest INC-WO, confirmed against Streamline's own UI
        that a dispatched WO doesn't change the incident's own SLA
        classification).

        overdue/overdue_response are Postgres booleans (True/False/None)
        cast to 1/0/None for sqlite3, same as every other boolean this
        app caches."""
        rows = retry_fetch(
            self.incident_repository.fetch_sla_compliance_details, "Incident-sla-compliance-details"
        )
        if rows is None:
            return None

        first_row_by_incident_id = {}
        for r in rows:
            iid = r.get("incident_id")
            if iid and iid not in first_row_by_incident_id:
                first_row_by_incident_id[iid] = r
        deduped = list(first_row_by_incident_id.values())

        def _bool_to_int(value):
            return None if value is None else int(bool(value))

        normalized = [
            {
                "incident_id": r.get("incident_id"),
                "incident_numeric_id": r.get("incident_numeric_id"),
                "iso_week": r.get("iso_week"),
                "category": r.get("category") or "Uncategorized",
                "priority": r.get("priority") or "Unknown",
                "support_level": r.get("support_level") or "",
                "site_grade": r.get("site_grade") or "",
                "occurred_at": to_local_seconds(r.get("occurred_at")),
                "overdue_response": _bool_to_int(r.get("overdue_response")),
                "overdue": _bool_to_int(r.get("overdue")),
            }
            for r in deduped
        ]
        try:
            self.sla_compliance_details_cache_repository.replace_all(
                _SLA_COMPLIANCE_DETAILS_TABLE, normalized
            )
        except Exception as e:
            logger.error(f"Incident-sla-compliance-details cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_SLA_COMPLIANCE_DETAILS_TABLE}")
        return len(normalized)

    def sync_vip_incident_status(self):
        """Refresh vip_incident_status — same row shape as
        incident_by_status, so _normalize_status_row() is reused as-is.

        Also widens the VIP/VVIP site scope to sites MSSQL's TBL_SITE.
        SITE_STRATEGIC flags (mssql_vip_site_codes, from vip_site_cache —
        see vip_incident_status.sql's own comment for why), on top of
        whichever sites Postgres's own site_strategic_type already
        flags. A stale/empty vip_site_cache (e.g. its own sync hasn't run
        yet) just means no extra sites get added this cycle — Postgres's
        own flag alone still works exactly as before."""
        mssql_vip_site_codes = [
            row["site_code"]
            for row in self.vip_site_cache_repository.fetch_all("vip_site_cache")
            if (row.get("site_strategic") or "").lower() in ("vip", "vvip")
        ]
        rows = retry_fetch(
            lambda: self.incident_repository.fetch_vip_incident_status(mssql_vip_site_codes),
            "VIP-incident-status",
        )
        if rows is None:
            return None

        nms_by_site = self._nms_by_site()
        wo_by_key = self._latest_wo_by_incident_site(rows)
        normalized = [self._normalize_status_row(r, nms_by_site, wo_by_key) for r in rows]
        try:
            self.vip_incident_status_cache_repository.replace_all(
                _VIP_INCIDENT_STATUS_TABLE, normalized
            )
        except Exception as e:
            logger.error(f"VIP-incident-status cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_VIP_INCIDENT_STATUS_TABLE}")
        return len(normalized)

    @staticmethod
    def _normalize_incident_site_down_row(row, nms_by_site, wo_by_key):
        """Maps incident_site_down.sql's column aliases onto the
        incident_site_down cache table's snake_case keys."""
        wo = wo_by_key.get((row.get("Incident Numeric ID"), row.get("Site Numeric ID"))) or {}
        return {
            "incident_id": row.get("Incident ID") or "",
            "incident_numeric_id": row.get("Incident Numeric ID"),
            "incident_status": row.get("Incident Status") or "",
            "wo_id": wo.get("INC-WO ID") or "",
            "wo_numeric_id": wo.get("INC-WO Numeric ID"),
            "wo_created_at": to_local_seconds(wo.get("INC-WO Created At")),
            "wo_status": wo.get("INC-WO Status") or "",
            "site_name": row.get("Site Name") or "",
            "site_code": row.get("Site Code") or "",
            "occurred_at": to_local_seconds(row.get("Occurred At")),
            "l1_noc_investigation_result": row.get("L1 NOC Investigation Result") or "",
            "last_comments": row.get("Last Comments") or "",
            "source": row.get("Source") or "",
            "nms": NMS_NAMES.get(str(nms_by_site.get(row.get("Site Code")) or "").strip(), ""),
            "hub_site": row.get("Hub Site") or "",
            "site_grade": row.get("Site Grade") or "",
            "province": row.get("Province") or "",
            "district": row.get("District") or "",
            "commune": row.get("Commune") or "",
        }

    @staticmethod
    def _normalize_incwo_resolved_row(row, nms_by_site):
        """Maps inc_wo_resolved.sql's column aliases onto the
        inc_wo_resolved cache table's snake_case keys — same shape as
        _normalize_incwo_row() plus incident_status."""
        return {
            "incident_id": row.get("Incident ID") or "",
            "incident_numeric_id": row.get("Incident Numeric ID"),
            "incident_status": row.get("Incident Status") or "",
            "wo_id": row.get("INC-WO ID"),
            "wo_numeric_id": row.get("INC-WO Numeric ID"),
            "wo_created_at": to_local_seconds(row.get("INC-WO Created At")),
            "wo_status": row.get("INC-WO Status") or "",
            "resolved_at": to_local_seconds(row.get("Resolved At")),
            "responsible_team": row.get("Responsible Team") or "",
            "site_name": row.get("Site Name") or "",
            "site_code": row.get("Site Code") or "",
            "overdue": row.get("overdue") or "",
            "support_level": row.get("Support Level") or "",
            "fault_description": row.get("Fault Description") or "",
            "nms": NMS_NAMES.get(str(nms_by_site.get(row.get("Site Code")) or "").strip(), ""),
            "hub_site": row.get("Hub Site") or "",
            "site_grade": row.get("Site Grade") or "",
            "province": row.get("Province") or "",
            "district": row.get("District") or "",
            "commune": row.get("Commune") or "",
        }

    @staticmethod
    def _site_name_with_fallback(row):
        """An "Other Site" WO has no Site Name — label it with Site
        Code instead of leaving it blank."""
        site_name = row.get("Site Name") or ""
        if site_name:
            return site_name
        site_code = row.get("Site Code") or ""
        return f"Other Site ({site_code})" if site_code else "Other Site"

    @staticmethod
    def _normalize_incwo_row(row, nms_by_site):
        """Maps inc_wo_by_status.sql's column aliases onto the
        inc_wo_by_status cache table's snake_case keys.

        wo_id is left as raw None when absent — a fresh 'new' WO has no
        wo_id yet, and several such rows can exist at once; SQLite
        allows multiple real NULLs in a PRIMARY KEY column, so this is
        safe as long as callers handle wo_id possibly being None."""
        return {
            "incident_id": row.get("Incident ID") or "",
            "incident_numeric_id": row.get("Incident Numeric ID"),
            "incident_status": row.get("Incident Status") or "",
            "wo_id": row.get("INC-WO ID"),
            "wo_numeric_id": row.get("INC-WO Numeric ID"),
            "wo_created_at": to_local_seconds(row.get("INC-WO Created At")),
            "wo_status": row.get("INC-WO Status") or "",
            "resolved_at": to_local_seconds(row.get("Resolved At")),
            "incident_category": row.get("Incident Category") or "",
            "site_name": IncidentSyncService._site_name_with_fallback(row),
            "site_code": row.get("Site Code") or "",
            "overdue": row.get("overdue") or "",
            "support_level": row.get("Support Level") or "",
            "responsible_team": row.get("Responsible Team") or "",
            "fault_description": row.get("Fault Description") or "",
            "nms": NMS_NAMES.get(str(nms_by_site.get(row.get("Site Code")) or "").strip(), ""),
            "hub_site": row.get("Hub Site") or "",
            "site_grade": row.get("Site Grade") or "",
            "province": row.get("Province") or "",
            "district": row.get("District") or "",
            "commune": row.get("Commune") or "",
        }

    @staticmethod
    def _normalize_status_row(row, nms_by_site, wo_by_key):
        """Maps incident_by_status.sql's column aliases onto the
        incident_by_status cache table's snake_case keys."""
        wo = wo_by_key.get((row.get("Incident Numeric ID"), row.get("Site Numeric ID"))) or {}
        return {
            "incident_id": row.get("Incident ID") or "",
            "incident_numeric_id": row.get("Incident Numeric ID"),
            "incident_status": row.get("Incident Status") or "",
            "wo_id": wo.get("INC-WO ID") or "",
            "wo_numeric_id": wo.get("INC-WO Numeric ID"),
            "wo_created_at": to_local_seconds(wo.get("INC-WO Created At")),
            "wo_status": wo.get("INC-WO Status") or "",
            "resolved_at": to_local_seconds(wo.get("Resolved At")),
            "responsible_team": wo.get("Responsible Team") or "",
            "support_level": wo.get("Support Level") or "",
            "site_name": row.get("Site Name") or "",
            "site_code": row.get("Site Code") or "",
            "occurred_at": to_local_seconds(row.get("Occurred At")),
            "overdue": row.get("overdue") or "",
            "category": row.get("category") or "",
            "l1_noc_investigation_result": row.get("L1 NOC Investigation Result") or "",
            "nms": NMS_NAMES.get(str(nms_by_site.get(row.get("Site Code")) or "").strip(), ""),
            "hub_site": row.get("Hub Site") or "",
            "site_grade": row.get("Site Grade") or "",
            "province": row.get("Province") or "",
            "district": row.get("District") or "",
            "commune": row.get("Commune") or "",
        }
