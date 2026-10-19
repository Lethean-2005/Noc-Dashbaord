"""Business logic for the RAN Status card's 'DC Low/High' column.

Reads from the local ape_alarm cache (synced by ape_alarm_scheduler.py),
purely local, no query of its own. Narrows to alarms whose event_name is
a High or Low DC Voltage variant — same "dc" substring check
vip_alarm_service.py and mentor_site_service.py already use for their
own High/Low DC Voltage badges, folded into one "Voltage" bucket here
since RAN Status doesn't split by direction.

Same shape as ran_main_ac_alarm_service.py in every other respect — see
that module's docstring for the Hub-Site-takes-priority-over-grade rule,
the Power-category-first/Site-Down-fallback Incident/INC-WO enrichment,
and the Remark column.
"""

from app.repositories.ape_alarm.ape_alarm_cache_repository import ApeAlarmCacheRepository
from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.utils.datetime import elapsed_minutes
from app.utils.event_name import clean_event_name
from app.utils.nms import NMS_NAMES
from app.utils.ttl_cache import ttl_cache

_APE_ALARM_TABLE = "ape_alarm"
_SITE_TABLE = "site_cache"
_INCIDENT_STATUS_TABLE = "incident_by_status"

BADGE_TYPES = ("Hub-Site", "Diamond", "Gold", "Silver", "Bronze")

_HUB_SITE_VALUES = {"hub-mw", "hub-router"}
_GRADE_BADGES = {"diamond": "Diamond", "gold": "Gold", "silver": "Silver", "bronze": "Bronze"}

_POWER_CATEGORY = "power"
_SITE_DOWN_CATEGORY = "site down"


def _is_voltage(event_name):
    name = (event_name or "").lower()
    return "high dc" in name or "low dc" in name


class RanVoltageService:
    def __init__(
        self,
        ape_alarm_cache_repository=None,
        site_cache_repository=None,
        incident_status_cache_repository=None,
    ):
        self.ape_alarm_cache_repository = ape_alarm_cache_repository or ApeAlarmCacheRepository()
        self.site_cache_repository = site_cache_repository or SiteCacheRepository()
        self.incident_status_cache_repository = (
            incident_status_cache_repository or IncidentStatusCacheRepository()
        )

    def _voltage_rows_with_site(self):
        """Only rows whose site_code has a matching site_cache record —
        that cache already excludes off_air sites (see site_cache.sql), so
        this also drops alarms still open against a site the master data
        marks decommissioned, plus any alarm whose site_code couldn't be
        resolved to any site at all. Same "off_air isn't really down" call
        already made for RAN Site Down/RAN Tech Down/Alarm Site Down/Alarm
        Main Failure."""
        alarm_rows = self.ape_alarm_cache_repository.fetch_all(_APE_ALARM_TABLE)
        site_by_code = {
            r["standard_code"]: r
            for r in self.site_cache_repository.fetch_all(_SITE_TABLE)
            if r.get("standard_code")
        }
        result = []
        for row in alarm_rows:
            if not _is_voltage(row.get("event_name")):
                continue
            site = site_by_code.get(row.get("site_code"))
            if site is None:
                continue
            result.append((row, site))
        return result

    @ttl_cache(15)
    def get_counts(self):
        """{'Hub-Site': n, 'Diamond': n, 'Gold': n, 'Silver': n, 'Bronze': n}
        — see module docstring: Hub-Site takes priority over grade."""
        counts = {t: 0 for t in BADGE_TYPES}
        for _, site in self._voltage_rows_with_site():
            if (site.get("hub_site") or "").lower() in _HUB_SITE_VALUES:
                counts["Hub-Site"] += 1
                continue
            badge = _GRADE_BADGES.get((site.get("site_grade") or "").lower())
            if badge:
                counts[badge] += 1
        return counts

    def get_details(self, badge_type=None):
        """Every cached Voltage ape_alarm row, enriched with its site's
        current Incident/INC-WO (from incident_by_status) — a Power-category
        incident if the site has one, otherwise falling back to its Site
        Down-category incident so the Incident/WO columns aren't left blank
        just because the open ticket happens to be filed as Site Down
        instead of Power. Remark shows that matched incident's own Incident
        Category as-is ("Power" / "Site Down") — not a fixed flag — so it's
        blank only when the site has neither, plus Hub Site/Site Grade/
        Province and outage_min computed at read time — optionally narrowed
        to one badge (matches get_counts()'s categorization)."""
        all_incidents = self.incident_status_cache_repository.fetch_all(_INCIDENT_STATUS_TABLE)
        power_incidents = [
            r for r in all_incidents if (r.get("category") or "").strip().lower() == _POWER_CATEGORY
        ]
        site_down_incidents = [
            r
            for r in all_incidents
            if (r.get("category") or "").strip().lower() == _SITE_DOWN_CATEGORY
        ]
        power_by_site = IncidentStatusCacheRepository.latest_by_site(power_incidents)
        site_down_by_site = IncidentStatusCacheRepository.latest_by_site(site_down_incidents)

        rows = []
        for alarm, site in self._voltage_rows_with_site():
            row = dict(alarm)
            inc = (
                power_by_site.get(row.get("site_code"))
                or site_down_by_site.get(row.get("site_code"))
                or {}
            )
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
            row["nms"] = inc.get("nms") or NMS_NAMES.get(
                str(row.get("nms") or "").strip(), row.get("nms")
            )
            row["remark"] = inc.get("category") or ""
            rows.append(row)

        if badge_type == "Hub-Site":
            rows = [r for r in rows if r["hub_site"].lower() in _HUB_SITE_VALUES]
        elif badge_type in _GRADE_BADGES.values():
            rows = [
                r
                for r in rows
                if r["site_grade"] == badge_type and r["hub_site"].lower() not in _HUB_SITE_VALUES
            ]
        return rows
