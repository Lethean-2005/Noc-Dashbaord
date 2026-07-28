"""Tests for IncidentService.get_details() — the Overall Dashboard's
"Incident" column drilldown. Real bug found and fixed here: the plain
"View Incidents" footer link (app/templates/dashboard/partials/cards.html)
passes no `type` query param, so dashboard.py's scope handler calls
get_details("") — which used to return None for ANY badge_type not in
BADGE_FILTERS, including "", so the button rendered the empty-state
template instead of every Incident row. Every other drilldown service in
this app (DgOnAlarmService, AlarmSiteDownService, etc.) treats an empty/
missing badge_type as "no filter, show everything" — these were the
outliers.
"""
from app.services.incident.incident_service import IncidentService


class FakeStatusRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


def _row(incident_status="New", category="BSS Hardware", overdue="No", **overrides):
    row = {
        "incident_id": "INC1", "incident_status": incident_status, "category": category,
        "overdue": overdue, "site_code": "S1", "occurred_at": "2026-01-01 00:00:00",
    }
    row.update(overrides)
    return row


def test_get_details_with_no_badge_type_returns_every_row():
    rows = [_row(incident_status="New"), _row(incident_status="In Progress")]
    svc = IncidentService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details("")

    assert len(result) == 2


def test_get_details_with_none_badge_type_returns_every_row():
    rows = [_row(incident_status="New"), _row(incident_status="In Progress")]
    svc = IncidentService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details(None)

    assert len(result) == 2


def test_get_details_filters_by_known_badge_type():
    rows = [_row(incident_status="New"), _row(incident_status="In Progress")]
    svc = IncidentService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details("new")

    assert len(result) == 1
    assert result[0]["incident_status"] == "New"


def test_get_details_with_unknown_badge_type_returns_none():
    rows = [_row()]
    svc = IncidentService(FakeStatusRepo(rows), FakeStatusRepo([]))

    assert svc.get_details("not_a_real_badge") is None
