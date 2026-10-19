"""Tests for the Response Time card's "By Duration" popup —
dashboard.py's _response_duration_bucket_index()/
_response_time_duration_by_week()/_response_time_duration_details(),
and the "Response Time Duration" drilldown scope built on top of them.
"""

import pytest

from app.repositories.incident.incident_response_time_details_cache_repository import (
    IncidentResponseTimeDetailsCacheRepository,
)
from app.routes.dashboard import (
    _RESPONSE_DURATION_BUCKET_LABELS,
    _response_duration_bucket_index,
    _response_time_duration_by_week,
    _response_time_duration_details,
)


@pytest.fixture(autouse=True)
def _clear_response_time_details_cache():
    """dashboard.py's _response_time_details_cache_repository is a
    module-level singleton reused for this whole pytest session (unlike
    the fresh SQLite file each `app` fixture gets) — its 15s
    @ttl_cache(15) doesn't know when a DIFFERENT test's `app` fixture
    swapped in a completely different database, so without this a test
    running within 15s of a previous one in this file would see that
    earlier test's stale cached result instead of its own (possibly
    empty) data. Clearing before AND after covers both directions:
    this test reading a previous one's leftovers, and the next test
    file reading this one's."""
    from app.routes import dashboard as dash_mod

    def _clear():
        dash_mod._response_time_details_cache_repository.__dict__.pop("_ttl_cache_fetch_all", None)

    _clear()
    yield
    _clear()


def test_bucket_index_boundaries():
    assert _response_duration_bucket_index(0) == 0
    assert _response_duration_bucket_index(1) == 0
    assert _response_duration_bucket_index(1.01) == 1
    assert _response_duration_bucket_index(14.99) == 1
    assert _response_duration_bucket_index(15) == 2
    assert _response_duration_bucket_index(59.99) == 2
    assert _response_duration_bucket_index(60) == 3
    assert _response_duration_bucket_index(239.99) == 3
    assert _response_duration_bucket_index(240) == 4
    assert _response_duration_bucket_index(1439.99) == 4
    assert _response_duration_bucket_index(1440) == 5
    assert _response_duration_bucket_index(100000) == 5


def _seed_response_time_details(app, rows):
    with app.app_context():
        normalized = [
            {
                "incident_id": r["incident_id"],
                "incident_numeric_id": i,
                "iso_week": r["iso_week"],
                "category": r.get("category", "Power"),
                "occurred_at": "2026-09-01 00:00:00",
                "took_in_progress_at": "2026-09-01 00:01:00",
                "response_minutes": r["response_minutes"],
            }
            for i, r in enumerate(rows)
        ]
        IncidentResponseTimeDetailsCacheRepository().replace_all(
            "incident_response_time_details", normalized
        )


def test_response_time_duration_by_week_buckets_and_defaults_to_latest_two_weeks(app):
    _seed_response_time_details(app, [
        {"incident_id": "INC1", "iso_week": "2026-W35", "response_minutes": 0.5},
        {"incident_id": "INC2", "iso_week": "2026-W36", "response_minutes": 0.5},
        {"incident_id": "INC3", "iso_week": "2026-W36", "response_minutes": 0.5},
        {"incident_id": "INC4", "iso_week": "2026-W36", "response_minutes": 20},
        {"incident_id": "INC5", "iso_week": "2026-W37", "response_minutes": 0.5},
    ])

    with app.app_context():
        by_week = _response_time_duration_by_week()

    # Default picks the latest 2 weeks present (W36, W37), not W35.
    assert set(by_week.keys()) == {"2026-W36", "2026-W37"}
    w36 = by_week["2026-W36"]
    bucket_labels = [b["label"] for b in w36["buckets"]]
    assert bucket_labels == list(_RESPONSE_DURATION_BUCKET_LABELS)
    # 2 incidents in <=1m bucket (index 0), 1 in 15m-1h bucket (index 2).
    assert w36["buckets"][0]["count"] == 2
    assert w36["buckets"][2]["count"] == 1
    assert w36["buckets"][0]["badge_type"] == "lt1m_2026-W36"
    assert w36["week_label"] == "Wk 36"


def test_response_time_duration_by_week_respects_category_and_week_filter(app):
    _seed_response_time_details(app, [
        {"incident_id": "INC1", "iso_week": "2026-W36", "response_minutes": 0.5, "category": "Power"},
        {"incident_id": "INC2", "iso_week": "2026-W36", "response_minutes": 0.5, "category": "Customer Complaint"},
    ])

    with app.app_context():
        by_week = _response_time_duration_by_week(categories=["Power"], weeks=["2026-W36"])

    assert set(by_week.keys()) == {"2026-W36"}
    assert sum(b["count"] for b in by_week["2026-W36"]["buckets"]) == 1


