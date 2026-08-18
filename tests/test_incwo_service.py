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
        "incident_id": "INC1",
        "wo_id": "WO1",
        "wo_status": wo_status,
        "incident_status": incident_status,
        "overdue": overdue,
        "site_code": "S1",
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


def _overdue_row(support_level, incident_status, incident_category="Customer Complaint"):
    return _row(
        overdue="Yes",
        support_level=support_level,
        incident_category=incident_category,
        incident_status=incident_status,
    )


def test_overdue_l2_includes_matching_row():
    rows = [_overdue_row("L2 On-Site", incident_status="In Progress")]
    svc = IncWoService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details("overdue_l2")

    assert len(result) == 1


def test_overdue_l3_excludes_resolved_parent_incident():
    rows = [_overdue_row("L3 Internal Support", incident_status="Resolved")]
    svc = IncWoService(FakeStatusRepo(rows), FakeStatusRepo([]))

    assert svc.get_details("overdue_l3") == []


def test_overdue_excludes_resolved_parent_incident():
    rows = [_overdue_row(support_level=None, incident_status="Resolved")]
    svc = IncWoService(FakeStatusRepo(rows), FakeStatusRepo([]))

    assert svc.get_details("overdue") == []


def test_overdue_includes_other_categories_even_when_resolved():
    """Only the Customer Complaint + Resolved combination is dropped — any
    other category is cached regardless of its parent Incident's status."""
    rows = [_overdue_row(support_level=None, incident_category="Power", incident_status="Resolved")]
    svc = IncWoService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details("overdue")

    assert len(result) == 1


def test_overdue_includes_customer_complaint_when_not_resolved():
    rows = [
        _overdue_row(
            support_level=None,
            incident_category="Customer Complaint",
            incident_status="In Progress",
        )
    ]
    svc = IncWoService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details("overdue")

    assert len(result) == 1


def test_overdue_l2_excludes_resolved_customer_complaint():
    rows = [
        _overdue_row(
            "L2 On-Site", incident_category="Customer Complaint", incident_status="Resolved"
        )
    ]
    svc = IncWoService(FakeStatusRepo(rows), FakeStatusRepo([]))

    assert svc.get_details("overdue_l2") == []


def test_overdue_l2_includes_other_categories_even_when_resolved():
    rows = [_overdue_row("L2 On-Site", incident_category="Power", incident_status="Resolved")]
    svc = IncWoService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details("overdue_l2")

    assert len(result) == 1


def test_get_site_down_details_drops_rows_with_no_wo_id():
    """A brand-new site_down WO (status='new') the source system hasn't
    assigned an ID to yet has no site/support level/fault description
    either — it'd only render as a row of dashes, so it's excluded here
    rather than shown blank."""
    rows = [
        _row(wo_id=None, site_grade="Silver"),
        _row(wo_id="WO2", site_grade="Silver"),
    ]
    svc = IncWoService(FakeStatusRepo([]), FakeStatusRepo([]))
    svc.status_cache_repository = FakeStatusRepo(rows)

    result = svc.get_site_down_details()

    assert len(result) == 1
    assert result[0]["wo_id"] == "WO2"


def test_get_site_down_details_badge_filter_still_applies_after_wo_id_drop():
    rows = [
        _row(wo_id=None, site_grade="Gold"),
        _row(wo_id="WO2", site_grade="Silver"),
        _row(wo_id="WO3", site_grade="Gold"),
    ]
    svc = IncWoService(FakeStatusRepo([]), FakeStatusRepo([]))
    svc.status_cache_repository = FakeStatusRepo(rows)

    result = svc.get_site_down_details("gold")

    assert len(result) == 1
    assert result[0]["wo_id"] == "WO3"
