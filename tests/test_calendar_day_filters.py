"""Tables and downloads share inclusive Cambodia calendar-date filters."""
import pytest

from app.routes.dashboard import _filter_by_occurred_at, _filter_by_wo_created_at
from app.utils.datetime import filter_calendar_dates


@pytest.mark.parametrize("field", ["occurred_at", "wo_created_at", "down_time"])
def test_full_day_includes_both_midnights_correctly(field):
    values = ["2026-11-10 23:59:59", "2026-11-11 00:00:00",
              "2026-11-11 23:59:59.999999", "2026-11-12 00:00:00", None]
    rows = [{field: value} for value in values]
    assert filter_calendar_dates(rows, field, "2026-11-11", "2026-11-11") == rows[1:3]


@pytest.mark.parametrize("apply,field", [(_filter_by_occurred_at, "occurred_at"),
                                        (_filter_by_wo_created_at, "wo_created_at")])
def test_route_helpers_use_complete_days(apply, field):
    rows = [{field: "2026-11-11 23:59:59.999999"}, {field: "2026-11-12 00:00:00"}]
    assert apply(rows, "2026-11-11", "2026-11-11") == rows[:1]


def test_no_filter_preserves_older_active_alarms():
    rows = [{"down_time": "2026-01-01 00:00:00"}, {"down_time": None}]
    assert filter_calendar_dates(rows, "down_time") is rows


def test_end_only_does_not_include_missing_dates():
    rows = [{"down_time": None}, {"down_time": "2026-11-11 23:59:59"}]
    assert filter_calendar_dates(rows, "down_time", date_to="2026-11-11") == rows[1:]


def test_invalid_date_does_not_raise_server_error():
    assert filter_calendar_dates([{"down_time": "2026-11-11"}], "down_time", "invalid") == []
