"""Tests for IncWoService.get_details() — the Overall Dashboard's "INC-WO"
column drilldown. Same real bug as test_incident_service.py: the plain
"View INC-WO" footer link passes no `type` query param, so get_details("")
used to return None for ANY badge_type not in BADGE_FILTERS, including "",
rendering the empty-state template instead of every INC-WO row.
"""
from app.services.incwo.incwo_service import IncWoService


class FakeStatusRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


def _row(wo_status="New", incident_status="New", overdue="No", **overrides):
    row = {
        "incident_id": "INC1", "wo_id": "WO1", "wo_status": wo_status,
        "incident_status": incident_status, "overdue": overdue, "site_code": "S1",
    }
    row.update(overrides)
    return row


def test_get_details_with_no_badge_type_returns_every_row():
    rows = [_row(wo_status="New"), _row(wo_status="Assigned")]
    svc = IncWoService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details("")

    assert len(result) == 2


def test_get_details_with_none_badge_type_returns_every_row():
    rows = [_row(wo_status="New"), _row(wo_status="Assigned")]
    svc = IncWoService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details(None)

    assert len(result) == 2


def test_get_details_filters_by_known_badge_type():
    rows = [_row(wo_status="New"), _row(wo_status="Assigned")]
    svc = IncWoService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details("new")

    assert len(result) == 1
    assert result[0]["wo_status"] == "New"


def test_get_details_with_unknown_badge_type_returns_none():
    rows = [_row()]
    svc = IncWoService(FakeStatusRepo(rows), FakeStatusRepo([]))

    assert svc.get_details("not_a_real_badge") is None
