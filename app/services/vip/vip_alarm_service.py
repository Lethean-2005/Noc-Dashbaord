"""Business logic for the VVIP Site dashboard card.

Reads from the local cache (instance/localstorage.db) that
app/services/vip/vip_alarm_scheduler.py keeps in sync in the background —
by filtering the already-synced ape_alarm cache down to VIP/VVIP sites
(see app/services/vip/vip_alarm_sync_service.py), not by querying Postgres
directly. The card always reports its full fixed set of badge categories,
same convention as app/services/alarm/alarm_service.py: a category with no
active alarms comes back as 0 (rendered green) instead of disappearing, so
the card layout never shifts.

vip_alarm has no event_name filter (every alarm type at a VIP/VVIP site is
cached, same as ape_alarm), so the badge categories below are derived
here, at read time, by matching event_name/additional_info against the
same keyword patterns ape_alarm.sql uses to build its own curated filter.

get_details()'s Incident/INC-WO enrichment reads from vip_incident_status,
NOT incident_by_status — that one only keeps 'new'/'in_progress' (shared by
IncidentService and MentorSiteService, both of which need Resolved
excluded), so a site's ticket reference would go blank the moment it's
Resolved. vip_incident_status is a separate cache scoped to only VIP/VVIP
sites (see app/database/queries/vip_incident_status.sql) that also keeps
Resolved incidents (only excludes Closed) — safe to widen that way here
specifically because it's scoped to 33 of 4,360 sites, unlike
incident_by_status which covers every site company-wide.
"""
from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.repositories.vip.vip_alarm_cache_repository import VipAlarmCacheRepository
from app.repositories.vip.vip_incident_status_cache_repository import VipIncidentStatusCacheRepository
from app.utils.alarm_category import SITE_DOWN_EVENTS
from app.utils.datetime import elapsed_minutes
from app.utils.event_name import clean_event_name
from app.utils.nms import NMS_NAMES

_TABLE = "vip_alarm"
_VIP_INCIDENT_STATUS_TABLE = "vip_incident_status"
_SITE_TABLE = "site_cache"

BADGE_TYPES = (
    "Site Down", "Main AC Failure", "Low DC Voltage", "High DC Voltage",
    "DG-On", "RECT Failure", "Door Alarm", "Other",
)

# vip_alarm.nms is the alarm's own raw numeric vendor code straight from
# object_138 — every other drilldown in this project (incident_by_status,
# incwo_by_status) translates this same code via object_227's nms_name
# (see app/utils/nms.py's NMS_NAMES, the one shared copy of this mapping),
# so it's translated here too instead of showing a bare "7".


def _categorize(event_name, additional_info):
    name = (event_name or "").lower()
    info = (additional_info or "").lower()
    if name in SITE_DOWN_EVENTS:
        return "Site Down"
    if "main failure" in name:
        return "Main AC Failure"
    if "high dc" in name:
        return "High DC Voltage"
    if "low dc" in name:
        return "Low DC Voltage"
    if "dg on" in name or "dg on" in info:
        return "DG-On"
    if "rectifier" in name:
        return "RECT Failure"
    if "door" in name:
        return "Door Alarm"
    return "Other"


class VipAlarmService:
    def __init__(self, cache_repository=None, vip_incident_status_cache_repository=None, site_cache_repository=None):
        self.cache_repository = cache_repository or VipAlarmCacheRepository()
        self.vip_incident_status_cache_repository = (
            vip_incident_status_cache_repository or VipIncidentStatusCacheRepository()
        )
        self.site_cache_repository = site_cache_repository or SiteCacheRepository()

    def get_counts(self):
        """{'Site Down': n, 'Main AC Failure': n, ...} for the VVIP Site
        badges — n is the number of DISTINCT SITES with at least one
        matching alarm, not the number of alarm rows (a site with 3 Main
        Failure alarms still counts once toward "Main AC Failure", not 3)."""
        rows = self.cache_repository.fetch_all(_TABLE)
        sites_by_category = {t: set() for t in BADGE_TYPES}
        for r in rows:
            site_code = r.get("site_code")
            if not site_code:
                continue
            category = _categorize(r.get("event_name"), r.get("additional_info"))
            sites_by_category[category].add(site_code)
        return {category: len(sites) for category, sites in sites_by_category.items()}

    def get_details(self, alarm_type=None):
        """Every cached VIP/VVIP alarm row, with outage_min filled in,
        optionally narrowed to one badge category (matches get_counts()'s
        categorization), and enriched with each site's current Incident/
        INC-WO (including Resolved, not just New/In Progress — see module
        docstring) plus Hub Site/Site Grade/Province — all resolved locally
        against vip_incident_status/site_cache (same reasoning as
        app/services/vip/vip_incident_alarm_sync_service.py: no Postgres
        call needed since both are already synced separately)."""
        rows = self.cache_repository.fetch_all(_TABLE)
        incident_by_site = IncidentStatusCacheRepository.latest_by_site(
            self.vip_incident_status_cache_repository.fetch_all(_VIP_INCIDENT_STATUS_TABLE)
        )
        site_by_code = {
            r["standard_code"]: r
            for r in self.site_cache_repository.fetch_all(_SITE_TABLE)
            if r.get("standard_code")
        }
        for r in rows:
            r["outage_min"] = elapsed_minutes(r.get("occurred_at"))
            r["badge_type"] = _categorize(r.get("event_name"), r.get("additional_info"))
            r["event_name"] = clean_event_name(r.get("event_name"))
            site_code = r.get("site_code") or ""
            inc = incident_by_site.get(site_code) or {}
            site = site_by_code.get(site_code) or {}
            r["incident_id"] = inc.get("incident_id") or ""
            r["incident_numeric_id"] = inc.get("incident_numeric_id")
            r["wo_id"] = inc.get("wo_id") or ""
            r["wo_numeric_id"] = inc.get("wo_numeric_id")
            r["wo_created_at"] = inc.get("wo_created_at") or ""
            r["wo_status"] = inc.get("wo_status") or ""
            r["resolved_at"] = inc.get("resolved_at") or ""
            r["category"] = inc.get("category") or ""
            r["hub_site"] = inc.get("hub_site") or site.get("hub_site") or ""
            r["site_grade"] = inc.get("site_grade") or (site.get("site_grade") or "").capitalize()
            r["province"] = inc.get("province") or site.get("province") or ""
            r["nms"] = inc.get("nms") or NMS_NAMES.get(str(r.get("nms") or "").strip(), r.get("nms"))
        if alarm_type:
            rows = [r for r in rows if r["badge_type"] == alarm_type]
        return rows
