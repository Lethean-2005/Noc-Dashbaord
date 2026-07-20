"""Business logic for the Incident / INC-WO card, plus the "Incident Site
Down" card on the Custom Dashboard (reports/index.html).

Both badge counts and drilldown detail read from local caches
(instance/localstorage.db, see app/database/cache.py) that
app/services/incident_scheduler.py keeps in sync with PostgreSQL in the
background — the dashboard never waits on a live Postgres query.
"""
from app.repositories.incident_site_down_cache_repository import IncidentSiteDownCacheRepository
from app.repositories.incident_status_cache_repository import IncidentStatusCacheRepository
from app.utils.datetime import elapsed_minutes

_STATUS_TABLE = "incident_by_status"
_SITE_DOWN_TABLE = "incident_site_down"

# badge `type` (from the drilldown URL / badge count key) -> the exact
# field/value pairs to match in incident_by_status (already formatted by
# incident_by_status.sql, e.g. 'site_down' -> 'Site Down', overdue -> 'Yes').
# Add the next badge here the same way.
BADGE_FILTERS = {
    "new": {"incident_status": "New"},
    "new_site_down": {"incident_status": "New", "category": "Site Down"},
    "in_progress": {"incident_status": "In Progress"},
    "in_progress_site_down": {"incident_status": "In Progress", "category": "Site Down"},
    "overdue": {"overdue": "Yes"},
    "overdue_site_down": {"overdue": "Yes", "category": "Site Down"},
}

# "Incident Site Down" card badge `type` -> site_grade value to match in
# incident_site_down (already INITCAP'd by site_down.sql). "hub" checks for
# "any kind of hub" (Hub-Router or Hub-MW), not an exact match — see
# get_incident_site_down_counts().
_SITE_GRADE_BADGES = {
    "diamond": "Diamond",
    "gold": "Gold",
    "silver": "Silver",
    "bronze": "Bronze",
}


def _matches(row, filters):
    return all(row.get(key) == value for key, value in filters.items())


def _matches_site_down_badge(row, badge_type):
    """True if `row` belongs under the clicked "Incident Site Down" badge
    (hub/diamond/gold/silver/bronze) — same rule used to compute the badge
    counts in get_incident_site_down_counts()."""
    if badge_type == "hub":
        return (row.get("hub_site") or "").strip() not in ("", "Not Hub")
    return row.get("site_grade") == _SITE_GRADE_BADGES.get(badge_type)


class IncidentService:
    def __init__(self, status_cache_repository=None, site_down_cache_repository=None):
        self.status_cache_repository = status_cache_repository or IncidentStatusCacheRepository()
        self.site_down_cache_repository = site_down_cache_repository or IncidentSiteDownCacheRepository()

    def get_incident_counts(self):
        """Badge counts for every Incident-column badge (New, New Site-Down,
        In-Progress, In-Progress Site-Down, Overdue, Overdue Site-Down)."""
        rows = self.status_cache_repository.fetch_all(_STATUS_TABLE)
        return {
            badge_type: sum(1 for r in rows if _matches(r, filters))
            for badge_type, filters in BADGE_FILTERS.items()
        }

    def get_details(self, badge_type):
        """Full drilldown rows for one Incident badge (see BADGE_FILTERS),
        with outage_min filled in. Returns None if `badge_type` isn't a
        known badge."""
        filters = BADGE_FILTERS.get(badge_type)
        if filters is None:
            return None
        rows = self.status_cache_repository.fetch_all(_STATUS_TABLE)
        filtered = [r for r in rows if _matches(r, filters)]
        for r in filtered:
            r["outage_min"] = elapsed_minutes(r.get("occurred_at"))
        return filtered

    def get_incident_site_down_counts(self):
        """Badge counts for the "Incident Site Down" card (Hub, Diamond,
        Gold, Silver, Bronze) — hub counts any hub type, the rest match
        site_grade exactly."""
        rows = self.site_down_cache_repository.fetch_all(_SITE_DOWN_TABLE)
        counts = {
            grade: sum(1 for r in rows if r.get("site_grade") == label)
            for grade, label in _SITE_GRADE_BADGES.items()
        }
        counts["hub"] = sum(
            1 for r in rows if (r.get("hub_site") or "").strip() not in ("", "Not Hub")
        )
        return counts

    def get_incident_site_down_details(self, badge_type=None):
        """Rows behind the "Incident Site Down" card, with outage_min filled
        in. `badge_type` (hub/diamond/gold/silver/bronze) narrows to just
        that badge's rows, matching get_incident_site_down_counts(); omit it
        (or pass "") for every row."""
        rows = self.site_down_cache_repository.fetch_all(_SITE_DOWN_TABLE)
        if badge_type:
            rows = [r for r in rows if _matches_site_down_badge(r, badge_type)]
        for r in rows:
            r["outage_min"] = elapsed_minutes(r.get("occurred_at"))
        return rows
