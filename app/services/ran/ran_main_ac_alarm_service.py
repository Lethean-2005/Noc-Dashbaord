"""Business logic for the RAN Status card's 'RAN Main AC Alarm' column.

Reads the local ape_alarm cache, no query of its own. Narrows to alarms
whose event_name contains "main failure" (case-insensitive substring —
real event_name text is messy, an exact match hits zero rows).

Hub-Site and the 4 grade tiers come from site_cache — Hub-Site takes
priority, so a hub site's alarm never also counts toward its grade badge.

get_details() enriches each row with the site's current Incident/INC-WO:
a Power-category incident takes priority, Site Down is the fallback (a
Main AC Failure often precedes a full outage).

ape_alarm.nms (the live alarm feed's own vendor code) wins over the
matched incident's nms (resolved from NE inventory, which can be stale
for a site whose equipment changed) — the incident's nms is only a
fallback when the alarm itself has none. Same order as
vip_alarm_service.py/alarm_site_down_service.py.
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


def _is_main_failure(event_name):
    return "main failure" in (event_name or "").lower()


class RanMainAcAlarmService:
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

    def _main_failure_rows_with_site(self):
        """Only rows whose site_code has a matching site_cache record —
        that cache already excludes off_air sites, so this also drops
        alarms against a decommissioned or unresolvable site."""
        alarm_rows = self.ape_alarm_cache_repository.fetch_all(_APE_ALARM_TABLE)
        site_by_code = {
            r["standard_code"]: r
            for r in self.site_cache_repository.fetch_all(_SITE_TABLE)
            if r.get("standard_code")
        }
        result = []
        for row in alarm_rows:
            if not _is_main_failure(row.get("event_name")):
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
        for _, site in self._main_failure_rows_with_site():
            if (site.get("hub_site") or "").lower() in _HUB_SITE_VALUES:
                counts["Hub-Site"] += 1
                continue
            badge = _GRADE_BADGES.get((site.get("site_grade") or "").lower())
            if badge:
                counts[badge] += 1
        return counts

    def get_details(self, badge_type=None):
        """Every cached Main-Failure ape_alarm row, enriched with its
        site's current Incident/INC-WO — Power-category preferred, Site
        Down as fallback. Remark shows that incident's own category as-is.
        Optionally narrowed to one badge (matches get_counts())."""
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
        for alarm, site in self._main_failure_rows_with_site():
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
            row["nms"] = NMS_NAMES.get(str(row.get("nms") or "").strip(), row.get("nms")) or inc.get(
                "nms"
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
