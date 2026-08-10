"""Tests for RanSiteDownService — the RAN Status card's "RAN Site Down"
column. Same completely-down definition as AlarmCompletelySiteDownService
(see app/utils/alarm_category.py's classify_site_technology_coverage() and
its own test suite for the full SRAN/generation-mapping edge cases) — this
suite focuses on what's specific to this service: Hub-Site badge naming
(not Hub) and the incident_site_down enrichment.
"""

from app.services.ran.ran_site_down_service import RanSiteDownService


class FakeApeAlarmRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeSiteRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeSiteTechnologyRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeIncidentSiteDownRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


def _alarm_row(site_code, event_name="NE Is Disconnected", **overrides):
    row = {
        "occurred_at": "2026-01-01 00:00:00",
        "event_name": event_name,
        "additional_info": "",
        "nms": "ZTE",
        "technology": "RAN",
        "site_code": site_code,
        "site_name": f"Site {site_code}",
        "occurrence_count": 1,
    }
    row.update(overrides)
    return row


def _tech_rows(site_code, *techs):
    return [{"site_code": site_code, "technology": t} for t in techs]


def test_get_counts_hub_site_takes_priority_over_grade():
    alarm_rows = [_alarm_row("S1", event_name="NE Is Disconnected")]
    site_rows = [{"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g")
    svc = RanSiteDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows),
        FakeIncidentSiteDownRepo([]),
    )

    counts = svc.get_counts()

    assert counts["Hub-Site"] == 1
    assert counts["Gold"] == 0


def test_partial_single_generation_alarm_does_not_count():
    alarm_rows = [_alarm_row("S1", event_name="eNodeB is out of service")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g", "4g")
    svc = RanSiteDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows),
        FakeIncidentSiteDownRepo([]),
    )

    counts = svc.get_counts()

    assert counts["Gold"] == 0


def test_get_details_includes_radio_technology_and_incident():
    alarm_rows = [_alarm_row("S1", event_name="NE Is Disconnected")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g")
    incident_rows = [{"site_code": "S1", "incident_id": "INC1", "wo_id": "WO1"}]
    svc = RanSiteDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows),
        FakeIncidentSiteDownRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["radio_technology"] == "SRAN"
    assert row["incident_id"] == "INC1"
    assert row["wo_id"] == "WO1"


def test_get_details_hides_co_occurring_single_generation_row_when_sran_present():
    """Real user-reported case: site with both a SRAN alarm and a 2G
    alarm open at once (SRAN alone already makes it completely down) —
    RAN Site Down should show only the SRAN row, not the 2G one too."""
    alarm_rows = [
        _alarm_row("S1", event_name="The link between the server and the ME is broken"),
        _alarm_row("S1", event_name="Site Abis control link broken"),
    ]
    site_rows = [{"standard_code": "S1", "hub_site": "Hub-Router", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g", "3g", "4g")
    svc = RanSiteDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows),
        FakeIncidentSiteDownRepo([]),
    )

    rows = svc.get_details()

    assert len(rows) == 1
    assert rows[0]["radio_technology"] == "SRAN"


def test_get_details_keeps_all_rows_when_completely_down_without_sran():
    """No SRAN alarm present — the site only reached completely-down by
    combining several single-generation alarms, so there's no single row
    representing "whole site down" and all of them still show."""
    alarm_rows = [
        _alarm_row("S1", event_name="eNodeB is out of service"),
        _alarm_row("S1", event_name="NodeB is out of service"),
    ]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "3g", "4g")
    svc = RanSiteDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows),
        FakeIncidentSiteDownRepo([]),
    )

    rows = svc.get_details()

    assert len(rows) == 2


def test_get_details_filters_by_hub_site_badge():
    alarm_rows = [
        _alarm_row("S1", event_name="NE Is Disconnected"),
        _alarm_row("S2", event_name="NE Is Disconnected"),
    ]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "bronze"},
    ]
    tech_rows = _tech_rows("S1", "4g") + _tech_rows("S2", "4g")
    svc = RanSiteDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows),
        FakeIncidentSiteDownRepo([]),
    )

    rows = svc.get_details("Hub-Site")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S1"


def test_get_details_excludes_hub_site_from_its_grade_badge():
    alarm_rows = [
        _alarm_row("S1", event_name="NE Is Disconnected"),
        _alarm_row("S2", event_name="NE Is Disconnected"),
    ]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "gold"},
    ]
    tech_rows = _tech_rows("S1", "4g") + _tech_rows("S2", "4g")
    svc = RanSiteDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows),
        FakeIncidentSiteDownRepo([]),
    )

    rows = svc.get_details("Gold")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S2"
