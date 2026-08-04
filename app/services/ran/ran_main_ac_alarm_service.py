"""Business logic for the RAN Status card's 'RAN Main AC Alarm' column.

Reads from the local ape_alarm cache (instance/localstorage.db) that
app/services/ape_alarm/ape_alarm_scheduler.py keeps in sync in the
background — no query of its own, purely local. Narrows to alarms whose
event_name is a Main Failure variant: real event_name text is messy
("Main Failure Alarm", "BASE STATION EXTERNAL ALARM NOTIFICATION:::Main
Failure", plus assorted typos), so this uses the same case-insensitive
substring check app/services/vip/vip_alarm_service.py already uses for its
own "Main AC Failure" badge, rather than an exact match (which would match
zero rows against the real data).

Hub-Site and the 4 grade tiers (Diamond/Gold/Silver/Bronze) both come from
site_cache (hub_site / site_grade), and a site can technically be both a
hub site and graded — but Hub-Site takes priority: a hub site's
Main-Failure alarm counts only toward "Hub-Site", never also toward its
grade badge, so the same site never appears to double-count across two
badges on the card.

get_details() also enriches each row with its site's current **Power**-
category Incident/INC-WO (from incident_by_status) if any — deliberately
narrower than "any open incident": a Main Failure alarm's Incident/INC-WO
context should be the Power ticket tracking that same outage, not an
unrelated Incident of some other category that happens to be open at the
same site. No Postgres call needed, just a local join (same reasoning as
app/services/vip/vip_alarm_service.py).

Remark is a "Site down" cross-reference flag — set when the same site
*also* currently has an open **Site Down**-category incident (a Main AC
Failure often precedes/accompanies a full site outage), not the matched
Power incident's own investigation notes.

Real incident_by_status.category values are "Power" and "Site Down"
(title case, space not underscore) — confirmed against real data, not the
lowercase 'power'/'site_down' Postgres enum values you might expect.

ape_alarm.nms is the alarm's own raw numeric vendor code straight from
object_138 — translated here via app/utils/nms.py's NMS_NAMES (the one
shared copy of this mapping), same as every other drilldown in this
project, instead of showing a bare "7". If the site has a current Power
incident, that record's own already-translated nms takes priority (same
preference order as vip_alarm_service.py).
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
        self.incident_status_cache_repository = incident_status_cache_repository or IncidentStatusCacheRepository()

    def _main_failure_rows_with_site(self):
        alarm_rows = self.ape_alarm_cache_repository.fetch_all(_APE_ALARM_TABLE)
        site_by_code = {
            r["standard_code"]: r
            for r in self.site_cache_repository.fetch_all(_SITE_TABLE)
            if r.get("standard_code")
        }
        return [
            (row, site_by_code.get(row.get("site_code")) or {})
            for row in alarm_rows
            if _is_main_failure(row.get("event_name"))
        ]

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
        """Every cached Main-Failure ape_alarm row, enriched with its site's
        current Power-category Incident/INC-WO (from incident_by_status) if
        any, a "Site down" Remark flag if that same site also currently has
        an open Site Down-category incident, plus Hub Site/Site Grade/
        Province and outage_min computed at read time — optionally narrowed
        to one badge (matches get_counts()'s categorization)."""
        all_incidents = self.incident_status_cache_repository.fetch_all(_INCIDENT_STATUS_TABLE)
        power_incidents = [r for r in all_incidents if (r.get("category") or "").strip().lower() == _POWER_CATEGORY]
        incident_by_site = IncidentStatusCacheRepository.latest_by_site(power_incidents)
        site_down_site_codes = {
            r.get("site_code") for r in all_incidents
            if (r.get("category") or "").strip().lower() == _SITE_DOWN_CATEGORY and r.get("site_code")
        }

        rows = []
        for alarm, site in self._main_failure_rows_with_site():
            row = dict(alarm)
            inc = incident_by_site.get(row.get("site_code")) or {}
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
            row["remark"] = "Site down" if row.get("site_code") in site_down_site_codes else ""
            rows.append(row)

        if badge_type == "Hub-Site":
            rows = [r for r in rows if r["hub_site"].lower() in _HUB_SITE_VALUES]
        elif badge_type in _GRADE_BADGES.values():
            rows = [
                r for r in rows
                if r["site_grade"] == badge_type and r["hub_site"].lower() not in _HUB_SITE_VALUES
            ]
        return rows
