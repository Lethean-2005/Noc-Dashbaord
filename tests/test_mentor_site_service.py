"""Tests for MentorSiteService — the Mentor Site page lets the user
configure a specific list of sites (typed in or CSV-uploaded), then checks
each against the already-synced ape_alarm/incident_by_status/site_cache
local caches, same flow as vip_alarm_service.py but for a user-picked site
list. mentor_sites itself is NOT a Postgres sync cache — see
mentor_site_repository.py.
"""

import io

from app.services.mentor.mentor_site_service import MentorSiteService


class FakeMentorSiteRepo:
    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.removed = []
        self.cleared = False

    def add(self, site_code, source):
        if not any(r["site_code"] == site_code for r in self._rows):
            self._rows.append(
                {"site_code": site_code, "added_at": "2026-01-01T00:00:00", "source": source}
            )

    def fetch_all(self):
        return list(self._rows)

    def remove(self, site_code):
        self.removed.append(site_code)
        self._rows = [r for r in self._rows if r["site_code"] != site_code]

    def clear_all(self):
        self.cleared = True
        self._rows = []


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


def _alarm_row(site_code, event_name="Door Alarm", additional_info="", **overrides):
    row = {
        "occurred_at": "2026-01-01 00:00:00",
        "event_name": event_name,
        "additional_info": additional_info,
        "nms": "ZTE",
        "technology": "Power",
        "site_code": site_code,
        "site_name": f"Site {site_code}",
        "occurrence_count": 1,
    }
    row.update(overrides)
    return row


def _svc(mentor_rows=None, alarm_rows=None, site_rows=None, incident_rows=None):
    return MentorSiteService(
        FakeMentorSiteRepo(mentor_rows),
        FakeApeAlarmRepo(alarm_rows or []),
        FakeSiteRepo(site_rows or []),
        FakeIncidentStatusRepo(incident_rows or []),
    )


_KNOWN_SITES = [
    {"standard_code": "S1"},
    {"standard_code": "S2"},
    {"standard_code": "S3"},
    {"standard_code": "S4"},
]


def test_add_site_codes_splits_on_commas_spaces_and_newlines():
    svc = _svc(site_rows=_KNOWN_SITES)
    added, duplicate, invalid = svc.add_site_codes("s1, s2\ns3 s4")
    assert set(added) == {"S1", "S2", "S3", "S4"}
    assert duplicate == []
    assert invalid == []
    assert {r["site_code"] for r in svc.mentor_site_repository.fetch_all()} == {
        "S1",
        "S2",
        "S3",
        "S4",
    }


def test_add_site_codes_dedupes_and_uppercases():
    svc = _svc(site_rows=_KNOWN_SITES)
    svc.add_site_codes("s1")
    svc.add_site_codes("S1, s2")
    assert {r["site_code"] for r in svc.mentor_site_repository.fetch_all()} == {"S1", "S2"}


def test_add_site_codes_returns_empty_for_blank_input():
    svc = _svc(site_rows=_KNOWN_SITES)
    added, duplicate, invalid = svc.add_site_codes("   ")
    assert added == []
    assert duplicate == []
    assert invalid == []


def test_add_site_codes_rejects_codes_that_are_not_real_sites():
    svc = _svc(site_rows=_KNOWN_SITES)
    added, duplicate, invalid = svc.add_site_codes("s1, bogus123")
    assert added == ["S1"]
    assert invalid == ["BOGUS123"]
    assert {r["site_code"] for r in svc.mentor_site_repository.fetch_all()} == {"S1"}


def test_add_site_codes_flags_already_configured_sites_as_duplicate():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    svc = _svc(mentor_rows=mentor_rows, site_rows=_KNOWN_SITES)

    added, duplicate, invalid = svc.add_site_codes("s1, s2")

    assert added == ["S2"]
    assert duplicate == ["S1"]
    assert invalid == []


