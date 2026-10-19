"""Tests for the Resolution Time card's "By Duration" popup —
dashboard.py's _resolution_duration_bucket_index()/
_resolution_time_duration_by_week()/_resolution_time_duration_details(),
and the "Resolution Time Duration" drilldown scope built on top of them.
Mirrors test_response_time_duration.py's own coverage.
"""

import pytest

from app.repositories.incident.incident_resolution_time_details_cache_repository import (
    IncidentResolutionTimeDetailsCacheRepository,
)
from app.routes.dashboard import (
    _RESOLUTION_DURATION_BUCKET_LABELS,
    _resolution_duration_bucket_index,
    _resolution_time_duration_by_week,
    _resolution_time_duration_details,
)


@pytest.fixture(autouse=True)
def _clear_resolution_time_details_cache():
    """See test_response_time_duration.py's own
    _clear_response_time_details_cache fixture for the full reasoning —
    same hazard, same fix, for the Resolution Time sibling table."""
    from app.routes import dashboard as dash_mod

    def _clear():
        dash_mod._resolution_time_details_cache_repository.__dict__.pop("_ttl_cache_fetch_all", None)

    _clear()
    yield
    _clear()


def test_bucket_index_boundaries():
    assert _resolution_duration_bucket_index(0) == 0
    assert _resolution_duration_bucket_index(1) == 0
    assert _resolution_duration_bucket_index(1.01) == 1
    assert _resolution_duration_bucket_index(14.99) == 1
    assert _resolution_duration_bucket_index(15) == 2
    assert _resolution_duration_bucket_index(59.99) == 2
    assert _resolution_duration_bucket_index(60) == 3
    assert _resolution_duration_bucket_index(239.99) == 3
    assert _resolution_duration_bucket_index(240) == 4
    assert _resolution_duration_bucket_index(1439.99) == 4
    assert _resolution_duration_bucket_index(1440) == 5
    assert _resolution_duration_bucket_index(100000) == 5


def _seed_resolution_time_details(app, rows):
    with app.app_context():
        normalized = [
            {
                "incident_id": r["incident_id"],
                "incident_numeric_id": i,
                "iso_week": r["iso_week"],
                "category": r.get("category", "Power"),
                "occurred_at": "2026-09-01 00:00:00",
                "resolved_at": "2026-09-01 00:01:00",
                "resolution_minutes": r["resolution_minutes"],
            }
            for i, r in enumerate(rows)
        ]
        IncidentResolutionTimeDetailsCacheRepository().replace_all(
            "incident_resolution_time_details", normalized
        )


def test_resolution_time_duration_by_week_buckets_and_defaults_to_latest_two_weeks(app):
    _seed_resolution_time_details(app, [
        {"incident_id": "INC1", "iso_week": "2026-W35", "resolution_minutes": 0.5},
        {"incident_id": "INC2", "iso_week": "2026-W36", "resolution_minutes": 0.5},
        {"incident_id": "INC3", "iso_week": "2026-W36", "resolution_minutes": 0.5},
        {"incident_id": "INC4", "iso_week": "2026-W36", "resolution_minutes": 2000},
        {"incident_id": "INC5", "iso_week": "2026-W37", "resolution_minutes": 0.5},
    ])

    with app.app_context():
        by_week = _resolution_time_duration_by_week()

    # Default picks the latest 2 weeks present (W36, W37), not W35.
    assert set(by_week.keys()) == {"2026-W36", "2026-W37"}
    w36 = by_week["2026-W36"]
    bucket_labels = [b["label"] for b in w36["buckets"]]
    assert bucket_labels == list(_RESOLUTION_DURATION_BUCKET_LABELS)
    # 2 incidents in <=1m bucket (index 0), 1 in >24h bucket (index 5,
    # since 2000 min > 1440 min = 24h).
    assert w36["buckets"][0]["count"] == 2
    assert w36["buckets"][5]["count"] == 1
    assert w36["buckets"][0]["badge_type"] == "lt1m_2026-W36"
    assert w36["week_label"] == "Wk 36"


