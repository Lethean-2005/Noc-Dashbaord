"""Builds the vip_incident_alarm cache (instance/localstorage.db) by joining
three ALREADY-SYNCED local tables — vip_alarm, incident_by_status, and
site_cache — entirely in Python. Unlike every other *_sync_service.py in
this project, this one never touches Postgres: all three source tables
are themselves kept fresh by their own sync services
(vip_alarm_sync_service.py, incident_sync_service.py, site_sync_service.py),
so this is just a local re-join of data already on disk. No retry logic is
needed since there's no foreign table, no replica, and no
"conflict with recovery" risk at this layer.
"""
from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.repositories.vip.vip_alarm_cache_repository import VipAlarmCacheRepository
from app.repositories.vip.vip_incident_alarm_cache_repository import VipIncidentAlarmCacheRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = "vip_incident_alarm"
_VIP_ALARM_TABLE = "vip_alarm"
_INCIDENT_STATUS_TABLE = "incident_by_status"
_SITE_TABLE = "site_cache"


class VipIncidentAlarmSyncService:
    def __init__(self, vip_alarm_cache_repository=None, incident_status_cache_repository=None,
                 site_cache_repository=None, cache_repository=None):
        self.vip_alarm_cache_repository = vip_alarm_cache_repository or VipAlarmCacheRepository()
        self.incident_status_cache_repository = incident_status_cache_repository or IncidentStatusCacheRepository()
        self.site_cache_repository = site_cache_repository or SiteCacheRepository()
        self.cache_repository = cache_repository or VipIncidentAlarmCacheRepository()

    def sync(self):
        """Rebuild vip_incident_alarm from the three local cache tables.
        Wrapped in try/except-per-step, same reasoning as every other sync
        service: this runs inside an infinite background loop, so any
        uncaught exception here would silently kill that loop forever.
        Returns the row count synced, or None on failure."""
        try:
            alarm_rows = self.vip_alarm_cache_repository.fetch_all(_VIP_ALARM_TABLE)
            incident_rows = self.incident_status_cache_repository.fetch_all(_INCIDENT_STATUS_TABLE)
            site_rows = self.site_cache_repository.fetch_all(_SITE_TABLE)
        except Exception as e:
            logger.error(f"Reading local cache tables for vip_incident_alarm failed: {e}")
            return None

        incident_by_site = IncidentStatusCacheRepository.latest_by_site(incident_rows)
        site_by_code = {r["standard_code"]: r for r in site_rows if r.get("standard_code")}

        normalized = [self._normalize_row(a, incident_by_site, site_by_code) for a in alarm_rows]
        try:
            self.cache_repository.replace_all(_TABLE, normalized)
        except Exception as e:
            logger.error(f"vip_incident_alarm cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_TABLE}")
        return len(normalized)

    @staticmethod
    def _normalize_row(alarm, incident_by_site, site_by_code):
        """One row per vip_alarm entry, enriched with its site's current
        Incident/INC-WO (if any) and Hub Site/Site Grade/Province — falling
        back to site_cache when there's no active incident to pull those
        from."""
        site_code = alarm.get("site_code") or ""
        inc = incident_by_site.get(site_code) or {}
        site = site_by_code.get(site_code) or {}
        return {
            "incident_id": inc.get("incident_id") or "",
            "wo_id": inc.get("wo_id") or "",
            "wo_created_at": inc.get("wo_created_at") or "",
            "wo_status": inc.get("wo_status") or "",
            "resolved_at": inc.get("resolved_at") or "",
            "site_name": alarm.get("site_name") or inc.get("site_name") or site.get("physical_location_name") or "",
            "site_code": site_code,
            "occurred_at": alarm.get("occurred_at") or "",
            "event_name": alarm.get("event_name") or "",
            "category": inc.get("category") or "",
            "nms": alarm.get("nms") or inc.get("nms") or "",
            "hub_site": inc.get("hub_site") or site.get("hub_site") or "",
            "site_grade": inc.get("site_grade") or (site.get("site_grade") or "").capitalize() or "",
            "province": inc.get("province") or site.get("province") or "",
        }
