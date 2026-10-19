"""Tests for RanMainAcAlarmService — the RAN Status card's 'RAN Main AC
Alarm' column. Reads the already-synced ape_alarm cache (no Postgres call
of its own), narrows to Main Failure event types via a case-insensitive
substring match (real event_name text is messy, see the service's module
docstring), buckets by Hub-Site/Diamond/Gold/Silver/Bronze from site_cache (Hub-Site
takes priority: a hub site counts only there, never also under its grade),
and enriches
drilldown rows with the site's current **Power**-category Incident/INC-WO
from incident_by_status (not any open incident) plus a "Site down" Remark
flag when that same site also has an open **Site Down**-category incident.
"""

from app.services.ran.ran_main_ac_alarm_service import RanMainAcAlarmService


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


def test_get_counts_matches_messy_real_world_main_failure_variants():
    alarm_rows = [
        _alarm_row("S1", event_name="Main Failure Alarm"),
        _alarm_row("S1", event_name="BASE STATION EXTERNAL ALARM NOTIFICATION:::Main Failure"),
        _alarm_row("S1", event_name="Door Alarm"),  # not a main failure, excluded
    ]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([])
    )

    counts = svc.get_counts()

    assert counts["Gold"] == 2
    assert counts["Hub-Site"] == 0


def test_get_counts_hub_site_takes_priority_over_grade_for_the_same_alarm():
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "diamond"}]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([])
    )

    counts = svc.get_counts()

    assert counts["Hub-Site"] == 1
    assert counts["Diamond"] == 0


def test_get_counts_ignores_alarms_with_no_matching_site():
    alarm_rows = [_alarm_row("UNKNOWN")]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo([]), FakeIncidentStatusRepo([])
    )

    counts = svc.get_counts()

    assert all(n == 0 for n in counts.values())


def test_get_details_enriches_rows_with_site_and_computes_outage_min():
    alarm_rows = [_alarm_row("S1", occurred_at="2020-01-01 00:00:00")]
    site_rows = [
        {
            "standard_code": "S1",
            "hub_site": "Hub-Router",
            "site_grade": "silver",
            "province": "Phnom Penh",
        }
    ]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([])
    )

    rows = svc.get_details()

    assert rows[0]["hub_site"] == "Hub-Router"
    assert rows[0]["site_grade"] == "Silver"
    assert rows[0]["province"] == "Phnom Penh"
    assert rows[0]["outage_min"] > 0


def test_get_details_enriches_rows_with_current_power_incident_and_inc_wo():
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    incident_rows = [
        {
            "site_code": "S1",
            "incident_id": "INC1",
            "incident_numeric_id": 1,
            "wo_id": "WO1",
            "wo_numeric_id": 1,
            "wo_created_at": "2026-01-01 00:00:00",
            "wo_status": "New",
            "category": "Power",
        }
    ]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeIncidentStatusRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["incident_id"] == "INC1"
    assert row["wo_id"] == "WO1"
    assert row["wo_status"] == "New"


def test_get_details_ignores_non_power_incidents_for_incident_wo_enrichment():
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    incident_rows = [
        {
            "site_code": "S1",
            "incident_id": "INC1",
            "wo_id": "WO1",
            "category": "BSS Hardware",
        }
    ]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeIncidentStatusRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["incident_id"] == ""
    assert row["wo_id"] == ""


def test_get_details_remark_shows_site_down_category_for_a_site_down_incident():
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    incident_rows = [{"site_code": "S1", "category": "Site Down"}]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeIncidentStatusRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["remark"] == "Site Down"


def test_get_details_remark_shows_power_category_for_a_power_incident():
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    incident_rows = [{"site_code": "S1", "category": "Power"}]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeIncidentStatusRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["remark"] == "Power"


def test_get_details_falls_back_to_site_down_incident_when_no_power_incident():
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    incident_rows = [
        {
            "site_code": "S1",
            "incident_id": "INC1",
            "incident_numeric_id": 1,
            "wo_id": "WO1",
            "wo_numeric_id": 1,
            "wo_created_at": "2026-01-01 00:00:00",
            "wo_status": "New",
            "category": "Site Down",
        }
    ]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeIncidentStatusRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["incident_id"] == "INC1"
    assert row["wo_id"] == "WO1"
    assert row["remark"] == "Site Down"


