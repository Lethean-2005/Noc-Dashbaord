"""Pulls Incident and INC-WO records from PostgreSQL and writes them into
the local cache (instance/localstorage.db). Mirrors the Site sync in
app/services/site_sync_service.py — same reasoning applies here.

Four separate tables get synced here, all on the same schedule
(app/services/incident_scheduler.py calls each tick):
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
  - vip_customer_complaint — every new, not-yet-worked customer complaint
                            raised by a VIP customer.
  - incident_site_down    — Site Down incidents not yet Closed whose alarm
                            hasn't cleared (same filter/join as
                            site_down.sql, shared with the Telegram alert)
                            — behind the "Incident Site Down" card on the
                            Custom Dashboard.

Only 'new'/'in_progress' (Incident) and not-yet-'closed' (INC-WO) get
synced — resolved/closed records aren't shown on any badge, so there's no
reason to cache them.
"""
from app.repositories.incident_repository import IncidentRepository
from app.repositories.incident_site_down_cache_repository import IncidentSiteDownCacheRepository
from app.repositories.incident_status_cache_repository import IncidentStatusCacheRepository
from app.repositories.incwo_repository import IncWoRepository
from app.repositories.incwo_resolved_cache_repository import IncWoResolvedCacheRepository
from app.repositories.incwo_status_cache_repository import IncWoStatusCacheRepository
from app.repositories.vip_customer_complaint_cache_repository import VipCustomerComplaintCacheRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

_STATUS_TABLE = "incident_by_status"
_INC_WO_STATUS_TABLE = "inc_wo_by_status"
_INC_WO_SITE_DOWN_TABLE = "inc_wo_site_down"
_INC_WO_RESOLVED_TABLE = "inc_wo_resolved"
_VIP_CUSTOMER_COMPLAINT_TABLE = "vip_customer_complaint"
_INCIDENT_SITE_DOWN_TABLE = "incident_site_down"


def _to_seconds(value):
    """'YYYY-MM-DD HH:MM:SS[.ffffff]' -> 'YYYY-MM-DD HH:MM:SS'. Postgres
    timestamps only show microseconds via str() when they're non-zero, so
    without this, INC-WO Created At (which has sub-second precision) and
    Occurred At (which usually doesn't) render inconsistently side by side."""
    return str(value)[:19] if value else ""


