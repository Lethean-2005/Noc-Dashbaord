"""Business logic for the Mentor Site page (app/routes/mentor.py) — lets
the user configure a specific list of sites to monitor (typed in or
uploaded via CSV), then checks each against the same alarm feed used
elsewhere (ape_alarm) and Incident tracking (incident_by_status), same
flow as app/services/vip/vip_alarm_service.py but for a user-picked site
list instead of every VIP/VVIP site.

mentor_sites (the table backing this) is NOT a Postgres/MSSQL sync cache —
see app/repositories/mentor/mentor_site_repository.py and
app/database/cache.py's init_cache_db() for why it's never auto-dropped.
Site Name/Province are resolved live from site_cache, not stored, so they
always reflect the latest Site master data.

One category system, _categorize() below, is shared by both UI surfaces on
this page:
  - get_configured_sites()'s "Status" column — a site with none of
    _categorize()'s types currently active shows "OK", Site Down takes
    priority if more than one matches, and anything that doesn't match one
    of the named categories shows "Other" rather than falling through
    unnoticed. (This used to run its own narrower 4-category check — Site
    Down/Main Failure/Low DC Voltage/DG On only — so a site whose only
    active alarm was, say, a Door Alarm or Rectifier Failure still showed
    "OK", reading as "nothing wrong" when something was.)
  - get_counts()/get_alarm_details()'s badge_type — the FULL 8-category
    breakdown (Site Down, Main AC Failure, Low DC Voltage, High DC
    Voltage, DG-On, RECT Failure, Door Alarm, Other), matching the Overall
    Dashboard's "Mentor Site" card (app/templates/dashboard/partials/cards.html)
    exactly. It's intentionally the same category logic as
    app/services/vip/vip_alarm_service.py's _categorize() (not imported
    from there, to avoid coupling two independently-evolving features to
    one shared private function) — both read the same ape_alarm-derived
    row shape, so the same keyword rules apply.
"""

import csv
import io
import re

from app.repositories.ape_alarm.ape_alarm_cache_repository import ApeAlarmCacheRepository
from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository
from app.repositories.mentor.mentor_site_repository import MentorSiteRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.utils.alarm_category import SITE_DOWN_EVENTS
from app.utils.datetime import elapsed_minutes
from app.utils.event_name import clean_event_name
from app.utils.nms import NMS_NAMES

_APE_ALARM_TABLE = "ape_alarm"
_SITE_TABLE = "site_cache"
_INCIDENT_STATUS_TABLE = "incident_by_status"

_SITE_DOWN_CATEGORY = "site down"

BADGE_TYPES = (
    "Site Down",
    "Main AC Failure",
    "Low DC Voltage",
    "High DC Voltage",
    "DG-On",
    "RECT Failure",
    "Door Alarm",
    "Other",
)

STATUS_TYPES = BADGE_TYPES + ("OK",)


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


