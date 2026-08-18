"""Business logic for the INC-WO / third column of the Incident/INC-WO card,
plus the "INC-WO Site Down" and "INC-WO Resolved" cards on the Custom
Dashboard (reports/index.html).

All of it reads from local caches (instance/localstorage.db, see
app/database/cache.py) that app/services/incident/incident_scheduler.py keeps in
sync with PostgreSQL in the background — the dashboard never waits on a
live Postgres query.
"""

from app.repositories.incwo.incwo_resolved_cache_repository import IncWoResolvedCacheRepository
from app.repositories.incwo.incwo_status_cache_repository import IncWoStatusCacheRepository

_TABLE = "inc_wo_by_status"
_SITE_DOWN_TABLE = "inc_wo_site_down"
_RESOLVED_TABLE = "inc_wo_resolved"


# badge `type` (from the drilldown URL / badge count key) -> the exact
# field/value pairs to match in inc_wo_by_status (already formatted by
# inc_wo_by_status.sql, e.g. 'l2_on_site' -> 'L2 On-Site', overdue -> 'Yes').
# Add the next badge here the same way.
#
# "resolved" also requires incident_status == "In Progress" — same
# definition as the separate "INC-WO Resolved" card (inc_wo_resolved.sql):
# an INC-WO that's Resolved while its parent Incident is still open overall,
# not just any Resolved INC-WO regardless of the parent Incident's status.
#
# "overdue"/"overdue_l2"/"overdue_l3" cache every incident category — the
# only thing excluded is the specific combination of Customer Complaint +
# parent Incident already Resolved (not "Customer Complaint only", and not
# "every Resolved incident"). A row with any other category is kept
# regardless of resolved status; a Customer Complaint row is kept as long
# as it isn't yet Resolved. "_exclude" is a special filter key (see
# _matches() below): a callable given the whole row, returning True if the
# row should be dropped — the opposite of every other filter key, which is
# a positive match requirement.
def _is_resolved_customer_complaint(row):
    return (
        row.get("incident_category") == "Customer Complaint"
        and row.get("incident_status") == "Resolved"
    )


BADGE_FILTERS = {
    "new": {"wo_status": "New"},
    "assigned": {"wo_status": "Assigned"},
    "acknowledged": {"wo_status": "Acknowledged"},
    "in_progress": {"wo_status": "In Progress"},
    "resolved": {"wo_status": "Resolved", "incident_status": "In Progress"},
    "reopened": {"wo_status": "Reopened"},
    "returned": {"wo_status": "Returned"},
    "on_hold": {"wo_status": "On Hold"},
    "overdue": {"overdue": "Yes", "_exclude": _is_resolved_customer_complaint},
    "overdue_l2": {
        "overdue": "Yes",
        "support_level": "L2 On-Site",
        "_exclude": _is_resolved_customer_complaint,
    },
    "overdue_l3": {
        "overdue": "Yes",
        "support_level": "L3 Internal Support",
        "_exclude": _is_resolved_customer_complaint,
    },
}

# "INC-WO Site Down" card badge `type` -> field/value pair to match in
# inc_wo_site_down. hub_site checks for "any kind of hub" (Hub-Router or
# Hub-MW), not an exact match — see get_site_down_counts().
_SITE_GRADE_BADGES = {
    "diamond": "Diamond",
    "gold": "Gold",
    "silver": "Silver",
    "bronze": "Bronze",
}


def _matches(row, filters):
    """Each filter value is either an exact value to match, or a callable
    predicate on that one field's value (e.g. `lambda status: status !=
    "Resolved"`) for conditions a plain equality check can't express. The
    special key "_exclude" is a callable given the whole row instead of one
    field's value, returning True if the row should be DROPPED rather than
    kept — for conditions on a combination of fields, like BADGE_FILTERS["overdue"]'s
    "drop only if Customer Complaint AND Resolved" rule, which isn't
    expressible as a per-field requirement."""
    for key, value in filters.items():
        if key == "_exclude":
            if value(row):
                return False
            continue
        actual = row.get(key)
        if callable(value):
            if not value(actual):
                return False
        elif actual != value:
            return False
    return True


