"""Tests for the SLA Compliance — Weekly Trends card's per-week popup —
dashboard.py's _sla_compliance_week_breakdowns().

Regression coverage for a real bug: not_graded_count used to be computed
as incident_count - resolution_known_count, but those two are anchored to
different weeks (created_at vs closed_at — see
incident_sla_compliance_weekly.sql's own header), so the subtraction
mixed two different cohorts of incidents and produced a number with no
real meaning. Confirmed live against a real week: the popup showed "1"
while the actual not-graded incidents (same category/priority,
issue_occurred_at in that week, overdue IS NULL) numbered 27. The fix
computes not_graded_count directly (issue_occurred_at-anchored, same as
incident_sla_compliance_details — what the popup's "Not Graded" link
drills down into), so it's now read straight from the cached row instead
of being derived.
"""

import pytest

from app.repositories.incident.incident_sla_compliance_details_cache_repository import (
    IncidentSlaComplianceDetailsCacheRepository,
)
from app.repositories.incident.incident_sla_compliance_weekly_cache_repository import (
    IncidentSlaComplianceWeeklyCacheRepository,
)
from app.routes.dashboard import (
    _sla_compliance_details,
    _sla_compliance_root_cause_breakdowns,
    _sla_compliance_week_breakdowns,
)


@pytest.fixture(autouse=True)
def _clear_sla_compliance_details_cache():
    """dashboard.py's _sla_compliance_details_cache_repository is a
    module-level singleton with its own @ttl_cache(15) (see that
    repository class) — same reasoning as
    test_response_time_duration.py's own fixture: without this, a test
    in this file running within 15s of a previous one would see that
    earlier test's seeded rows instead of (or mixed with) its own."""
    from app.routes import dashboard as dash_mod

    def _clear():
        dash_mod._sla_compliance_details_cache_repository.__dict__.pop("_ttl_cache_fetch_all", None)

    _clear()
    yield
    _clear()


def _seed_sla_compliance_weekly(app, rows):
    with app.app_context():
        IncidentSlaComplianceWeeklyCacheRepository().replace_all(
            "incident_sla_compliance_weekly", rows
        )


def test_not_graded_count_is_read_directly_not_derived_by_subtraction(app):
    # incident_count - resolution_known_count would give 44 - 43 = 1 here
    # (the old, wrong behavior) — but the real not_graded_count, computed
    # independently on a different week-anchor, is 27. This is the exact
    # real-world row (BSS Hardware/Low, a real week) that exposed the bug.
    _seed_sla_compliance_weekly(app, [{
        "iso_week": "2026-W44",
        "category": "BSS Hardware",
        "priority": "Low",
        "incident_count": 44,
        "response_met_count": 44,
        "response_sla_pct": 100.0,
        "resolution_known_count": 43,
        "resolution_met_count": 21,
        "resolution_sla_pct": 49.0,
        "not_graded_count": 27,
    }])

    with app.app_context():
        breakdowns = _sla_compliance_week_breakdowns()

    row = breakdowns["2026-W44"]["rows"][0]
    assert row["not_graded_count"] == 27
    assert row["not_graded_count"] != row["incident_count"] - row["resolution_known_count"]


def test_not_graded_count_none_defaults_to_zero(app):
    _seed_sla_compliance_weekly(app, [{
        "iso_week": "2026-W44",
        "category": "BSS Hardware",
        "priority": "Low",
        "incident_count": 5,
        "response_met_count": 5,
        "response_sla_pct": 100.0,
        "resolution_known_count": 5,
        "resolution_met_count": 5,
        "resolution_sla_pct": 100.0,
        "not_graded_count": None,
    }])

    with app.app_context():
        breakdowns = _sla_compliance_week_breakdowns()

    assert breakdowns["2026-W44"]["rows"][0]["not_graded_count"] == 0


def _seed_sla_compliance_details(app, rows):
    with app.app_context():
        normalized = [
            {
                "incident_id": r["incident_id"],
                "incident_numeric_id": i,
                "iso_week": r.get("iso_week"),
                "response_iso_week": r.get("response_iso_week"),
                "resolution_iso_week": r.get("resolution_iso_week"),
                "category": r.get("category", "BSS Hardware"),
                "priority": r.get("priority", "Low"),
                "support_level": "L1 NOC",
                "site_grade": "",
                "occurred_at": "2026-10-01 00:00:00",
                "overdue_response": r.get("overdue_response"),
                "overdue": r.get("overdue"),
                "root_cause_category": r.get("root_cause_category", "Not Assigned"),
            }
            for i, r in enumerate(rows)
        ]
        IncidentSlaComplianceDetailsCacheRepository().replace_all(
            "incident_sla_compliance_details", normalized
        )