def test_add_from_csv_parses_site_code_column():
    csv_text = "site_code,note\nS1,first\nS2,second\n"
    svc = _svc(site_rows=_KNOWN_SITES)
    added, duplicate, invalid, error = svc.add_from_csv(io.BytesIO(csv_text.encode("utf-8")))
    assert error is None
    assert set(added) == {"S1", "S2"}
    assert duplicate == []
    assert invalid == []
    assert {r["site_code"] for r in svc.mentor_site_repository.fetch_all()} == {"S1", "S2"}


def test_add_from_csv_matches_column_case_insensitively():
    csv_text = "Site_Code\nS1\n"
    svc = _svc(site_rows=_KNOWN_SITES)
    added, duplicate, invalid, error = svc.add_from_csv(io.BytesIO(csv_text.encode("utf-8")))
    assert error is None
    assert added == ["S1"]


def test_add_from_csv_rejects_codes_that_are_not_real_sites():
    csv_text = "site_code\nS1\nbogus123\n"
    svc = _svc(site_rows=_KNOWN_SITES)
    added, duplicate, invalid, error = svc.add_from_csv(io.BytesIO(csv_text.encode("utf-8")))
    assert error is None
    assert added == ["S1"]
    assert invalid == ["BOGUS123"]


def test_add_from_csv_flags_already_configured_sites_as_duplicate():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    csv_text = "site_code\nS1\nS2\n"
    svc = _svc(mentor_rows=mentor_rows, site_rows=_KNOWN_SITES)

    added, duplicate, invalid, error = svc.add_from_csv(io.BytesIO(csv_text.encode("utf-8")))

    assert added == ["S2"]
    assert duplicate == ["S1"]
    assert invalid == []


def test_add_from_csv_errors_when_no_site_code_column():
    csv_text = "name,value\nfoo,bar\n"
    svc = _svc(site_rows=_KNOWN_SITES)
    added, duplicate, invalid, error = svc.add_from_csv(io.BytesIO(csv_text.encode("utf-8")))
    assert added == []
    assert error == "No 'site_code' column found in the file."


def test_add_from_csv_errors_on_empty_file():
    svc = _svc(site_rows=_KNOWN_SITES)
    added, duplicate, invalid, error = svc.add_from_csv(io.BytesIO(b""))
    assert added == []
    assert error == "The file is empty."


def test_remove_site_delegates_to_repository():
    svc = _svc(mentor_rows=[{"site_code": "S1", "added_at": "", "source": "Manual"}])
    svc.remove_site("S1")
    assert svc.mentor_site_repository.removed == ["S1"]


def test_clear_all_sites_delegates_to_repository():
    svc = _svc(mentor_rows=[{"site_code": "S1", "added_at": "", "source": "Manual"}])
    svc.clear_all_sites()
    assert svc.mentor_site_repository.cleared is True
    assert svc.get_configured_sites() == []


def test_has_configured_sites_false_when_none_configured():
    svc = _svc()
    assert svc.has_configured_sites() is False


def test_has_configured_sites_true_once_a_site_is_added():
    svc = _svc(mentor_rows=[{"site_code": "S1", "added_at": "", "source": "Manual"}])
    assert svc.has_configured_sites() is True


def test_get_configured_sites_resolves_name_and_province():
    mentor_rows = [{"site_code": "S1", "added_at": "2026-01-01T00:00:00", "source": "Manual"}]
    site_rows = [
        {"standard_code": "S1", "physical_location_name": "Rose Condo", "province": "Phnom Penh"}
    ]
    svc = _svc(mentor_rows=mentor_rows, site_rows=site_rows)

    rows = svc.get_configured_sites()

    assert rows[0]["site_name"] == "Rose Condo"
    assert rows[0]["province"] == "Phnom Penh"
    assert rows[0]["status"] == "OK"


