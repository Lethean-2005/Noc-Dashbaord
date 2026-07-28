"""Tests for dashboard.py's _filter_by_occurred_at() — the shared
"Occurred At" date-range filter applied to every _SCOPE_HANDLERS-routed
drilldown listed in _DATE_FILTERABLE_SCOPES (Incident, Incident Site Down,
VVIP Site, RAN Main AC Alarm, RAN Site Down, RAN Tech Down, Alarm DG On,
Alarm Site Down, Alarm Completely Site Down, Mentor sites/Mentor Site).
ISP POP/EZE/TCT/IT NODE keep filtering Down Time instead, via their own
separate _fetch_rows() path — not covered here.
"""
from app.routes.dashboard import _DATE_FILTERABLE_SCOPES, _filter_by_occurred_at


def _row(occurred_at):
    return {"occurred_at": occurred_at, "site_code": "S1"}


def test_no_filter_returns_every_row():
    rows = [_row("2026-01-01 00:00:00"), _row("2026-02-01 00:00:00")]

    result = _filter_by_occurred_at(rows, "", "")

    assert len(result) == 2


def test_date_from_excludes_earlier_rows():
    rows = [_row("2026-01-01 00:00:00"), _row("2026-02-01 00:00:00")]

    result = _filter_by_occurred_at(rows, "2026-01-15", "")

    assert len(result) == 1
    assert result[0]["occurred_at"] == "2026-02-01 00:00:00"


def test_date_to_excludes_later_rows():
    rows = [_row("2026-01-01 00:00:00"), _row("2026-02-01 00:00:00")]

    result = _filter_by_occurred_at(rows, "", "2026-01-15")

    assert len(result) == 1
    assert result[0]["occurred_at"] == "2026-01-01 00:00:00"


def test_date_range_is_inclusive_on_both_ends():
    rows = [_row("2026-01-01 08:00:00")]

    result = _filter_by_occurred_at(rows, "2026-01-01", "2026-01-01")

    assert len(result) == 1


def test_row_with_no_occurred_at_is_excluded_by_any_bound():
    rows = [{"occurred_at": "", "site_code": "S1"}]

    result = _filter_by_occurred_at(rows, "2026-01-01", "")

    assert result == []


def test_date_filterable_scopes_excludes_inc_wo_and_alarm_scopes():
    """INC-WO/INC-WO Resolved have no occurred_at field (only INC-WO
    Created At / Resolved At) — ISP POP/EZE/TCT/IT NODE aren't routed
    through _SCOPE_HANDLERS at all, so neither belongs in this set."""
    assert "INC-WO" not in _DATE_FILTERABLE_SCOPES
    assert "INC-WO Resolved" not in _DATE_FILTERABLE_SCOPES
    assert "ISP POP" not in _DATE_FILTERABLE_SCOPES


def test_date_filterable_scopes_includes_expected_scopes():
    for scope in (
        "Incident", "Incident Site Down", "VVIP Site", "RAN Main AC Alarm",
        "RAN Site Down", "RAN Tech Down", "Alarm DG On", "Alarm Site Down",
        "Alarm Completely Site Down", "Mentor sites", "Mentor Site",
    ):
        assert scope in _DATE_FILTERABLE_SCOPES
