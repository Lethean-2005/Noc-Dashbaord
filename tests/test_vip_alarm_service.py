"""Tests for VipAlarmService.get_details()'s event_name display cleanup —
vip_alarm is derived from ape_alarm (see vip_alarm_sync_service.py), so it
carries the same noisy vendor prefix on some rows
("BASE STATION EXTERNAL ALARM NOTIFICATION:::Main Failure"). Categorization
(_categorize(), badge_type) must keep matching the full raw text — only the
displayed event_name should be cleaned, and only after categorization runs.
"""

from app.services.vip.vip_alarm_service import VipAlarmService


class FakeCacheRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeIncidentStatusRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeSiteRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


def _vip_alarm_row(**overrides):
    row = {
        "occurred_at": "2026-01-01 00:00:00",
        "event_name": "BASE STATION EXTERNAL ALARM NOTIFICATION:::Main Failure",
        "additional_info": "",
        "nms": "7",
        "technology": "Power",
        "site_code": "S1",
        "site_name": "Site S1",
        "site_strategic_type": "VIP",
        "occurrence_count": 1,
    }
    row.update(overrides)
    return row


def _site_row(code):
    return {"standard_code": code, "hub_site": "Not Hub", "site_grade": "gold"}


def test_get_details_strips_noisy_prefix_from_displayed_event_name():
    svc = VipAlarmService(
        FakeCacheRepo([_vip_alarm_row()]),
        FakeIncidentStatusRepo([]),
        FakeSiteRepo([_site_row("S1")]),
    )

    row = svc.get_details()[0]

    assert row["event_name"] == "Main Failure"


def test_get_details_categorizes_using_the_full_raw_event_name():
    svc = VipAlarmService(
        FakeCacheRepo([_vip_alarm_row()]),
        FakeIncidentStatusRepo([]),
        FakeSiteRepo([_site_row("S1")]),
    )

    row = svc.get_details()[0]

    # "main failure" substring still matches inside the un-cleaned raw text,
    # so badge_type categorization is unaffected by the prefix.
    assert row["badge_type"] == "Main AC Failure"


def test_get_details_leaves_clean_event_names_unchanged():
    svc = VipAlarmService(
        FakeCacheRepo([_vip_alarm_row(event_name="Door Alarm")]),
        FakeIncidentStatusRepo([]),
        FakeSiteRepo([_site_row("S1")]),
    )

    row = svc.get_details()[0]

    assert row["event_name"] == "Door Alarm"
    assert row["badge_type"] == "Door Alarm"


def test_get_details_prefers_vip_alarms_own_nms_over_incidents_stale_code():
    # vip_alarm.nms (code "7" here) comes straight from the live alarm
    # feed (object_138); the incident's nms is resolved from object_227's
    # NE inventory, which can be stale for a site whose equipment changed
    # (confirmed live: an old NE kept a superseded vendor code while a
    # newer NE had none recorded at all, even though the live alarm feed
    # already had the correct vendor).
    svc = VipAlarmService(
        FakeCacheRepo([_vip_alarm_row(nms="7")]),
        FakeIncidentStatusRepo([{"site_code": "S1", "nms": "Huawei"}]),
        FakeSiteRepo([_site_row("S1")]),
    )

    row = svc.get_details()[0]

    assert row["nms"] == "Nokia"


def test_get_details_falls_back_to_incidents_nms_when_alarm_has_none():
    svc = VipAlarmService(
        FakeCacheRepo([_vip_alarm_row(nms="")]),
        FakeIncidentStatusRepo([{"site_code": "S1", "nms": "Huawei"}]),
        FakeSiteRepo([_site_row("S1")]),
    )

    row = svc.get_details()[0]

    assert row["nms"] == "Huawei"


def test_get_counts_counts_distinct_sites_not_alarm_rows():
    rows = [
        _vip_alarm_row(site_code="S1", event_name="Main Failure Alarm"),
        _vip_alarm_row(site_code="S1", event_name="Main Failure Alarm again"),
        _vip_alarm_row(site_code="S2", event_name="Main Failure Alarm"),
    ]
    svc = VipAlarmService(
        FakeCacheRepo(rows),
        FakeIncidentStatusRepo([]),
        FakeSiteRepo([_site_row("S1"), _site_row("S2")]),
    )

    counts = svc.get_counts()

    # S1 has 2 Main Failure alarm rows but counts once; S2 adds a second site.
    assert counts["Main AC Failure"] == 2


def test_get_counts_ignores_rows_with_no_site_code():
    rows = [_vip_alarm_row(site_code="", event_name="Main Failure Alarm")]
    svc = VipAlarmService(
        FakeCacheRepo(rows), FakeIncidentStatusRepo([]), FakeSiteRepo([_site_row("S1")])
    )

    counts = svc.get_counts()

    assert counts["Main AC Failure"] == 0


def test_get_details_excludes_rows_with_no_matching_site_cache_record():
    """Same "off_air isn't legitimately down" exclusion as the other alarm
    cards — a site missing from site_cache (off_air, or unmapped) is
    dropped instead of showing with blank Hub/Grade/Province."""
    svc = VipAlarmService(
        FakeCacheRepo([_vip_alarm_row()]), FakeIncidentStatusRepo([]), FakeSiteRepo([])
    )

    assert svc.get_details() == []


def test_get_counts_excludes_sites_with_no_matching_site_cache_record():
    rows = [_vip_alarm_row(site_code="S1", event_name="Main Failure Alarm")]
    svc = VipAlarmService(FakeCacheRepo(rows), FakeIncidentStatusRepo([]), FakeSiteRepo([]))

    counts = svc.get_counts()

    assert counts["Main AC Failure"] == 0