def test_get_configured_sites_status_other_when_alarm_matches_no_named_category():
    """An alarm that doesn't fall into any of the named categories must
    still surface as "Other" — showing "OK" here would read as "nothing
    wrong" for a site that genuinely has an active, uncategorized alarm."""
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [_alarm_row("S1", event_name="Some Other Alarm")]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    rows = svc.get_configured_sites()

    assert rows[0]["status"] == "Other"


def test_get_configured_sites_status_main_ac_failure():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [_alarm_row("S1", event_name="Main Failure Alarm")]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    rows = svc.get_configured_sites()

    assert rows[0]["status"] == "Main AC Failure"


def test_get_configured_sites_status_low_dc_voltage():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [_alarm_row("S1", event_name="Low DC Voltage Alarm")]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    rows = svc.get_configured_sites()

    assert rows[0]["status"] == "Low DC Voltage"


def test_get_configured_sites_status_high_dc_voltage():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [_alarm_row("S1", event_name="High DC Voltage Alarm")]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    rows = svc.get_configured_sites()

    assert rows[0]["status"] == "High DC Voltage"


def test_get_configured_sites_status_rect_failure():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [_alarm_row("S1", event_name="Rectifier Failure Alarm")]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    rows = svc.get_configured_sites()

    assert rows[0]["status"] == "RECT Failure"


def test_get_configured_sites_status_door_alarm():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [_alarm_row("S1", event_name="Door Alarm")]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    rows = svc.get_configured_sites()

    assert rows[0]["status"] == "Door Alarm"


def test_get_configured_sites_status_dg_on_matches_additional_info_too():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [_alarm_row("S1", event_name="Generator Event", additional_info="Status=DG On;")]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    rows = svc.get_configured_sites()

    assert rows[0]["status"] == "DG-On"


def test_get_configured_sites_status_site_down_takes_priority():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [
        _alarm_row("S1", event_name="Main Failure Alarm"),
        _alarm_row("S1", event_name="eNodeB is out of service"),
    ]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    rows = svc.get_configured_sites()

    assert rows[0]["status"] == "Site Down"


def test_get_configured_sites_returns_empty_list_when_nothing_configured():
    svc = _svc()
    assert svc.get_configured_sites() == []


def test_get_configured_sites_status_site_down_from_incident_with_no_matching_alarm():
    # Real-world case (site 6202): zero ape_alarm rows right now, but an
    # open Site Down Incident (a formal ticket) still exists — Status must
    # reflect that instead of falling back to "OK" just because no alarm
    # happens to be currently firing.
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    incident_rows = [{"site_code": "S1", "category": "Site Down"}]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=[], incident_rows=incident_rows)

    rows = svc.get_configured_sites()

    assert rows[0]["status"] == "Site Down"


def test_get_configured_sites_status_ok_when_incident_is_a_different_category():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    incident_rows = [{"site_code": "S1", "category": "Power"}]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=[], incident_rows=incident_rows)

    rows = svc.get_configured_sites()

    assert rows[0]["status"] == "OK"


def test_get_alarm_details_only_includes_configured_sites():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2")]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    rows = svc.get_alarm_details()

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S1"


def test_get_alarm_details_filters_by_site_code():
    """The Configured Mentor Sites table's per-row "View" action passes
    site_code so it opens only that site's alarms, not every configured
    site's. Real bug caught here: the per-row loop used a local variable
    also named `site_code` (for its own per-row incident/site lookups),
    which shadowed this method's own site_code parameter — by the end of
    the loop the filter compared against whichever site the LAST alarm row
    happened to belong to, not what the caller actually asked for. Filtering
    for S1 (the non-last site) is what exposes that — filtering for S2 (the
    last one) would pass even with the bug present."""
    mentor_rows = [
        {"site_code": "S1", "added_at": "", "source": "Manual"},
        {"site_code": "S2", "added_at": "", "source": "Manual"},
    ]
    alarm_rows = [_alarm_row("S1"), _alarm_row("S2")]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    rows = svc.get_alarm_details(site_code="S1")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S1"

    rows = svc.get_alarm_details(site_code="S2")

    assert len(rows) == 1
    assert rows[0]["site_code"] == "S2"