def test_response_time_duration_by_week_empty_when_no_rows(app):
    with app.app_context():
        assert _response_time_duration_by_week() == {}


def test_response_time_duration_details_filters_by_badge_type(app):
    _seed_response_time_details(app, [
        {"incident_id": "INC1", "iso_week": "2026-W36", "response_minutes": 0.5},
        {"incident_id": "INC2", "iso_week": "2026-W36", "response_minutes": 20},
        {"incident_id": "INC3", "iso_week": "2026-W37", "response_minutes": 0.5},
    ])

    with app.app_context():
        rows = _response_time_duration_details("lt1m_2026-W36")

    assert [r["incident_id"] for r in rows] == ["INC1"]
    assert rows[0]["response_display"] == "30s"


def test_response_time_duration_details_invalid_badge_type_returns_none(app):
    with app.app_context():
        assert _response_time_duration_details("not-a-real-badge-type") is None


def test_response_time_duration_details_empty_badge_type_returns_all_sorted(app):
    _seed_response_time_details(app, [
        {"incident_id": "SLOW", "iso_week": "2026-W36", "response_minutes": 20},
        {"incident_id": "FAST", "iso_week": "2026-W36", "response_minutes": 0.5},
    ])

    with app.app_context():
        rows = _response_time_duration_details()

    assert [r["incident_id"] for r in rows] == ["FAST", "SLOW"]


def test_response_time_duration_drilldown_route_returns_200(client, app):
    _seed_response_time_details(app, [
        {"incident_id": "INC1", "iso_week": "2026-W36", "response_minutes": 0.5},
    ])

    response = client.get(
        "/drilldown?title=Congestion&label=%3C%3D1m&value=0"
        "&scope=Response+Time+Duration&type=lt1m_2026-W36"
    )

    assert response.status_code == 200
    assert b"INC1" in response.data


def test_response_time_duration_details_matches_multiple_comma_joined_tokens(app):
    _seed_response_time_details(app, [
        {"incident_id": "FAST", "iso_week": "2026-W36", "response_minutes": 0.5},
        {"incident_id": "MID", "iso_week": "2026-W36", "response_minutes": 5},
        {"incident_id": "SLOW", "iso_week": "2026-W36", "response_minutes": 20},
    ])

    with app.app_context():
        rows = _response_time_duration_details("lt1m,1m_15m_2026-W36")

    # ≤1m (FAST) and 1m-15m (MID) both match; 15m-1h (SLOW's bucket) doesn't.
    assert {r["incident_id"] for r in rows} == {"FAST", "MID"}


def test_response_time_duration_drilldown_filters_by_category(client, app):
    _seed_response_time_details(app, [
        {"incident_id": "POWER", "iso_week": "2026-W36", "response_minutes": 0.5, "category": "Power"},
        {"incident_id": "CC", "iso_week": "2026-W36", "response_minutes": 0.5, "category": "Customer Complaint"},
    ])

    response = client.get(
        "/drilldown?title=Test&label=Test&value=0"
        "&scope=Response+Time+Duration&type=lt1m_2026-W36&category=Power"
    )

    assert response.status_code == 200
    assert b"POWER" in response.data
    assert b"CC" not in response.data


def test_response_time_duration_drilldown_duration_bucket_filter_overrides_original_bucket(client, app):
    # Opened via a popup click on the ≤1m bucket (INC_FAST), but the
    # page's own "Filter by Duration" checkboxes were then changed to
    # 1m-15m instead — the checkboxes (duration_bucket + week) should
    # win over the original ≤1m from `type`.
    _seed_response_time_details(app, [
        {"incident_id": "INC_FAST", "iso_week": "2026-W36", "response_minutes": 0.5},
        {"incident_id": "INC_MID", "iso_week": "2026-W36", "response_minutes": 5},
    ])

    response = client.get(
        "/drilldown?title=Test&label=Test&value=0"
        "&scope=Response+Time+Duration&type=lt1m_2026-W36"
        "&duration_bucket=1m-15m&week=2026-W36"
    )

    assert response.status_code == 200
    assert b"INC_MID" in response.data
    assert b"INC_FAST" not in response.data
