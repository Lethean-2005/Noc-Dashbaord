"""Pulls Incident and INC-WO records from PostgreSQL and writes them into
the local cache (instance/localstorage.db). Mirrors the Site sync in
app/services/site/site_sync_service.py — same reasoning applies here.

Four separate tables get synced here, all on the same schedule
(app/services/incident/incident_scheduler.py calls each tick):
  - incident_by_status    — joined Incident drilldown detail (Site/INC-WO/NMS/...),
                            only 'new'/'in_progress' incidents, used by the
                            drilldown page behind every Incident badge.
  - inc_wo_by_status      — joined INC-WO drilldown detail (Site/Incident/NMS/...),
                            every INC-WO not yet 'closed', used by the
                            drilldown page behind every INC-WO badge.
  - inc_wo_site_down      — same join as inc_wo_by_status, narrowed to
                            category='site_down' work orders not yet
                            resolved/closed — behind the "INC-WO Site Down"
                            card on the Custom Dashboard (reports/index.html).
  - inc_wo_resolved       — INC-WO that are Resolved while their parent
                            Incident is still In-Progress overall — behind
                            the "INC-WO Resolved" card on the Custom Dashboard.
  - incident_site_down    — Site Down incidents not yet Closed whose alarm
                            hasn't cleared (same filter/join as
                            incident_site_down.sql, shared with the Telegram alert)
                            — behind the "Incident Site Down" card on the
                            Custom Dashboard.
  - vip_incident_status   — same shape as incident_by_status, but scoped to
                            only VIP/VVIP sites and not-yet-Closed (so
                            Resolved stays) — used only by VipAlarmService's
                            enrichment. Kept separate from incident_by_status
                            itself since that one's shared by IncidentService
                            and MentorSiteService, both of which need
                            Resolved excluded — see
                            app/database/queries/vip_incident_status.sql.

Only 'new'/'in_progress' (Incident) and not-yet-'closed' (INC-WO) get
synced — resolved/closed records aren't shown on any badge, so there's no
reason to cache them. vip_incident_status is the one deliberate exception,
scoped narrowly enough (33 of 4,360 sites) to safely include Resolved.
"""

from app.repositories.incident.incident_repository import IncidentRepository
from app.repositories.incident.incident_site_down_cache_repository import (
    IncidentSiteDownCacheRepository,
)
from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository
from app.repositories.incwo.incwo_repository import IncWoRepository
from app.repositories.incwo.incwo_resolved_cache_repository import IncWoResolvedCacheRepository
from app.repositories.incwo.incwo_status_cache_repository import IncWoStatusCacheRepository
from app.repositories.site.ne_nms_lookup_cache_repository import NeNmsLookupCacheRepository
from app.repositories.vip.vip_incident_status_cache_repository import (
    VipIncidentStatusCacheRepository,
)
from app.services.postgres_sync_utils import retry_fetch, to_local_seconds
from app.utils.logger import get_logger
from app.utils.nms import NMS_NAMES

logger = get_logger(__name__)

_STATUS_TABLE = "incident_by_status"
_INC_WO_STATUS_TABLE = "inc_wo_by_status"
_INC_WO_SITE_DOWN_TABLE = "inc_wo_site_down"
_INC_WO_RESOLVED_TABLE = "inc_wo_resolved"
_INCIDENT_SITE_DOWN_TABLE = "incident_site_down"
_VIP_INCIDENT_STATUS_TABLE = "vip_incident_status"
_NE_NMS_LOOKUP_TABLE = "ne_nms_lookup_cache"

# object_322/324/160/227/162/308 are all confirmed foreign tables subject
# to "conflict with recovery" (the replica's WAL-replay race). Every fetch
# below goes through retry_fetch() (app/services/postgres_sync_utils.py),
# shared with ape_alarm/vip_alarm_sync_service.py.