def test_resolution_met_drilldown_filters_by_resolution_iso_week_not_iso_week(app):
    # This incident OCCURRED in W40, but was CLOSED (resolution graded)
    # in W44 — same situation that exposed the real bug: a popup cell
    # for Resolution Met W44 (closed_at-anchored, matching
    # incident_sla_compliance_weekly.sql's own resolution_stats CTE)
    # must find this incident via resolution_iso_week, not iso_week
    # (issue_occurred_at-anchored) — filtering on iso_week="2026-W44"
    # would miss it entirely, since it occurred in W40.
    _seed_sla_compliance_details(app, [
        {
            "incident_id": "INC-SLOW-RESOLVE",
            "iso_week": "2026-W40",
            "response_iso_week": "2026-W40",
            "resolution_iso_week": "2026-W44",
            "overdue_response": 0,
            "overdue": 0,
        },
        {
            "incident_id": "INC-OCCURRED-W44",
            "iso_week": "2026-W44",
            "response_iso_week": "2026-W44",
            "resolution_iso_week": None,
            "overdue_response": 0,
            "overdue": None,
        },
    ])

    with app.app_context():
        res_met_rows = _sla_compliance_details("res_met_2026-W44")

    assert [r["incident_id"] for r in res_met_rows] == ["INC-SLOW-RESOLVE"]


def test_response_met_drilldown_filters_by_response_iso_week(app):
    _seed_sla_compliance_details(app, [
        {
            "incident_id": "INC-CREATED-W44",
            "iso_week": "2026-W43",
            "response_iso_week": "2026-W44",
            "resolution_iso_week": None,
            "overdue_response": 0,
            "overdue": None,
        },
        {
            "incident_id": "INC-CREATED-W43",
            "iso_week": "2026-W43",
            "response_iso_week": "2026-W43",
            "resolution_iso_week": None,
            "overdue_response": 0,
            "overdue": None,
        },
    ])

    with app.app_context():
        resp_met_rows = _sla_compliance_details("resp_met_2026-W44")

    assert [r["incident_id"] for r in resp_met_rows] == ["INC-CREATED-W44"]


def test_root_cause_breakdown_counts_incidents_per_category_for_the_week(app):
    # Requested live (SLA Compliance — Weekly Trends card): "how much
    # from each root cause category" for a given week — a second,
    # separate per-week popup table alongside the existing
    # Category/Priority one, built from the SAME per-incident cache
    # (incident_sla_compliance_details) but counting by
    # root_cause_category instead.
    _seed_sla_compliance_details(app, [
        {
            "incident_id": "INC-1", "iso_week": "2026-W44",
            "root_cause_category": "EDC Power outage", "overdue": 1,
        },
        {
            "incident_id": "INC-2", "iso_week": "2026-W44",
            "root_cause_category": "EDC Power outage", "overdue": 1,
        },
        {
            "incident_id": "INC-3", "iso_week": "2026-W44",
            "root_cause_category": "Lightning Strike", "overdue": 1,
        },
        {
            "incident_id": "INC-4", "iso_week": "2026-W44",
            "root_cause_category": None, "overdue": 1,  # still open / no RCA set yet
        },
        {
            "incident_id": "INC-OTHER-WEEK", "iso_week": "2026-W43",
            "root_cause_category": "EDC Power outage", "overdue": 1,
        },
    ])

    with app.app_context():
        breakdowns = _sla_compliance_root_cause_breakdowns()

    week44 = breakdowns["2026-W44"]
    # Sorted by count descending — "EDC Power outage" (2) before the
    # two 1-count categories.
    assert week44[0] == {"category": "EDC Power outage", "count": 2, "response_not_met": 0, "resolution_not_met": 2}
    assert {"category": "Lightning Strike", "count": 1, "response_not_met": 0, "resolution_not_met": 1} in week44
    assert {"category": "Not Assigned", "count": 1, "response_not_met": 0, "resolution_not_met": 1} in week44
    assert len(week44) == 3
    # Week 43's own single incident doesn't leak into week 44's counts.
    assert breakdowns["2026-W43"] == [{"category": "EDC Power outage", "count": 1, "response_not_met": 0, "resolution_not_met": 1}]


