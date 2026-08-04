"""Business logic for the "Alarm Completely Site Down" card on the Custom
Dashboard (reports/index.html). Same base data as
app/services/alarm_site_down/alarm_site_down_service.py (open ape_alarm
rows matching app/utils/alarm_category.py's SITE_DOWN_EVENTS), but narrowed
further to sites where EVERY radio technology the site actually has
(2g/3g/4g/5g, from the site_technology_cache — see
app/database/queries/site_technology_cache.sql) is currently down, not just one.

The completely-down/partially-down split itself lives in
app/utils/alarm_category.py's classify_site_technology_coverage() — shared
with app/services/ran/ran_site_down_service.py and ran_tech_down_service.py,
the RAN Status card's equivalent "all techs down" / "one tech down"
columns, so all three read one definition instead of re-deriving it. See
that function's docstring for the full SRAN/generation mapping reasoning.

A site with no known technology inventory (not in site_technology_cache)
never counts as "completely" down — there's nothing to have fully covered.

Hub/Diamond/Gold/Silver/Bronze (Hub takes priority over grade — a hub site
never also double-counts under its grade badge) and the Incident/INC-WO
enrichment follow the same conventions as alarm_site_down_service.py — see
that file for the fuller reasoning.
"""
from app.repositories.ape_alarm.ape_alarm_cache_repository import ApeAlarmCacheRepository
from app.repositories.incident.incident_site_down_cache_repository import IncidentSiteDownCacheRepository
from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.repositories.site.site_technology_cache_repository import SiteTechnologyCacheRepository
from app.utils.alarm_category import SITE_DOWN_EVENTS, classify_site_technology_coverage, site_down_technology
from app.utils.datetime import elapsed_minutes
from app.utils.event_name import clean_event_name
from app.utils.nms import NMS_NAMES
from app.utils.ttl_cache import ttl_cache

_APE_ALARM_TABLE = "ape_alarm"
_SITE_TABLE = "site_cache"
_SITE_TECHNOLOGY_TABLE = "site_technology_cache"
_INCIDENT_SITE_DOWN_TABLE = "incident_site_down"

BADGE_TYPES = ("Hub", "Diamond", "Gold", "Silver", "Bronze")

_HUB_SITE_VALUES = {"hub-mw", "hub-router"}
_GRADE_BADGES = {"diamond": "Diamond", "gold": "Gold", "silver": "Silver", "bronze": "Bronze"}


def _is_site_down(event_name):
    return (event_name or "").strip().lower() in SITE_DOWN_EVENTS


class AlarmCompletelySiteDownService:
    def __init__(
        self,
        ape_alarm_cache_repository=None,
        site_cache_repository=None,
        site_technology_cache_repository=None,
        incident_site_down_cache_repository=None,
    ):
        self.ape_alarm_cache_repository = ape_alarm_cache_repository or ApeAlarmCacheRepository()
        self.site_cache_repository = site_cache_repository or SiteCacheRepository()
        self.site_technology_cache_repository = (
            site_technology_cache_repository or SiteTechnologyCacheRepository()
        )
        self.incident_site_down_cache_repository = (
            incident_site_down_cache_repository or IncidentSiteDownCacheRepository()
        )

    def _technology_inventory_by_site(self):
        rows = self.site_technology_cache_repository.fetch_all(_SITE_TECHNOLOGY_TABLE)
        inventory = {}
        for r in rows:
            code = r.get("site_code")
            if code:
                inventory.setdefault(code, set()).add(r.get("technology"))
        return inventory

    def _completely_down_site_codes(self):
        alarm_rows = [
            row for row in self.ape_alarm_cache_repository.fetch_all(_APE_ALARM_TABLE)
            if _is_site_down(row.get("event_name"))
        ]
        completely_down, _partially_down = classify_site_technology_coverage(
            alarm_rows, self._technology_inventory_by_site()
        )
        return completely_down

    def _rows_with_site(self):
        completely_down = self._completely_down_site_codes()
        alarm_rows = self.ape_alarm_cache_repository.fetch_all(_APE_ALARM_TABLE)
        site_by_code = {
            r["standard_code"]: r
            for r in self.site_cache_repository.fetch_all(_SITE_TABLE)
            if r.get("standard_code")
        }
        return [
            (row, site_by_code.get(row.get("site_code")) or {})
            for row in alarm_rows
            if _is_site_down(row.get("event_name")) and row.get("site_code") in completely_down
        ]

    @ttl_cache(15)
    def get_counts(self):
        """{'Hub': n, 'Diamond': n, 'Gold': n, 'Silver': n, 'Bronze': n} —
        counts distinct sites that are completely down. Hub takes priority
        over grade: a hub site counts only toward "Hub", never also toward
        its grade badge."""
        completely_down = self._completely_down_site_codes()
        site_by_code = {
            r["standard_code"]: r
            for r in self.site_cache_repository.fetch_all(_SITE_TABLE)
            if r.get("standard_code")
        }
        counts = {t: 0 for t in BADGE_TYPES}
        for code in completely_down:
            site = site_by_code.get(code) or {}
            if (site.get("hub_site") or "").lower() in _HUB_SITE_VALUES:
                counts["Hub"] += 1
                continue
            badge = _GRADE_BADGES.get((site.get("site_grade") or "").lower())
            if badge:
                counts[badge] += 1
        return counts

    def get_details(self, badge_type=None):
        """Every cached Site Down ape_alarm row belonging to a completely-
        down site, enriched with its site's current Incident/INC-WO from
        incident_site_down if any, plus Hub Site/Site Grade/Province and
        outage_min computed at read time — optionally narrowed to one badge
        (matches get_counts()'s categorization)."""
        site_down_incidents = self.incident_site_down_cache_repository.fetch_all(_INCIDENT_SITE_DOWN_TABLE)
        incident_by_site = IncidentStatusCacheRepository.latest_by_site(site_down_incidents)

        rows = []
        for alarm, site in self._rows_with_site():
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