class MentorSiteService:
    def __init__(
        self,
        mentor_site_repository=None,
        ape_alarm_cache_repository=None,
        site_cache_repository=None,
        incident_status_cache_repository=None,
    ):
        self.mentor_site_repository = mentor_site_repository or MentorSiteRepository()
        self.ape_alarm_cache_repository = ape_alarm_cache_repository or ApeAlarmCacheRepository()
        self.site_cache_repository = site_cache_repository or SiteCacheRepository()
        self.incident_status_cache_repository = (
            incident_status_cache_repository or IncidentStatusCacheRepository()
        )

    def _real_site_codes(self):
        """Every standard_code currently in site_cache — used to reject
        input that doesn't correspond to a real, known site instead of
        silently adding garbage a user mistyped."""
        return {
            r["standard_code"]
            for r in self.site_cache_repository.fetch_all(_SITE_TABLE)
            if r.get("standard_code")
        }

    def add_site_codes(self, raw_text):
        """Splits raw_text (comma/space/newline-separated, matching the
        page's chip input) into individual site codes and adds only the
        ones that match a real site_cache site and aren't already
        configured (source="Manual"). Returns (added, duplicate, invalid)
        — duplicate lists codes that are valid sites but already in the
        configured list (so the caller can say "already added" instead of
        silently no-op'ing); invalid lists whatever doesn't correspond to
        any known site."""
        codes = {
            c.strip().upper() for c in re.split(r"[^A-Za-z0-9_-]+", raw_text or "") if c.strip()
        }
        valid_codes = self._real_site_codes()
        already_configured = {r["site_code"] for r in self.mentor_site_repository.fetch_all()}
        added, duplicate, invalid = [], [], []
        for code in codes:
            if code not in valid_codes:
                invalid.append(code)
            elif code in already_configured:
                duplicate.append(code)
            else:
                self.mentor_site_repository.add(code, "Manual")
                added.append(code)
        return added, duplicate, invalid

    def add_from_csv(self, file_stream):
        """Parses an uploaded CSV (must have a site_code column, case-
        insensitive) and adds only the rows whose value matches a real
        site_cache site and isn't already configured (source="Import").
        Returns (added, duplicate, invalid, error) — error is a message
        string if the file has no recognizable site_code column, else
        None; duplicate lists codes that are valid sites but already
        configured; invalid lists whatever doesn't correspond to any known
        site."""
        text = file_stream.read().decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return [], [], [], "The file is empty."
        column = next((f for f in reader.fieldnames if f.strip().lower() == "site_code"), None)
        if not column:
            return [], [], [], "No 'site_code' column found in the file."
        valid_codes = self._real_site_codes()
        already_configured = {r["site_code"] for r in self.mentor_site_repository.fetch_all()}
        added, duplicate, invalid = [], [], []
        for row in reader:
            code = (row.get(column) or "").strip().upper()
            if not code:
                continue
            if code not in valid_codes:
                invalid.append(code)
            elif code in already_configured:
                duplicate.append(code)
            else:
                self.mentor_site_repository.add(code, "Import")
                added.append(code)
        return added, duplicate, invalid, None

    def has_configured_sites(self):
        """True once at least one site has been added on the Mentor Site
        page — used to hide the Overall Dashboard's Mentor Site card
        (app/templates/dashboard/partials/cards.html) until there's
        actually something configured to show, instead of displaying an
        all-zero card with nothing behind it."""
        return bool(self.mentor_site_repository.fetch_all())

    def remove_site(self, site_code):
        self.mentor_site_repository.remove(site_code)

    def clear_all_sites(self):
        self.mentor_site_repository.clear_all()

    def get_configured_sites(self):
        """One row per configured site: Site Code, Site Name, Province,
        Status (one of STATUS_TYPES — the full 8-category breakdown plus
        OK), Source, Added — Site Name/Province resolved live from
        site_cache. Status checks BOTH the site's current ape_alarm rows
        AND incident_by_status — a site can have an open Site Down
        Incident (a formal ticket) without a currently-firing NE alarm
        (e.g. the alarm already cleared but the ticket is still open, or
        the underlying issue doesn't raise an ape_alarm event at all), so
        relying on alarms alone would show "OK" for a site that genuinely
        has an active, tracked problem."""
        configured = self.mentor_site_repository.fetch_all()
        if not configured:
            return []

        site_by_code = {
            r["standard_code"]: r
            for r in self.site_cache_repository.fetch_all(_SITE_TABLE)
            if r.get("standard_code")
        }
        alarms_by_site = {}
        for row in self.ape_alarm_cache_repository.fetch_all(_APE_ALARM_TABLE):
            alarms_by_site.setdefault(row.get("site_code"), []).append(row)
        site_down_incident_codes = {
            r.get("site_code")
            for r in self.incident_status_cache_repository.fetch_all(_INCIDENT_STATUS_TABLE)
            if (r.get("category") or "").strip().lower() == _SITE_DOWN_CATEGORY
            and r.get("site_code")
        }

        result = []
        for entry in configured:
            site_code = entry["site_code"]
            site = site_by_code.get(site_code) or {}
            status = "Site Down" if site_code in site_down_incident_codes else "OK"
            for alarm in alarms_by_site.get(site_code, []):
                matched = _categorize(alarm.get("event_name"), alarm.get("additional_info"))
                if matched == "Site Down":
                    status = "Site Down"
                    break
                if status == "OK":
                    status = matched
            result.append(
                {
                    "site_code": site_code,
                    "site_name": site.get("physical_location_name") or site.get("name") or "",
                    "province": site.get("province") or "",
                    "status": status,
                    "source": entry.get("source") or "",
                    "added_at": entry.get("added_at") or "",
                }
            )
        return result

    def _configured_alarm_rows(self):
        configured_codes = {r["site_code"] for r in self.mentor_site_repository.fetch_all()}
        if not configured_codes:
            return []
        return [
            row
            for row in self.ape_alarm_cache_repository.fetch_all(_APE_ALARM_TABLE)
            if row.get("site_code") in configured_codes
        ]

    def get_counts(self):
        """{'Site Down': n, 'Main AC Failure': n, ...} for the Overall
        Dashboard's Mentor Site card — the full 8-category breakdown (see
        module docstring). n is the number of DISTINCT configured SITES
        with at least one matching alarm, not the number of alarm rows
        (same convention as vip_alarm_service.py's get_counts() — a site
        with 3 Main Failure alarms still counts once)."""
        sites_by_category = {t: set() for t in BADGE_TYPES}
        for row in self._configured_alarm_rows():
            site_code = row.get("site_code")
            if not site_code:
                continue
            category = _categorize(row.get("event_name"), row.get("additional_info"))
            sites_by_category[category].add(site_code)
        return {category: len(sites) for category, sites in sites_by_category.items()}

    def get_alarm_details(self, alarm_type=None, site_code=None):
        """Every cached ape_alarm row currently at a configured Mentor
        site, enriched with Incident/INC-WO/Resolved At/Category plus Hub
        Site/Site Grade/Province and outage_min, optionally narrowed to one
        of the 8 badge categories (matches get_counts()'s categorization —
        used when a Mentor Site card badge is clicked; the /mentor/ page's
        own "View Alarms" link passes nothing, showing every alarm type) —
        and/or to one specific site_code (the Configured Mentor Sites
        table's own per-row "View" action, so it opens only that site's
        alarms instead of every configured site's)."""
        alarm_rows = self._configured_alarm_rows()
        if not alarm_rows:
            return []

        incident_by_site = IncidentStatusCacheRepository.latest_by_site(
            self.incident_status_cache_repository.fetch_all(_INCIDENT_STATUS_TABLE)
        )
        site_by_code = {
            r["standard_code"]: r
            for r in self.site_cache_repository.fetch_all(_SITE_TABLE)
            if r.get("standard_code")
        }

        rows = []
        for alarm in alarm_rows:
            row = dict(alarm)
            row_site_code = row.get("site_code") or ""
            inc = incident_by_site.get(row_site_code) or {}
            site = site_by_code.get(row_site_code) or {}
            row["badge_type"] = _categorize(row.get("event_name"), row.get("additional_info"))
            row["event_name"] = clean_event_name(row.get("event_name"))
            row["outage_min"] = elapsed_minutes(row.get("occurred_at"))
            row["incident_id"] = inc.get("incident_id") or ""
            row["incident_numeric_id"] = inc.get("incident_numeric_id")
            row["wo_id"] = inc.get("wo_id") or ""
            row["wo_numeric_id"] = inc.get("wo_numeric_id")
            row["wo_created_at"] = inc.get("wo_created_at") or ""
            row["wo_status"] = inc.get("wo_status") or ""
            row["resolved_at"] = inc.get("resolved_at") or ""
            row["category"] = inc.get("category") or ""
            row["hub_site"] = inc.get("hub_site") or site.get("hub_site") or ""
            row["site_grade"] = inc.get("site_grade") or (site.get("site_grade") or "").capitalize()
            row["province"] = inc.get("province") or site.get("province") or ""
            row["nms"] = inc.get("nms") or NMS_NAMES.get(
                str(row.get("nms") or "").strip(), row.get("nms")
            )
            rows.append(row)

        if alarm_type:
            rows = [r for r in rows if r["badge_type"] == alarm_type]
        if site_code:
            rows = [r for r in rows if r.get("site_code") == site_code]
        return rows