class IncidentSyncService:
    def __init__(self, incident_repository=None, status_cache_repository=None,
                 incwo_repository=None, incwo_status_cache_repository=None,
                 incwo_resolved_cache_repository=None, vip_customer_complaint_cache_repository=None,
                 incident_site_down_cache_repository=None):
        self.incident_repository = incident_repository or IncidentRepository()
        self.status_cache_repository = status_cache_repository or IncidentStatusCacheRepository()
        self.incwo_repository = incwo_repository or IncWoRepository()
        self.incwo_status_cache_repository = incwo_status_cache_repository or IncWoStatusCacheRepository()
        self.incwo_resolved_cache_repository = incwo_resolved_cache_repository or IncWoResolvedCacheRepository()
        self.vip_customer_complaint_cache_repository = (
            vip_customer_complaint_cache_repository or VipCustomerComplaintCacheRepository()
        )
        self.incident_site_down_cache_repository = (
            incident_site_down_cache_repository or IncidentSiteDownCacheRepository()
        )

    def sync_by_status(self):
        """Refresh the local incident_by_status cache from PostgreSQL.

        Both steps below are wrapped in their own try/except and `return`
        on failure instead of raising — this runs inside an infinite
        background loop (see incident_scheduler.py), so any uncaught
        exception here would silently kill that loop forever.
        """
        try:
            rows = self.incident_repository.fetch_by_status()
        except Exception as e:
            logger.error(f"Postgres Incident-by-status sync failed: {e}")
            return

        normalized = [self._normalize_status_row(r) for r in rows]
        try:
            self.status_cache_repository.replace_all(_STATUS_TABLE, normalized)
        except Exception as e:
            logger.error(f"Incident-by-status cache write failed: {e}")
            return
        logger.info(f"Synced {len(normalized)} row(s) into {_STATUS_TABLE}")

    def sync_inc_wo_by_status(self):
        """Refresh the local inc_wo_by_status cache from PostgreSQL. Same
        try/except-per-step reasoning as sync_by_status() above."""
        try:
            rows = self.incwo_repository.fetch_by_status()
        except Exception as e:
            logger.error(f"Postgres INC-WO-by-status sync failed: {e}")
            return

        normalized = [self._normalize_incwo_row(r) for r in rows]
        try:
            self.incwo_status_cache_repository.replace_all(_INC_WO_STATUS_TABLE, normalized)
        except Exception as e:
            logger.error(f"INC-WO-by-status cache write failed: {e}")
            return
        logger.info(f"Synced {len(normalized)} row(s) into {_INC_WO_STATUS_TABLE}")

    def sync_inc_wo_site_down(self):
        """Refresh the local inc_wo_site_down cache from PostgreSQL — same
        row shape as inc_wo_by_status, so _normalize_incwo_row() is reused
        as-is. Same try/except-per-step reasoning as sync_by_status() above."""
        try:
            rows = self.incwo_repository.fetch_site_down()
        except Exception as e:
            logger.error(f"Postgres INC-WO-site-down sync failed: {e}")
            return

        normalized = [self._normalize_incwo_row(r) for r in rows]
        try:
            self.incwo_status_cache_repository.replace_all(_INC_WO_SITE_DOWN_TABLE, normalized)
        except Exception as e:
            logger.error(f"INC-WO-site-down cache write failed: {e}")
            return
        logger.info(f"Synced {len(normalized)} row(s) into {_INC_WO_SITE_DOWN_TABLE}")

    def sync_inc_wo_resolved(self):
        """Refresh the local inc_wo_resolved cache from PostgreSQL. Same
        try/except-per-step reasoning as sync_by_status() above."""
        try:
            rows = self.incwo_repository.fetch_resolved()
        except Exception as e:
            logger.error(f"Postgres INC-WO-resolved sync failed: {e}")
            return

        normalized = [self._normalize_incwo_resolved_row(r) for r in rows]
        try:
            self.incwo_resolved_cache_repository.replace_all(_INC_WO_RESOLVED_TABLE, normalized)
        except Exception as e:
            logger.error(f"INC-WO-resolved cache write failed: {e}")
            return
        logger.info(f"Synced {len(normalized)} row(s) into {_INC_WO_RESOLVED_TABLE}")

    def sync_vip_customer_complaint(self):
        """Refresh the local vip_customer_complaint cache from PostgreSQL.
        Same try/except-per-step reasoning as sync_by_status() above."""
        try:
            rows = self.incident_repository.fetch_vip_customer_complaint()
        except Exception as e:
            logger.error(f"Postgres VIP-customer-complaint sync failed: {e}")
            return

        normalized = [self._normalize_vip_customer_complaint_row(r) for r in rows]
        try:
            self.vip_customer_complaint_cache_repository.replace_all(
                _VIP_CUSTOMER_COMPLAINT_TABLE, normalized
            )
        except Exception as e:
            logger.error(f"VIP-customer-complaint cache write failed: {e}")
            return
        logger.info(f"Synced {len(normalized)} row(s) into {_VIP_CUSTOMER_COMPLAINT_TABLE}")

    def sync_incident_site_down(self):
        """Refresh the local incident_site_down cache from PostgreSQL.
        Reuses fetch_site_down() — same query, same correct filter
        (Site Down, not Closed, alarm not cleared) shared with the Telegram
        alert. Same try/except-per-step reasoning as sync_by_status() above."""
        try:
            rows = self.incident_repository.fetch_site_down()
        except Exception as e:
            logger.error(f"Postgres Incident-site-down sync failed: {e}")
            return

        normalized = [self._normalize_incident_site_down_row(r) for r in rows]
        try:
            self.incident_site_down_cache_repository.replace_all(_INCIDENT_SITE_DOWN_TABLE, normalized)
        except Exception as e:
            logger.error(f"Incident-site-down cache write failed: {e}")
            return
        logger.info(f"Synced {len(normalized)} row(s) into {_INCIDENT_SITE_DOWN_TABLE}")

    @staticmethod
    def _normalize_incident_site_down_row(row):
        """Maps site_down.sql's quoted, mixed-case column aliases onto
        clean snake_case keys matching the incident_site_down cache
        table."""
        return {
            "incident_id": row.get("Incident ID") or "",
            "incident_status": row.get("Incident Status") or "",
            "wo_id": row.get("INC-WO ID") or "",
            "wo_created_at": _to_seconds(row.get("INC-WO Created At")),
            "wo_status": row.get("INC-WO Status") or "",
            "site_name": row.get("Site Name") or "",
            "site_code": row.get("Site Code") or "",
            "occurred_at": _to_seconds(row.get("Occurred At")),
            "l1_noc_investigation_result": row.get("L1 NOC Investigation Result") or "",
            "nms": row.get("NMS") or "",
            "hub_site": row.get("Hub Site") or "",
            "site_grade": row.get("Site Grade") or "",
            "province": row.get("Province") or "",
            "district": row.get("District") or "",
            "commune": row.get("Commune") or "",
        }

    @staticmethod
    def _normalize_vip_customer_complaint_row(row):
        """Maps vip_customer_complaint.sql's quoted, mixed-case column
        aliases onto clean snake_case keys matching the
        vip_customer_complaint cache table."""
        return {
            "incident_id": row.get("Incident ID") or "",
            "customer_address": row.get("Customer Address") or "",
            "customer_phone_no": row.get("Customer Phone No") or "",
            "problem_experienced_at": _to_seconds(row.get("Problem Experienced At")),
            "fault_description": row.get("Fault Description") or "",
        }

    @staticmethod
    def _normalize_incwo_resolved_row(row):
        """Maps incwo_resolved.sql's quoted, mixed-case column aliases onto
        clean snake_case keys matching the inc_wo_resolved cache table —
        same shape as _normalize_incwo_row() plus incident_status."""
        return {
            "incident_id": row.get("Incident ID") or "",
            "incident_status": row.get("Incident Status") or "",
            "wo_id": row.get("INC-WO ID"),
            "wo_created_at": _to_seconds(row.get("INC-WO Created At")),
            "wo_status": row.get("INC-WO Status") or "",
            "site_name": row.get("Site Name") or "",
            "site_code": row.get("Site Code") or "",
            "overdue": row.get("overdue") or "",
            "support_level": row.get("Support Level") or "",
            "fault_description": row.get("Fault Description") or "",
            "nms": row.get("NMS") or "",
            "hub_site": row.get("Hub Site") or "",
            "site_grade": row.get("Site Grade") or "",
            "province": row.get("Province") or "",
            "district": row.get("District") or "",
            "commune": row.get("Commune") or "",
        }

    @staticmethod
    def _normalize_incwo_row(row):
        """Maps incwo_by_status.sql's quoted, mixed-case column aliases onto
        clean snake_case keys matching the inc_wo_by_status cache table.

        wo_id (the primary key) is left as raw None when absent — a fresh
        'new' work order has no wo_id yet, and several such rows exist at
        once, so normalizing to "" here would collide multiple rows onto
        the same primary-key value. SQLite allows multiple real NULLs in a
        PRIMARY KEY column (unlike some other databases), so this is safe;
        it just means callers must handle wo_id possibly being None when
        reading it back (see IncWoService.get_details())."""
        return {
            "incident_id": row.get("Incident ID") or "",
            "wo_id": row.get("INC-WO ID"),
            "wo_created_at": _to_seconds(row.get("INC-WO Created At")),
            "wo_status": row.get("INC-WO Status") or "",
            "site_name": row.get("Site Name") or "",
            "site_code": row.get("Site Code") or "",
            "overdue": row.get("overdue") or "",
            "support_level": row.get("Support Level") or "",
            "fault_description": row.get("Fault Description") or "",
            "nms": row.get("NMS") or "",
            "hub_site": row.get("Hub Site") or "",
            "site_grade": row.get("Site Grade") or "",
            "province": row.get("Province") or "",
            "district": row.get("District") or "",
            "commune": row.get("Commune") or "",
        }

    @staticmethod
    def _normalize_status_row(row):
        """Maps incident_by_status.sql's quoted, mixed-case column aliases
        (e.g. "Incident ID", "INC-WO ID") onto clean snake_case keys matching
        the incident_by_status cache table."""
        return {
            "incident_id": row.get("Incident ID") or "",
            "incident_status": row.get("Incident Status") or "",
            "wo_id": row.get("INC-WO ID") or "",
            "wo_created_at": _to_seconds(row.get("INC-WO Created At")),
            "wo_status": row.get("INC-WO Status") or "",
            "site_name": row.get("Site Name") or "",
            "site_code": row.get("Site Code") or "",
            "occurred_at": _to_seconds(row.get("Occurred At")),
            "overdue": row.get("overdue") or "",
            "category": row.get("category") or "",
            "l1_noc_investigation_result": row.get("L1 NOC Investigation Result") or "",
            "nms": row.get("NMS") or "",
            "hub_site": row.get("Hub Site") or "",
            "site_grade": row.get("Site Grade") or "",
            "province": row.get("Province") or "",
            "district": row.get("District") or "",
            "commune": row.get("Commune") or "",
        }
