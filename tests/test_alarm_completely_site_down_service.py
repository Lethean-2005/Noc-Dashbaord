"""Tests for AlarmCompletelySiteDownService — the "Alarm Completely Site
Down" card on the Custom Dashboard. Narrows AlarmSiteDownService's own base
data (open ape_alarm rows matching SITE_DOWN_EVENTS) further to sites where
EVERY technology the site has (from site_technology_cache) is currently
down: gNodeB events -> 5G, eNodeB events -> 4G, NodeB/WCDMA BASE STATION
OUT OF USE -> 3G, CSL Fault/BTS O&M LINK FAILURE/Site Abis control link
broken -> 2G, and only NE Is Disconnected/NE3SWS AGENT NOT RESPONDING TO
REQUESTS/The link between the server and the ME is broken ("SRAN", the
shared baseband) count as taking down every technology the site has — an
exact mapping given directly by the user, not a substring heuristic.
"""
from app.services.alarm_site_down.alarm_completely_site_down_service import AlarmCompletelySiteDownService


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


def test_generic_event_counts_all_technologies_down():
    alarm_rows = [_alarm_row("S1", event_name="NE Is Disconnected")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g", "4g")
    svc = AlarmCompletelySiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows), FakeIncidentSiteDownRepo([]),
    )

    counts = svc.get_counts()

    assert counts["Gold"] == 1


def test_single_generation_alarm_does_not_cover_a_multi_tech_site():
    alarm_rows = [_alarm_row("S1", event_name="eNodeB is out of service")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g", "4g")
    svc = AlarmCompletelySiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows), FakeIncidentSiteDownRepo([]),
    )

    counts = svc.get_counts()

    assert counts["Gold"] == 0


def test_covering_every_generation_alarm_counts_as_completely_down():
    alarm_rows = [
        _alarm_row("S1", event_name="eNodeB is out of service"),
        _alarm_row("S1", event_name="NodeB is out of service"),
    ]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "silver"}]
    tech_rows = _tech_rows("S1", "3g", "4g")
    svc = AlarmCompletelySiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows), FakeIncidentSiteDownRepo([]),
    )

    counts = svc.get_counts()

    assert counts["Silver"] == 1


def test_csl_fault_maps_to_2g_not_sran():
    """CSL Fault/BTS O&M LINK FAILURE/Site Abis control link broken are 2G-
    specific, NOT part of the "covers everything" SRAN bucket — a site
    with 2G+4G alarming only CSL Fault should NOT count as completely
    down, since its 4G is still untouched."""
    alarm_rows = [_alarm_row("S1", event_name="CSL Fault")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g", "4g")
    svc = AlarmCompletelySiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows), FakeIncidentSiteDownRepo([]),
    )

    counts = svc.get_counts()

    assert counts["Gold"] == 0


def test_csl_fault_completely_covers_a_2g_only_site():
    alarm_rows = [_alarm_row("S1", event_name="BTS O&M LINK FAILURE")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g")
    svc = AlarmCompletelySiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows), FakeIncidentSiteDownRepo([]),
    )

    counts = svc.get_counts()

    assert counts["Gold"] == 1


def test_site_with_no_known_technology_inventory_never_counts():
    alarm_rows = [_alarm_row("S1", event_name="NE Is Disconnected")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = AlarmCompletelySiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo([]), FakeIncidentSiteDownRepo([]),
    )

    counts = svc.get_counts()

    assert counts["Gold"] == 0


def test_get_details_only_includes_completely_down_sites():
    alarm_rows = [
        _alarm_row("S1", event_name="NE Is Disconnected"),
        _alarm_row("S2", event_name="eNodeB is out of service"),
    ]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "bronze"},
    ]
    tech_rows = _tech_rows("S1", "2g", "4g") + _tech_rows("S2", "2g", "4g")
    svc = AlarmCompletelySiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows), FakeIncidentSiteDownRepo([]),
    )

    rows = svc.get_details()

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S1"


def test_get_details_includes_radio_technology():
    alarm_rows = [_alarm_row("S1", event_name="NE Is Disconnected")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g")
    svc = AlarmCompletelySiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows), FakeIncidentSiteDownRepo([]),
    )

    row = svc.get_details()[0]

    assert row["radio_technology"] == "SRAN"


def test_get_details_enriches_with_incident_site_down():
    alarm_rows = [_alarm_row("S1", event_name="NE Is Disconnected")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    tech_rows = _tech_rows("S1", "2g")
    incident_rows = [{"site_code": "S1", "incident_id": "INC1", "wo_id": "WO1"}]
    svc = AlarmCompletelySiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows), FakeIncidentSiteDownRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["incident_id"] == "INC1"
    assert row["wo_id"] == "WO1"


def test_get_details_filters_by_badge():
    alarm_rows = [
        _alarm_row("S1", event_name="NE Is Disconnected"),
        _alarm_row("S2", event_name="NE Is Disconnected"),
    ]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "bronze"},
    ]
    tech_rows = _tech_rows("S1", "4g") + _tech_rows("S2", "4g")
    svc = AlarmCompletelySiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows),
        FakeSiteTechnologyRepo(tech_rows), FakeIncidentSiteDownRepo([]),
    )

    rows = svc.get_details("Bronze")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S2"