def _matches_site_down_badge(row, badge_type):
    """True if `row` belongs under the clicked "INC-WO Site Down" badge
    (hub_site/diamond/gold/silver/bronze) — same rule used to compute the
    badge counts in get_site_down_counts()."""
    if badge_type == "hub_site":
        return (row.get("hub_site") or "").strip() not in ("", "Not Hub")
    return row.get("site_grade") == _SITE_GRADE_BADGES.get(badge_type)


class IncWoService:
    def __init__(self, status_cache_repository=None, resolved_cache_repository=None):
        self.status_cache_repository = status_cache_repository or IncWoStatusCacheRepository()
        self.resolved_cache_repository = resolved_cache_repository or IncWoResolvedCacheRepository()

    def get_incwo_counts(self):
        """Badge counts for every INC-WO-column badge (New, Assigned,
        Acknowledged, In-Progress, Resolved, Reopened, Returned, On-Hold,
        Overdue, Overdue L2, Overdue L3)."""
        rows = self.status_cache_repository.fetch_all(_TABLE)
        return {
            badge_type: sum(1 for r in rows if _matches(r, filters))
            for badge_type, filters in BADGE_FILTERS.items()
        }

    def get_details(self, badge_type=None):
        """Full drilldown rows for one INC-WO badge (see BADGE_FILTERS) — or
        every row if `badge_type` is empty (the plain "View INC-WO" link,
        with no badge clicked). Returns None only when `badge_type` is
        given but isn't a known badge, distinguishing "no filter" from
        "invalid filter" for drilldown_download()'s 404 handling."""
        if not badge_type:
            filters = {}
        else:
            filters = BADGE_FILTERS.get(badge_type)
            if filters is None:
                return None
        rows = self.status_cache_repository.fetch_all(_TABLE)
        filtered = [r for r in rows if _matches(r, filters)]
        for r in filtered:
            r["wo_id"] = r.get("wo_id") or ""
        return filtered

    def get_site_down_counts(self):
        """Badge counts for the "INC-WO Site Down" card (Hub-Site, Diamond,
        Gold, Silver, Bronze) — hub_site counts any hub type, the rest match
        site_grade exactly."""
        rows = self.status_cache_repository.fetch_all(_SITE_DOWN_TABLE)
        counts = {
            grade: sum(1 for r in rows if r.get("site_grade") == label)
            for grade, label in _SITE_GRADE_BADGES.items()
        }
        counts["hub_site"] = sum(
            1 for r in rows if (r.get("hub_site") or "").strip() not in ("", "Not Hub")
        )
        return counts

    def get_site_down_details(self, badge_type=None):
        """Rows behind the "INC-WO Site Down" card. `badge_type`
        (hub_site/diamond/gold/silver/bronze) narrows to just that badge's
        rows, matching get_site_down_counts(); omit it (or pass "") for
        every row.

        Rows with no wo_id yet (a brand-new WO the source hasn't assigned
        one to) are dropped — nothing meaningful to show until then."""
        rows = self.status_cache_repository.fetch_all(_SITE_DOWN_TABLE)
        rows = [r for r in rows if r.get("wo_id")]
        if badge_type:
            rows = [r for r in rows if _matches_site_down_badge(r, badge_type)]
        return rows

    def get_resolved_count(self):
        """Single badge count for the "INC-WO Resolved" card."""
        return len(self.resolved_cache_repository.fetch_all(_RESOLVED_TABLE))

    def get_resolved_details(self):
        """Every row behind the "INC-WO Resolved" card — already fully
        scoped by inc_wo_resolved.sql, no further filtering needed."""
        rows = self.resolved_cache_repository.fetch_all(_RESOLVED_TABLE)
        for r in rows:
            r["wo_id"] = r.get("wo_id") or ""
        return rows
