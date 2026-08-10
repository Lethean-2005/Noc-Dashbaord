"""Tests for RanTechDownService — the RAN Status card's "RAN Tech Down"
column, the complement of RanSiteDownService: a site counts here only when
ONE specific technology is down (a generation-specific alarm present, but
not covering the site's whole inventory, and no SRAN alarm either) — never
both this and RAN Site Down for the same site. See
app/utils/alarm_category.py's classify_site_technology_coverage() for the
shared split and its own test suite for the full edge cases.
"""

from app.services.ran.ran_tech_down_service import RanTechDownService


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


def _alarm_row(site_code, event_name="eNodeB is out of service", **overrides):
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


def test_single_generation_alarm_on_multi_tech_site_counts():
    alarm_rows = [_alarm_row("S1", event_name="eNodeB is out of service")]
    site_rows = [{"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g", "4g")
    svc = RanTechDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows),
        FakeIncidentSiteDownRepo([]),
    )

    counts = svc.get_counts()

    assert counts["Hub-Site"] == 1
    assert counts["Gold"] == 0


def test_sran_alarm_never_counts_as_tech_down():
    """A SRAN alarm takes down every technology — that's RAN Site Down's
    territory, never RAN Tech Down's, even on a multi-tech site."""
    alarm_rows = [_alarm_row("S1", event_name="NE Is Disconnected")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g", "4g")
    svc = RanTechDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows),
        FakeIncidentSiteDownRepo([]),
    )

    counts = svc.get_counts()

    assert counts["Gold"] == 0


def test_single_tech_site_fully_covered_is_not_tech_down():
    """A single-generation alarm that happens to cover the site's ENTIRE
    inventory (a 2G-only site) is completely down, not partially — RAN
    Site Down's territory, not RAN Tech Down's."""
    alarm_rows = [_alarm_row("S1", event_name="BTS O&M LINK FAILURE")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g")
    svc = RanTechDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows),
        FakeIncidentSiteDownRepo([]),
    )

    counts = svc.get_counts()

    assert counts["Gold"] == 0


def test_get_details_includes_radio_technology_and_incident():
    alarm_rows = [_alarm_row("S1", event_name="eNodeB is out of service")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g", "4g")
    incident_rows = [{"site_code": "S1", "incident_id": "INC1", "wo_id": "WO1"}]
    svc = RanTechDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows),
        FakeIncidentSiteDownRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["radio_technology"] == "4G"
    assert row["incident_id"] == "INC1"
    assert row["wo_id"] == "WO1"


def test_get_details_filters_by_grade_badge():
    alarm_rows = [
        _alarm_row("S1", event_name="eNodeB is out of service"),
        _alarm_row("S2", event_name="CSL Fault"),
    ]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "bronze"},
    ]
    tech_rows = _tech_rows("S1", "2g", "4g") + _tech_rows("S2", "2g", "4g")
    svc = RanTechDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows),
        FakeIncidentSiteDownRepo([]),
    )

    rows = svc.get_details("Bronze")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S2"