def test_get_alarm_details_returns_empty_when_nothing_configured():
    svc = _svc(alarm_rows=[_alarm_row("S1")])
    assert svc.get_alarm_details() == []


def test_get_alarm_details_enriches_with_incident_and_computes_outage():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [_alarm_row("S1", occurred_at="2020-01-01 00:00:00")]
    site_rows = [
        {
            "standard_code": "S1",
            "hub_site": "Hub-MW",
            "site_grade": "gold",
            "province": "Phnom Penh",
        }
    ]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows, site_rows=site_rows)

    row = svc.get_alarm_details()[0]

    assert row["hub_site"] == "Hub-MW"
    assert row["site_grade"] == "Gold"
    assert row["province"] == "Phnom Penh"
    assert row["outage_min"] > 0


def test_get_alarm_details_returns_every_alarm_type_unfiltered():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [
        _alarm_row("S1", event_name="Main Failure Alarm"),
        _alarm_row("S1", event_name="Door Alarm"),
    ]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    rows = svc.get_alarm_details()

    assert {r["event_name"] for r in rows} == {"Main Failure Alarm", "Door Alarm"}


def test_get_counts_uses_the_full_8_category_breakdown():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [
        _alarm_row("S1", event_name="Main Failure Alarm"),
        _alarm_row("S1", event_name="High DC Voltage Alarm"),
        _alarm_row("S1", event_name="Rectifier Failure"),
        _alarm_row("S1", event_name="Door Alarm"),
        _alarm_row("S1", event_name="Something Else"),
    ]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    counts = svc.get_counts()

    assert counts["Main AC Failure"] == 1
    assert counts["High DC Voltage"] == 1
    assert counts["RECT Failure"] == 1
    assert counts["Door Alarm"] == 1
    assert counts["Other"] == 1
    assert counts["Site Down"] == 0


def test_get_counts_returns_all_zero_when_nothing_configured():
    svc = _svc()
    counts = svc.get_counts()
    assert all(n == 0 for n in counts.values())


def test_get_counts_counts_distinct_sites_not_alarm_rows():
    mentor_rows = [
        {"site_code": "S1", "added_at": "", "source": "Manual"},
        {"site_code": "S2", "added_at": "", "source": "Manual"},
    ]
    alarm_rows = [
        _alarm_row("S1", event_name="Main Failure Alarm"),
        _alarm_row("S1", event_name="Main Failure Alarm again"),
        _alarm_row("S2", event_name="Main Failure Alarm"),
    ]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    counts = svc.get_counts()

    # S1 has 2 Main Failure alarm rows but counts once; S2 adds a second site.
    assert counts["Main AC Failure"] == 2


def test_get_alarm_details_filters_by_full_badge_category():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [
        _alarm_row("S1", event_name="Main Failure Alarm"),
        _alarm_row("S1", event_name="Door Alarm"),
    ]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows)

    rows = svc.get_alarm_details("Main AC Failure")

    assert len(rows) == 1
    assert rows[0]["event_name"] == "Main Failure Alarm"


def test_get_alarm_details_includes_category_and_resolved_at_from_incident():
    mentor_rows = [{"site_code": "S1", "added_at": "", "source": "Manual"}]
    alarm_rows = [_alarm_row("S1")]
    incident_rows = [
        {
            "site_code": "S1",
            "category": "Power",
            "resolved_at": "2026-01-02 00:00:00",
        }
    ]
    svc = _svc(mentor_rows=mentor_rows, alarm_rows=alarm_rows, incident_rows=incident_rows)

    row = svc.get_alarm_details()[0]

    assert row["category"] == "Power"
    assert row["resolved_at"] == "2026-01-02 00:00:00"
