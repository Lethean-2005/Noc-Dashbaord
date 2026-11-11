"""Presentation-layer formatting helpers."""

# Every known Incident Status / INC-WO Status value -> its own distinct
# .status-badge CSS class (see app/static/css/components/status_links.css).
# One shared dict instead of the same status->class mapping copy-pasted
# across drilldown/incwo.html, incident_site_down.html, incwo_resolved.html,
# and incidents.html — that duplication is exactly how "Acknowledged" and
# "In Progress" once ended up sharing a color: one of the four copies never
# got updated when the others did.
_STATUS_BADGE_CLASSES = {
    "New": "status-new",
    "Assigned": "status-assigned",
    "Acknowledged": "status-acknowledged",
    "In Progress": "status-in-progress",
    "On Hold": "status-on-hold",
    "Resolved": "status-resolved",
    "Reopened": "status-reopened",
    "Returned": "status-returned",
}


def badge_color(count):
    """Green for a 0 alarm count, red otherwise — used by the live alarm cards."""
    return "badge-green" if not count else "badge-red"


def status_badge_class(status):
    """CSS class for an Incident Status / INC-WO Status badge. Falls back
    to "status-assigned" (gray) for any value not in _STATUS_BADGE_CLASSES,
    same default every template used before this was consolidated."""
    return _STATUS_BADGE_CLASSES.get(status, "status-assigned")


def site_code_display(value):
    """Display missing site codes without changing stored identifiers."""
    value = str(value).strip() if value is not None else ""
    return "_" if not value or set(value) == {"?"} else value