def test_root_cause_drilldown_matches_occurrence_week_and_selected_categories(app):
    _seed_sla_compliance_details(app, [
        {"incident_id": "INC-MATCH", "iso_week": "2026-W44", "response_iso_week": "2026-W43", "root_cause_category": "EDC Power outage", "overdue": 1, "category": "BSS Hardware"},
        {"incident_id": "INC-OTHER-CAUSE", "iso_week": "2026-W44", "root_cause_category": "Lightning Strike", "overdue": 1},
        {"incident_id": "INC-OTHER-WEEK", "iso_week": "2026-W43", "response_iso_week": "2026-W44", "root_cause_category": "EDC Power outage", "overdue": 1},
        {"incident_id": "INC-OTHER-CATEGORY", "iso_week": "2026-W44", "root_cause_category": "EDC Power outage", "overdue": 1, "category": "IP Core"},
    ])
    with app.test_request_context('/?root_cause=EDC+Power+outage&sla_compliance_category=BSS+Hardware'):
        breakdown = _sla_compliance_root_cause_breakdowns(["BSS Hardware"])
        rows = _sla_compliance_details("root_cause_2026-W44")
    count = next(row["count"] for row in breakdown["2026-W44"] if row["category"] == "EDC Power outage")
    assert count == len(rows) == 1
    assert rows[0]["incident_id"] == "INC-MATCH"


def test_missing_root_cause_drilldown_includes_blank_and_null(app):
    _seed_sla_compliance_details(app, [
        {"incident_id": "INC-NULL", "iso_week": "2026-W44", "root_cause_category": None, "overdue": 1},
        {"incident_id": "INC-BLANK", "iso_week": "2026-W44", "root_cause_category": "  ", "overdue": 1},
        {"incident_id": "INC-NAMED", "iso_week": "2026-W44", "root_cause_category": "Lightning Strike", "overdue": 1},
    ])
    with app.test_request_context('/?root_cause=Not+Assigned'):
        rows = _sla_compliance_details("root_cause_2026-W44")
        breakdown = _sla_compliance_root_cause_breakdowns()
    assert {row["incident_id"] for row in rows} == {"INC-NULL", "INC-BLANK"}
    assert all(row["root_cause_category"] == "Not Assigned" for row in rows)
    assert {"category": "Not Assigned", "count": 2, "response_not_met": 0, "resolution_not_met": 2} in breakdown["2026-W44"]


def test_root_cause_drilldown_export_preserves_filters(app, client):
    from urllib.parse import urlencode
    _seed_sla_compliance_details(app, [
        {"incident_id": "INC-INCLUDED", "iso_week": "2026-W44", "root_cause_category": "Power & Battery", "overdue": 1, "category": "BSS Hardware"},
        {"incident_id": "INC-EXCLUDED", "iso_week": "2026-W44", "root_cause_category": "Power & Battery", "overdue": 1, "category": "IP Core"},
    ])
    args = {"scope": "SLA Compliance", "type": "root_cause_2026-W44", "root_cause": "Power & Battery", "sla_compliance_category": "BSS Hardware"}
    response = client.get('/drilldown?' + urlencode(args))
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'INC-INCLUDED' in html
    assert 'INC-EXCLUDED' not in html
    from html.parser import HTMLParser
    class Links(HTMLParser):
        urls = []
        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                self.urls.extend(value for name, value in attrs if name == 'href' and '/drilldown/download' in value)
    links = Links()
    links.feed(html)
    assert len(links.urls) == 1
    exported = client.get(links.urls[0])
    assert exported.status_code == 200
    assert 'INC-INCLUDED' in exported.get_data(as_text=True)
    assert 'INC-EXCLUDED' not in exported.get_data(as_text=True)


def test_root_cause_counts_response_and_resolution_failures_separately(app):
    _seed_sla_compliance_details(app, [
        {"incident_id": "MISSED", "iso_week": "2026-W44", "root_cause_category": "Power", "overdue": 1},
        {"incident_id": "MET", "iso_week": "2026-W44", "root_cause_category": "Power", "overdue": 0, "overdue_response": 1},
        {"incident_id": "UNGRADED", "iso_week": "2026-W44", "root_cause_category": "Power", "overdue": None},
    ])
    with app.test_request_context('/?root_cause=Power'):
        breakdown = _sla_compliance_root_cause_breakdowns()
        rows = _sla_compliance_details("root_cause_2026-W44")
    assert breakdown["2026-W44"] == [{"category": "Power", "count": 2, "response_not_met": 1, "resolution_not_met": 1}]
    assert {r["incident_id"] for r in rows} == {"MISSED", "MET"}
    with app.test_request_context('/?root_cause=Power'):
        assert [r["incident_id"] for r in _sla_compliance_details("root_cause_resp_2026-W44")] == ["MET"]
        assert [r["incident_id"] for r in _sla_compliance_details("root_cause_res_2026-W44")] == ["MISSED"]