def test_resolution_time_duration_by_week_respects_category_and_week_filter(app):
    _seed_resolution_time_details(app, [
        {"incident_id": "INC1", "iso_week": "2026-W36", "resolution_minutes": 0.5, "category": "Power"},
        {"incident_id": "INC2", "iso_week": "2026-W36", "resolution_minutes": 0.5, "category": "Customer Complaint"},
    ])

    with app.app_context():
        by_week = _resolution_time_duration_by_week(categories=["Power"], weeks=["2026-W36"])

    assert set(by_week.keys()) == {"2026-W36"}
    assert sum(b["count"] for b in by_week["2026-W36"]["buckets"]) == 1


def test_resolution_time_duration_by_week_empty_when_no_rows(app):
    with app.app_context():
        assert _resolution_time_duration_by_week() == {}


def test_resolution_time_duration_details_filters_by_badge_type(app):
    _seed_resolution_time_details(app, [
        {"incident_id": "INC1", "iso_week": "2026-W36", "resolution_minutes": 0.5},
        {"incident_id": "INC2", "iso_week": "2026-W36", "resolution_minutes": 2000},
        {"incident_id": "INC3", "iso_week": "2026-W37", "resolution_minutes": 0.5},
    ])

    with app.app_context():
        rows = _resolution_time_duration_details("lt1m_2026-W36")

    assert [r["incident_id"] for r in rows] == ["INC1"]
    assert rows[0]["resolution_display"] == "30s"


def test_resolution_time_duration_details_invalid_badge_type_returns_none(app):
    with app.app_context():
        assert _resolution_time_duration_details("not-a-real-badge-type") is None


def test_resolution_time_duration_details_empty_badge_type_returns_all_sorted(app):
    _seed_resolution_time_details(app, [
        {"incident_id": "SLOW", "iso_week": "2026-W36", "resolution_minutes": 2000},
        {"incident_id": "FAST", "iso_week": "2026-W36", "resolution_minutes": 0.5},
    ])

    with app.app_context():
        rows = _resolution_time_duration_details()

    assert [r["incident_id"] for r in rows] == ["FAST", "SLOW"]


def test_resolution_time_duration_drilldown_route_returns_200(client, app):
    _seed_resolution_time_details(app, [
        {"incident_id": "INC1", "iso_week": "2026-W36", "resolution_minutes": 0.5},
    ])

    response = client.get(
        "/drilldown?title=Test&label=%3C%3D1m&value=0"
        "&scope=Resolution+Time+Duration&type=lt1m_2026-W36"
    )

    assert response.status_code == 200
    assert b"INC1" in response.data


def test_resolution_time_duration_details_matches_multiple_comma_joined_tokens(app):
    _seed_resolution_time_details(app, [
        {"incident_id": "FAST", "iso_week": "2026-W36", "resolution_minutes": 0.5},
        {"incident_id": "MID", "iso_week": "2026-W36", "resolution_minutes": 5},
        {"incident_id": "SLOW", "iso_week": "2026-W36", "resolution_minutes": 2000},
    ])

    with app.app_context():
        rows = _resolution_time_duration_details("lt1m,1m_15m_2026-W36")

    assert {r["incident_id"] for r in rows} == {"FAST", "MID"}


def test_resolution_time_duration_drilldown_filters_by_category(client, app):
    _seed_resolution_time_details(app, [
        {"incident_id": "POWER", "iso_week": "2026-W36", "resolution_minutes": 0.5, "category": "Power"},
        {"incident_id": "CC", "iso_week": "2026-W36", "resolution_minutes": 0.5, "category": "Customer Complaint"},
    ])

    response = client.get(
        "/drilldown?title=Test&label=Test&value=0"
        "&scope=Resolution+Time+Duration&type=lt1m_2026-W36&category=Power"
    )

    assert response.status_code == 200
    assert b"POWER" in response.data
    assert b"CC" not in response.data


def test_resolution_time_duration_drilldown_duration_bucket_filter_overrides_original_bucket(client, app):
    _seed_resolution_time_details(app, [
        {"incident_id": "INC_FAST", "iso_week": "2026-W36", "resolution_minutes": 0.5},
        {"incident_id": "INC_MID", "iso_week": "2026-W36", "resolution_minutes": 5},
    ])

    response = client.get(
        "/drilldown?title=Test&label=Test&value=0"
        "&scope=Resolution+Time+Duration&type=lt1m_2026-W36"
        "&duration_bucket=1m-15m&week=2026-W36"
    )

    assert response.status_code == 200
    assert b"INC_MID" in response.data
    assert b"INC_FAST" not in response.data
