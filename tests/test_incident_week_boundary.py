"""Boundaries must preserve complete Cambodia weeks in the source caches."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.database.sql_loader import load_queries

QUERIES = (
    "incident_closed_trend", "incident_created_trend", "incident_site_down_root_cause",
    "incident_site_down_duration_weekly", "incident_duration_weekly",
)


@pytest.mark.parametrize("name", QUERIES)
def test_source_query_converts_local_midnight_before_utc_comparison(name):
    query = load_queries(name)[name]
    assert "CAST(:since AS timestamp) AT TIME ZONE 'Asia/Phnom_Penh'" in query
    assert "AT TIME ZONE 'UTC'" in query
    assert ">= :since" not in query


def test_cambodia_midnight_includes_early_monday_records():
    local = ZoneInfo("Asia/Phnom_Penh")
    midnight = datetime(2026, 10, 19, tzinfo=local)
    utc_start = midnight.astimezone(timezone.utc).replace(tzinfo=None)
    assert utc_start == datetime(2026, 10, 18, 17)
    early_monday = datetime(2026, 10, 19, 1, tzinfo=local).astimezone(timezone.utc).replace(tzinfo=None)
    assert utc_start <= early_monday
    assert early_monday < datetime(2026, 10, 19)


def test_repeated_week_rankings_do_not_reuse_another_weeks_count():
    from app.services.incident.incident_service import IncidentService

    service = IncidentService()

    def rows(count):
        return list({"site_code": "TEST-SITE", "site": "Sample site"} for _ in range(count))

    for index in range(100):
        count = index % 7 + 1
        assert service._rank_site_down_codes(rows(count)) == [(("TEST-SITE", "Sample site"), count)]