def test_get_details_prefers_power_incident_over_site_down_when_both_exist():
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    incident_rows = [
        {"site_code": "S1", "incident_id": "INC-POWER", "wo_id": "WO-POWER", "category": "Power"},
        {"site_code": "S1", "incident_id": "INC-DOWN", "wo_id": "WO-DOWN", "category": "Site Down"},
    ]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeIncidentStatusRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["incident_id"] == "INC-POWER"
    assert row["wo_id"] == "WO-POWER"
    assert row["remark"] == "Power"


def test_get_details_defaults_incident_fields_to_empty_when_no_match():
    alarm_rows = [_alarm_row("S1")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([])
    )

    row = svc.get_details()[0]

    assert row["incident_id"] == ""
    assert row["wo_id"] == ""
    assert row["remark"] == ""


def test_get_details_strips_noisy_vendor_prefix_from_event_name():
    alarm_rows = [
        _alarm_row("S1", event_name="BASE STATION EXTERNAL ALARM NOTIFICATION:::Main Failure")
    ]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([])
    )

    row = svc.get_details()[0]

    assert row["event_name"] == "Main Failure"


def test_get_details_leaves_clean_event_names_unchanged():
    alarm_rows = [_alarm_row("S1", event_name="Main Failure Alarm")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([])
    )

    row = svc.get_details()[0]

    assert row["event_name"] == "Main Failure Alarm"


def test_get_details_excludes_rows_with_no_matching_site_cache_record():
    """A site missing from site_cache (off_air, or genuinely unmapped) is
    dropped instead of showing with blank Hub/Grade/Province — same
    exclusion as alarm_main_failure_service.py / alarm_site_down_service.py."""
    alarm_rows = [_alarm_row("OFF_AIR_SITE")]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo([]), FakeIncidentStatusRepo([])
    )

    assert svc.get_details() == []


def test_get_counts_excludes_sites_with_no_matching_site_cache_record():
    alarm_rows = [_alarm_row("OFF_AIR_SITE")]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo([]), FakeIncidentStatusRepo([])
    )

    counts = svc.get_counts()

    assert all(n == 0 for n in counts.values())


def test_get_details_translates_known_nms_code_to_vendor_name():
    alarm_rows = [_alarm_row("S1", nms="7")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([])
    )

    row = svc.get_details()[0]

    assert row["nms"] == "Nokia"


def test_get_details_leaves_unknown_nms_code_unchanged():
    alarm_rows = [_alarm_row("S1", nms="999")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([])
    )

    row = svc.get_details()[0]

    assert row["nms"] == "999"


def test_get_details_prefers_ape_alarms_own_nms_over_incidents_stale_code():
    # The alarm's own nms code comes straight from the live alarm feed
    # (object_138); the incident's nms is resolved from object_227's NE
    # inventory, which can be stale for a site whose equipment changed —
    # confirmed live (a site with an old NE keeping a superseded vendor
    # code while a newer NE has none recorded at all). So the alarm's own
    # translated code wins even when an incident's nms disagrees.
    alarm_rows = [_alarm_row("S1", nms="7")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    incident_rows = [{"site_code": "S1", "nms": "Huawei", "category": "Power"}]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeIncidentStatusRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["nms"] == "Nokia"


def test_get_details_falls_back_to_incidents_nms_when_alarm_has_none():
    alarm_rows = [_alarm_row("S1", nms="")]
    site_rows = [{"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"}]
    incident_rows = [{"site_code": "S1", "nms": "Huawei", "category": "Power"}]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows),
        FakeSiteRepo(site_rows),
        FakeIncidentStatusRepo(incident_rows),
    )

    row = svc.get_details()[0]

    assert row["nms"] == "Huawei"


def test_get_details_filters_by_badge_type():
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2")]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Not Hub", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "bronze"},
    ]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([])
    )

    rows = svc.get_details("Gold")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S1"


def test_get_details_filters_by_hub_site_badge():
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2")]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "bronze"},
    ]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([])
    )

    rows = svc.get_details("Hub-Site")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S1"


def test_get_details_excludes_hub_site_from_its_grade_badge():
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2")]
    site_rows = [
        {"standard_code": "S1", "hub_site": "Hub-MW", "site_grade": "gold"},
        {"standard_code": "S2", "hub_site": "Not Hub", "site_grade": "gold"},
    ]
    svc = RanMainAcAlarmService(
        FakeApeAlarmRepo(alarm_rows), FakeSiteRepo(site_rows), FakeIncidentStatusRepo([])
    )

    rows = svc.get_details("Gold")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S2"