class IncidentSyncService:
    def __init__(
        self,
        incident_repository=None,
        status_cache_repository=None,
        incwo_repository=None,
        incwo_status_cache_repository=None,
        incwo_resolved_cache_repository=None,
        incident_site_down_cache_repository=None,
        vip_incident_status_cache_repository=None,
        ne_nms_lookup_cache_repository=None,
    ):
        self.incident_repository = incident_repository or IncidentRepository()
        self.status_cache_repository = status_cache_repository or IncidentStatusCacheRepository()
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
        self.vip_incident_status_cache_repository = (
            vip_incident_status_cache_repository or VipIncidentStatusCacheRepository()
        )
        self.ne_nms_lookup_cache_repository = (
            ne_nms_lookup_cache_repository or NeNmsLookupCacheRepository()
        )

    def _nms_by_site(self):
        """site_code -> raw NMS vendor code, read from the local
        ne_nms_lookup_cache (synced independently by SiteSyncService.
        sync_ne_nms() — see app/database/queries/ne_nms_lookup.sql). Read
        fresh on every call rather than cached on `self`: this table is
        tiny (one row per site with an NE), and re-reading it keeps this
        service from ever holding a stale copy across sync ticks."""
        rows = self.ne_nms_lookup_cache_repository.fetch_all(_NE_NMS_LOOKUP_TABLE)
        return {r["site_code"]: r["nms_code"] for r in rows}

    @staticmethod
    def _is_newer(candidate, current):
        """True if candidate should replace current as the "latest" WO —
        same tie-break as SQL's `ORDER BY created_at DESC NULLS LAST LIMIT
        1` (a WO with no created_at never beats one that has one)."""
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
        """(incident numeric id, site numeric id) -> latest INC-WO row, for
        the given batch of already-fetched incident/site rows. Fetches
        every candidate WO in one batched round-trip (see
        app/database/queries/inc_wo_by_incident_ids.sql) instead of one
        Postgres round-trip per row.

        WO rows with no site (Site Numeric ID is None) are skipped for the
        (incident, site) keys: in SQL, `NULL = NULL` is never true, so a
        siteless WO should never match a siteless row purely by site.
        Python's `None == None` IS true, so without this guard a dict
        keyed by (incident_id, None) would wrongly attach one WO to every
        siteless row of the SAME incident when that incident has more than
        one (e.g. a multi-site incident where several sites don't resolve)
        — there'd be no way to tell which row it actually belongs to.

        "Other Site" fallback: an incident whose site isn't in the
        registered Site list (see incident_by_status.sql's COALESCE note)
        has no Site Numeric ID at all, so it can never get a WO via the
        (incident, site) key above even when the match is otherwise
        unambiguous. Confirmed live against the original bug case
        (INC-0000122533/INC-0000118176, both "Other Site" incidents) that
        the (incident, site) guard above was A DIFFERENT incident_numeric_id
        each — the key already can't cross-match between them, since
        object_324.parent_incident is a direct FK to the incident's own
        numeric id, not derived from site at all. Site only matters here as
        a disambiguator for incidents that fan out to MORE THAN ONE row
        (multi-site incidents); an incident that's a single row in this
        batch has nothing to disambiguate, so its WO(s) can be matched by
        incident id alone, still keeping the same siteless-WO-only-if-the-
        incident-is-also-siteless restriction (a site-having WO still only
        ever matches via the exact (incident, site) key)."""
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
        """Refresh the local incident_by_status cache from PostgreSQL.

        The fetch retries on failure (see retry_fetch()); the cache write
        below is still wrapped in its own try/except and `return` on
        failure instead of raising — this runs inside an infinite
        background loop (see incident_scheduler.py), so any uncaught
        exception here would silently kill that loop forever.
        """
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

    def sync_inc_wo_by_status(self):
        """Refresh the local inc_wo_by_status cache from PostgreSQL. Same
        retry-then-try/except reasoning as sync_by_status() above."""
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
        """Refresh the local inc_wo_site_down cache from PostgreSQL — same
        row shape as inc_wo_by_status, so _normalize_incwo_row() is reused
        as-is. Same retry-then-try/except reasoning as sync_by_status() above."""
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

    def sync_inc_wo_resolved(self):
        """Refresh the local inc_wo_resolved cache from PostgreSQL. Same
        retry-then-try/except reasoning as sync_by_status() above."""
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
        """Refresh the local incident_site_down cache from PostgreSQL.
        Reuses fetch_site_down() — same query, same correct filter
        (Site Down, not Closed, alarm not cleared) shared with the Telegram
        alert. Same retry-then-try/except reasoning as sync_by_status() above."""
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

    def sync_vip_incident_status(self):
        """Refresh the local vip_incident_status cache from PostgreSQL —
        same row shape as incident_by_status, so _normalize_status_row() is
        reused as-is. Same retry-then-try/except reasoning as
        sync_by_status() above."""
        rows = retry_fetch(
            self.incident_repository.fetch_vip_incident_status, "VIP-incident-status"
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
        """Maps incident_site_down.sql's quoted, mixed-case column aliases onto
        clean snake_case keys matching the incident_site_down cache
        table. nms_by_site (site_code -> raw NMS code) comes from the local
        ne_nms_lookup_cache — see _nms_by_site(). wo_by_key ((incident
        numeric id, site numeric id) -> latest INC-WO row) comes from
        _latest_wo_by_incident_site()."""
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
            "nms": NMS_NAMES.get(str(nms_by_site.get(row.get("Site Code")) or "").strip(), ""),
            "hub_site": row.get("Hub Site") or "",
            "site_grade": row.get("Site Grade") or "",
            "province": row.get("Province") or "",
            "district": row.get("District") or "",
            "commune": row.get("Commune") or "",
        }

    @staticmethod
    def _normalize_incwo_resolved_row(row, nms_by_site):
        """Maps inc_wo_resolved.sql's quoted, mixed-case column aliases onto
        clean snake_case keys matching the inc_wo_resolved cache table —
        same shape as _normalize_incwo_row() plus incident_status.
        nms_by_site (site_code -> raw NMS code) comes from the local
        ne_nms_lookup_cache — see _nms_by_site()."""
        return {
            "incident_id": row.get("Incident ID") or "",
            "incident_numeric_id": row.get("Incident Numeric ID"),
            "incident_status": row.get("Incident Status") or "",
            "wo_id": row.get("INC-WO ID"),
            "wo_numeric_id": row.get("INC-WO Numeric ID"),
            "wo_created_at": to_local_seconds(row.get("INC-WO Created At")),
            "wo_status": row.get("INC-WO Status") or "",
            "resolved_at": to_local_seconds(row.get("Resolved At")),
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
    def _normalize_incwo_row(row, nms_by_site):
        """Maps inc_wo_by_status.sql's quoted, mixed-case column aliases onto
        clean snake_case keys matching the inc_wo_by_status cache table.
        nms_by_site (site_code -> raw NMS code) comes from the local
        ne_nms_lookup_cache — see _nms_by_site().

        wo_id (the primary key) is left as raw None when absent — a fresh
        'new' work order has no wo_id yet, and several such rows exist at
        once, so normalizing to "" here would collide multiple rows onto
        the same primary-key value. SQLite allows multiple real NULLs in a
        PRIMARY KEY column (unlike some other databases), so this is safe;
        it just means callers must handle wo_id possibly being None when
        reading it back (see IncWoService.get_details())."""
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
    def _normalize_status_row(row, nms_by_site, wo_by_key):
        """Maps incident_by_status.sql's quoted, mixed-case column aliases
        (e.g. "Incident ID", "Site Numeric ID") onto clean snake_case keys
        matching the incident_by_status cache table. nms_by_site (site_code
        -> raw NMS code) comes from the local ne_nms_lookup_cache — see
        _nms_by_site(). wo_by_key ((incident numeric id, site numeric id)
        -> latest INC-WO row) comes from _latest_wo_by_incident_site()."""
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
