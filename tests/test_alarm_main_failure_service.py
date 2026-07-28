"""Tests for AlarmMainFailureService — the "Alarm Main Failure" card on the
Custom Dashboard. Same architecture as test_dg_on_alarm_service.py: reads
the already-synced ape_alarm cache (no Postgres call of its own), narrows
to Main-Failure alarms via a case-insensitive substring match on
event_name, buckets by Hub/Diamond/Gold/Silver/Bronze from site_cache
(independent dimensions, so a site can count toward both), enriches
drilldown rows with the site's current Power-category Incident/INC-WO, and
excludes any alarm whose site_code has no matching site_cache record (that
cache already excludes off_air sites — see site_cache.sql).
"""
from app.services.alarm_main_failure.alarm_main_failure_service import AlarmMainFailureService


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


class FakeIncidentStatusRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


def _alarm_row(site_code, event_name="Main Failure Alarm", **overrides):
    row = {
        "occurred_at": "2026-01-01 00:00:00",
        "event_name": event_name,
        "additional_info": "",
        "nms": "ZTE",
        "technology": "Power",
        "site_code": site_code,
        "site_name": f"Site {site_code}",
        "occurrence_count": 1,
    }
    row.update(overrides)
    return row


def test_get_counts_matches_main_failure_in_event_name():
    alarm_rows = [_alarm_row("S1", event_name="Main Failure Alarm"), _alarm_row("S1", event_name="Door Alarm")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = AlarmMainFailureService(FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([]))

    counts = svc.get_counts()

    assert counts["Gold"] == 1


def test_get_counts_matches_messy_event_name_variant():
    alarm_rows = [
        _alarm_row("S1", event_name="BASE STATION EXTERNAL ALARM NOTIFICATION:::Main Failure"),
    ]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "silver"}]
    svc = AlarmMainFailureService(FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([]))

    counts = svc.get_counts()

    assert counts["Silver"] == 1


def test_get_counts_double_counts_hub_and_grade_for_the_same_alarm():
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "diamond"}]
    svc = AlarmMainFailureService(FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([]))

    counts = svc.get_counts()

    assert counts["Hub"] == 1
    assert counts["Diamond"] == 1


def test_get_counts_ignores_non_main_failure_events():
    alarm_rows = [_alarm_row("S1", event_name="DG on Alarm")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = AlarmMainFailureService(FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([]))

    counts = svc.get_counts()

    assert counts["Gold"] == 0


def test_get_details_enriches_rows_with_current_power_incident():
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    incident_rows = [{
        "site_code": "S1", "incident_id": "INC1", "wo_id": "WO1", "wo_status": "New", "category": "Power",
    }]
    svc = AlarmMainFailureService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["incident_id"] == "INC1"
    assert row["wo_id"] == "WO1"


def test_get_details_ignores_non_power_incidents():
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    incident_rows = [{"site_code": "S1", "incident_id": "INC1", "category": "BSS Hardware"}]
    svc = AlarmMainFailureService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["incident_id"] == ""


def test_get_details_translates_nms_code():
    alarm_rows = [_alarm_row("S1", nms="7")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = AlarmMainFailureService(FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([]))

    row = svc.get_details()[0]

    assert row["nms"] == "Nokia"


def test_get_details_filters_by_hub_badge():
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2")]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "bronze"},
    ]
    svc = AlarmMainFailureService(FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([]))

    rows = svc.get_details("Hub")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S1"


def test_get_details_filters_by_grade_badge():
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2")]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "bronze"},
    ]
    svc = AlarmMainFailureService(FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([]))

    rows = svc.get_details("Bronze")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S2"


def test_get_details_excludes_alarms_with_no_matching_site_cache_record():
    """A site missing from site_cache (off_air sites are excluded there —
    see site_cache.sql — or a site_code that never resolved to any real
    site) should not appear at all, rather than showing up with a blank
    Site Name/Hub/Grade/Province."""
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2"), _alarm_row("")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = AlarmMainFailureService(FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([]))

    rows = svc.get_details()

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S1"


def test_get_counts_excludes_alarms_with_no_matching_site_cache_record():
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = AlarmMainFailureService(FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([]))

    counts = svc.get_counts()

    assert counts["Gold"] == 1
