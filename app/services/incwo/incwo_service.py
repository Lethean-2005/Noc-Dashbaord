"""Business logic for the INC-WO card, plus the "INC-WO Site Down" and
"INC-WO Resolved" cards. Reads from local caches kept in sync by
app/services/incident/incident_scheduler.py — never queries Postgres live."""

from app.repositories.incwo.incwo_resolved_cache_repository import IncWoResolvedCacheRepository
from app.repositories.incwo.incwo_status_cache_repository import IncWoStatusCacheRepository
from app.utils.ttl_cache import ttl_cache

_TABLE = "inc_wo_by_status"
_SITE_DOWN_TABLE = "inc_wo_site_down"
_RESOLVED_TABLE = "inc_wo_resolved"


# badge type -> field/value pairs to match in inc_wo_by_status.
# "resolved" also requires incident_status == "In Progress" (Resolved WO,
# parent Incident still open) — same rule as inc_wo_resolved.sql.
# "overdue*" drop only Customer Complaint rows whose parent Incident is
# already Resolved — see "_exclude" in _matches() below.
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

# "INC-WO Site Down" badge type -> site_grade value. hub_site (below) checks
# for any hub type, not an exact match.
_SITE_GRADE_BADGES = {
    "diamond": "Diamond",
    "gold": "Gold",
    "silver": "Silver",
    "bronze": "Bronze",
}


def _matches(row, filters):
    """Each filter value is an exact match or a predicate callable on that
    field. "_exclude" is a callable on the whole row — True means drop it,
    for conditions spanning multiple fields (e.g. "overdue")."""
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
    """True if `row` belongs under the clicked "INC-WO Site Down" badge."""
    if badge_type == "hub_site":
        return (row.get("hub_site") or "").strip() not in ("", "Not Hub")
    return row.get("site_grade") == _SITE_GRADE_BADGES.get(badge_type)


def _fully_resolved_incident_ids(status_rows):
    """incident_numeric_ids from inc_wo_by_status where every WO on that
    incident has wo_status == "Resolved" — used by
    IncWoService._resolved_rows() to drop an incident's resolved WO(s)
    from the "INC-WO Resolved" card while a sibling WO is still open."""
    incident_ids = set()
    unresolved_incident_ids = set()
    for row in status_rows:
        incident_id = row.get("incident_numeric_id")
        incident_ids.add(incident_id)
        if row.get("wo_status") != "Resolved":
            unresolved_incident_ids.add(incident_id)
    return incident_ids - unresolved_incident_ids


def _resolved_sort_key(row):
    """Newest-first key for the "INC-WO Resolved" card — Resolved At,
    falling back to INC-WO Created At so a row with no resolved_at yet
    still sorts deterministically instead of erroring on comparison."""
    return (row.get("resolved_at") or "", row.get("wo_created_at") or "")


class IncWoService:
    def __init__(self, status_cache_repository=None, resolved_cache_repository=None):
        self.status_cache_repository = status_cache_repository or IncWoStatusCacheRepository()
        self.resolved_cache_repository = resolved_cache_repository or IncWoResolvedCacheRepository()

    @ttl_cache(15)
    def get_incwo_counts(self):
        """Badge counts for every INC-WO-column badge (see BADGE_FILTERS)."""
        rows = self.status_cache_repository.fetch_all(_TABLE)
        return {
            badge_type: sum(1 for r in rows if _matches(r, filters))
            for badge_type, filters in BADGE_FILTERS.items()
        }

    def get_details(self, badge_type=None):
        """Drilldown rows for one badge, or every row if `badge_type` is
        empty. None only for an unknown badge_type (vs. "no filter")."""
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

    @ttl_cache(15)
    def get_site_down_counts(self):
        """Badge counts for the "INC-WO Site Down" card."""
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
        """Rows behind the "INC-WO Site Down" card, optionally narrowed to
        one badge. Rows with no wo_id yet are dropped."""
        rows = self.status_cache_repository.fetch_all(_SITE_DOWN_TABLE)
        rows = [r for r in rows if r.get("wo_id")]
        if badge_type:
            rows = [r for r in rows if _matches_site_down_badge(r, badge_type)]
        return rows

    @ttl_cache(15)
    def get_resolved_count(self):
        """Single badge count for the "INC-WO Resolved" card — same
        rows as get_resolved_details(), just the count."""
        return len(self._resolved_rows())

    def get_resolved_details(self):
        """Every row behind the "INC-WO Resolved" card.

        An incident can have several WOs. inc_wo_resolved.sql already
        gives us every Resolved WO whose parent Incident is still
        In-Progress overall, but that's per-WO, not per-incident — if one
        sibling WO on the same incident isn't resolved yet, the incident's
        work isn't actually done, so none of its WOs belong on this card
        (checked against inc_wo_by_status, which has every WO regardless
        of status). Once every WO on an incident is resolved, only the
        latest one is kept — one row per incident, not one per historical
        WO."""
        return self._resolved_rows()

    def _resolved_rows(self):
        rows = self.resolved_cache_repository.fetch_all(_RESOLVED_TABLE)
        status_rows = self.status_cache_repository.fetch_all(_TABLE)
        fully_resolved = _fully_resolved_incident_ids(status_rows)

        latest_by_incident = {}
        for r in rows:
            incident_id = r.get("incident_numeric_id")
            if incident_id not in fully_resolved:
                continue
            current = latest_by_incident.get(incident_id)
            if current is None or _resolved_sort_key(r) > _resolved_sort_key(current):
                latest_by_incident[incident_id] = r

        result = list(latest_by_incident.values())
        result.sort(key=_resolved_sort_key, reverse=True)
        for r in result:
            r["wo_id"] = r.get("wo_id") or ""
        return result
