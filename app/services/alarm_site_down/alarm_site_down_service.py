"""Business logic for the "Alarm Site Down" card on the Custom Dashboard
(reports/index.html). Same architecture as
app/services/dg_on/dg_on_alarm_service.py — see that file for the full
reasoning, summarized here:

Reads from the local ape_alarm cache (instance/localstorage.db) that
app/services/ape_alarm/ape_alarm_scheduler.py keeps in sync in the
background — no query of its own, purely local. Narrows to alarms whose
event_name exactly matches one of app/utils/alarm_category.py's
SITE_DOWN_EVENTS (the same NE/connectivity event types ape_alarm.sql
originally filtered on, and the same set VipAlarmService/MentorSiteService
use for their own "Site Down" category) — confirmed against real Postgres
data before adding the newer variants (gNodeB Out of Service, gNodeB DU
out-of-service, etc.) to that set.

Hub and the 4 grade tiers (Diamond/Gold/Silver/Bronze) both come from
site_cache (hub_site / site_grade), and a site can technically be both a
hub site and graded — but Hub takes priority: a hub site's Site Down
alarm counts only toward "Hub", never also toward its grade badge, so the
same site never double-counts across two badges (same convention as
dg_on_alarm_service.py).

get_details() enriches each row with its site's current Incident/INC-WO
from the incident_site_down cache (app/database/queries/incident_site_down.sql) —
not incident_by_status, which the sync deliberately narrows to
'new'/'in_progress' only (see incident_sync_service.py). incident_site_down
is already scoped to exactly the right definition for this card's own
cross-reference: Incident Category = Site Down, Status != Closed (so a
Resolved-but-not-Closed incident still counts if its alarm hasn't cleared),
Cleared Alarm Received = FALSE. That's a broader/correct match than
incident_by_status would give, and needs no extra category filtering here
since every row already IS a Site Down incident.

ape_alarm.nms is the alarm's own raw numeric vendor code straight from
object_138 — translated here via app/utils/nms.py's NMS_NAMES, same as
every other drilldown in this project.
"""
from app.repositories.ape_alarm.ape_alarm_cache_repository import ApeAlarmCacheRepository
from app.repositories.incident.incident_site_down_cache_repository import IncidentSiteDownCacheRepository
from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.utils.alarm_category import SITE_DOWN_EVENTS, site_down_technology
from app.utils.datetime import elapsed_minutes
from app.utils.event_name import clean_event_name
from app.utils.nms import NMS_NAMES
from app.utils.ttl_cache import ttl_cache

_APE_ALARM_TABLE = "ape_alarm"
_SITE_TABLE = "site_cache"
_INCIDENT_SITE_DOWN_TABLE = "incident_site_down"

BADGE_TYPES = ("Hub", "Diamond", "Gold", "Silver", "Bronze")

_HUB_SITE_VALUES = {"hub-mw", "hub-router"}
_GRADE_BADGES = {"diamond": "Diamond", "gold": "Gold", "silver": "Silver", "bronze": "Bronze"}


def _is_site_down(event_name):
    return (event_name or "").strip().lower() in SITE_DOWN_EVENTS


class AlarmSiteDownService:
    def __init__(
        self,
        ape_alarm_cache_repository=None,
        site_cache_repository=None,
        incident_site_down_cache_repository=None,
    ):
        self.ape_alarm_cache_repository = ape_alarm_cache_repository or ApeAlarmCacheRepository()
        self.site_cache_repository = site_cache_repository or SiteCacheRepository()
        self.incident_site_down_cache_repository = (
            incident_site_down_cache_repository or IncidentSiteDownCacheRepository()
        )

    def _site_down_rows_with_site(self):
        """Only rows whose site_code has a matching site_cache record — that
        cache already excludes off_air sites (see site_cache.sql), so this
        also drops alarms still open against a site the master data marks
        decommissioned, plus any alarm whose site_code couldn't be resolved
        to any site at all. Without this, such rows showed up with a blank
        Site Name/Hub/Grade/Province (site_by_code.get() falling back to
        {}) instead of being excluded — same "off_air isn't really down"
        call already made for RAN Site Down/RAN Tech Down."""
        alarm_rows = self.ape_alarm_cache_repository.fetch_all(_APE_ALARM_TABLE)
        site_by_code = {
            r["standard_code"]: r
            for r in self.site_cache_repository.fetch_all(_SITE_TABLE)
            if r.get("standard_code")
        }
        result = []
        for row in alarm_rows:
            if not _is_site_down(row.get("event_name")):
                continue
            site = site_by_code.get(row.get("site_code"))
            if site is None:
                continue
            result.append((row, site))
        return result

    @ttl_cache(15)
    def get_counts(self):
        """{'Hub': n, 'Diamond': n, 'Gold': n, 'Silver': n, 'Bronze': n} —
        Hub takes priority over grade (see module docstring)."""
        counts = {t: 0 for t in BADGE_TYPES}
        for _, site in self._site_down_rows_with_site():
            if (site.get("hub_site") or "").lower() in _HUB_SITE_VALUES:
                counts["Hub"] += 1
                continue
            badge = _GRADE_BADGES.get((site.get("site_grade") or "").lower())
            if badge:
                counts[badge] += 1
        return counts

    def get_details(self, badge_type=None):
        """Every cached Site Down ape_alarm row, enriched with its site's
        current Incident/INC-WO from incident_site_down (already scoped to
        Category = Site Down, Status != Closed, Cleared Alarm Received =
        FALSE — see module docstring) if any, plus Hub Site/Site
        Grade/Province and outage_min computed at read time — optionally
        narrowed to one badge (matches get_counts()'s categorization)."""
        site_down_incidents = self.incident_site_down_cache_repository.fetch_all(_INCIDENT_SITE_DOWN_TABLE)
        incident_by_site = IncidentStatusCacheRepository.latest_by_site(site_down_incidents)

        rows = []
        for alarm, site in self._site_down_rows_with_site():
            row = dict(alarm)
            inc = incident_by_site.get(row.get("site_code")) or {}
            row["radio_technology"] = site_down_technology(row.get("event_name"))
            row["event_name"] = clean_event_name(row.get("event_name"))
            row["outage_min"] = elapsed_minutes(row.get("occurred_at"))
            row["incident_id"] = inc.get("incident_id") or ""
            row["incident_numeric_id"] = inc.get("incident_numeric_id")
            row["wo_id"] = inc.get("wo_id") or ""
            row["wo_numeric_id"] = inc.get("wo_numeric_id")
            row["wo_created_at"] = inc.get("wo_created_at") or ""
            row["wo_status"] = inc.get("wo_status") or ""
            row["hub_site"] = inc.get("hub_site") or site.get("hub_site") or ""
            row["site_grade"] = inc.get("site_grade") or (site.get("site_grade") or "").capitalize()
            row["province"] = inc.get("province") or site.get("province") or ""
            row["nms"] = inc.get("nms") or NMS_NAMES.get(str(row.get("nms") or "").strip(), row.get("nms"))
            rows.append(row)

        if badge_type == "Hub":
            rows = [r for r in rows if r["hub_site"].lower() in _HUB_SITE_VALUES]
        elif badge_type in _GRADE_BADGES.values():
            rows = [
                r for r in rows
                if r["site_grade"] == badge_type and r["hub_site"].lower() not in _HUB_SITE_VALUES
            ]
        return rows
