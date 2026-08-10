"""Tests for AlarmSiteDownService — the "Alarm Site Down" card on the
Custom Dashboard. Same architecture as test_dg_on_alarm_service.py: reads
the already-synced ape_alarm cache (no Postgres call of its own), narrows
to alarms whose event_name is an exact (case-insensitive) match against
app/utils/alarm_category.py's SITE_DOWN_EVENTS, buckets by
Hub/Diamond/Gold/Silver/Bronze from site_cache (Hub takes priority: a hub
site counts only there, never also under its grade), and enriches drilldown rows with the site's
current Incident/INC-WO from the incident_site_down cache — already scoped
to Category = Site Down, Status != Closed, Cleared Alarm Received = FALSE
(see app/database/queries/incident_site_down.sql), so no extra category filtering
is needed here.
"""

from app.services.alarm_site_down.alarm_site_down_service import AlarmSiteDownService


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


def test_get_counts_matches_site_down_event_name():
    alarm_rows = [
        _alarm_row("S1", event_name="NE Is Disconnected"),
        _alarm_row("S1", event_name="Door Alarm"),
    ]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = AlarmSiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentSiteDownRepo([])
    )

    counts = svc.get_counts()

    assert counts["Gold"] == 1


def test_get_counts_matches_newer_gnodeb_variants():
    alarm_rows = [
        _alarm_row("S1", event_name="gNodeB Out of Service"),
        _alarm_row("S2", event_name="gNodeB DU out-of-service"),
    ]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "silver"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "bronze"},
    ]
    svc = AlarmSiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentSiteDownRepo([])
    )

    counts = svc.get_counts()

    assert counts["Silver"] == 1
    assert counts["Bronze"] == 1


def test_get_counts_ignores_non_site_down_events():
    alarm_rows = [_alarm_row("S1", event_name="Main Failure Alarm")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = AlarmSiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentSiteDownRepo([])
    )

    counts = svc.get_counts()

    assert counts["Gold"] == 0


def test_get_counts_hub_takes_priority_over_grade_for_the_same_alarm():
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "diamond"}]
    svc = AlarmSiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentSiteDownRepo([])
    )

    counts = svc.get_counts()

    assert counts["Hub"] == 1
    assert counts["Diamond"] == 0


def test_get_details_enriches_rows_with_current_site_down_incident():
    """incident_site_down is already scoped to Status != Closed (see
    incident_site_down.sql) — a Resolved-but-not-Closed incident still matches,
    unlike incident_by_status which excludes 'resolved' entirely."""
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    incident_rows = [
        {
            "site_code": "S1",
            "incident_id": "INC1",
            "wo_id": "WO1",
            "wo_status": "New",
            "incident_status": "Resolved",
        }
    ]
    svc = AlarmSiteDownService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeIncidentSiteDownRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["incident_id"] == "INC1"
    assert row["wo_id"] == "WO1"


def test_get_details_includes_radio_technology():
    alarm_rows = [_alarm_row("S1", event_name="eNodeB is out of service")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = AlarmSiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentSiteDownRepo([])
    )

    row = svc.get_details()[0]

    assert row["radio_technology"] == "4G"


def test_get_details_translates_nms_code():
    alarm_rows = [_alarm_row("S1", nms="7")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = AlarmSiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentSiteDownRepo([])
    )

    row = svc.get_details()[0]

    assert row["nms"] == "Nokia"


def test_get_details_filters_by_hub_badge():
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2")]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "bronze"},
    ]
    svc = AlarmSiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentSiteDownRepo([])
    )

    rows = svc.get_details("Hub")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S1"


def test_get_details_excludes_hub_from_its_grade_badge():
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2")]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "gold"},
    ]
    svc = AlarmSiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentSiteDownRepo([])
    )

    rows = svc.get_details("Gold")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S2"


def test_get_details_excludes_alarms_with_no_matching_site_cache_record():
    """A site missing from site_cache (off_air sites are excluded there —
    see site_cache.sql — or a site_code that never resolved to any real
    site) should not appear at all, rather than showing up with a blank
    Site Name/Hub/Grade/Province."""
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2"), _alarm_row("")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = AlarmSiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentSiteDownRepo([])
    )

    rows = svc.get_details()

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S1"


def test_get_counts_excludes_alarms_with_no_matching_site_cache_record():
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = AlarmSiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentSiteDownRepo([])
    )

    counts = svc.get_counts()

    assert counts["Gold"] == 1


def test_get_details_filters_by_grade_badge():
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2")]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "bronze"},
    ]
    svc = AlarmSiteDownService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentSiteDownRepo([])
    )

    rows = svc.get_details("Bronze")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S2"
