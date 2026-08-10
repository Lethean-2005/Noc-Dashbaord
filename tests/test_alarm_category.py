"""Tests for app/utils/alarm_category.py's site_down_technology() — the
shared SITE_DOWN_EVENTS -> generation mapping used by both
AlarmSiteDownService and AlarmCompletelySiteDownService, given directly by
the user rather than inferred from event_name substrings — and
classify_site_technology_coverage(), the shared completely-down/
partially-down split used by AlarmCompletelySiteDownService,
RanSiteDownService, and RanTechDownService.
"""

from app.utils.alarm_category import classify_site_technology_coverage, site_down_technology


def test_gnodeb_events_map_to_5g():
    assert site_down_technology("gNodeB Out of Service") == "5G"
    assert site_down_technology("gNodeb DU out-of-service") == "5G"


def test_enodeb_events_map_to_4g():
    assert site_down_technology("eNodeB Out of Service") == "4G"
    assert site_down_technology("eNodeB is out of service") == "4G"


def test_nodeb_and_wcdma_events_map_to_3g():
    assert site_down_technology("NodeB Out of Service") == "3G"
    assert site_down_technology("NodeB is out of service") == "3G"
    assert site_down_technology("WCDMA BASE STATION OUT OF USE") == "3G"


def test_csl_bts_abis_events_map_to_2g():
    assert site_down_technology("CSL Fault") == "2G"
    assert site_down_technology("BTS O&M LINK FAILURE") == "2G"
    assert site_down_technology("Site Abis control link broken") == "2G"


def test_sran_events_map_to_sran():
    assert site_down_technology("NE Is Disconnected") == "SRAN"
    assert site_down_technology("NE3SWS AGENT NOT RESPONDING TO REQUESTS") == "SRAN"
    assert site_down_technology("The link between the server and the ME is broken") == "SRAN"


def test_non_site_down_event_maps_to_empty_string():
    assert site_down_technology("Main Failure Alarm") == ""
    assert site_down_technology("") == ""
    assert site_down_technology(None) == ""


def test_matching_is_case_insensitive():
    assert site_down_technology("gnodeb out of service") == "5G"
    assert site_down_technology("CSL FAULT") == "2G"


def _alarm(site_code, event_name):
    return {"site_code": site_code, "event_name": event_name}


def test_sran_alarm_alone_is_completely_down():
    completely, partial = classify_site_technology_coverage(
        [_alarm("S1", "NE Is Disconnected")],
        {"S1": {"2g", "4g"}},
    )
    assert completely == {"S1"}
    assert partial == set()


def test_single_generation_alarm_on_multi_tech_site_is_partial():
    completely, partial = classify_site_technology_coverage(
        [_alarm("S1", "eNodeB is out of service")],
        {"S1": {"2g", "4g"}},
    )
    assert completely == set()
    assert partial == {"S1"}


def test_covering_every_generation_is_completely_down():
    completely, partial = classify_site_technology_coverage(
        [_alarm("S1", "eNodeB is out of service"), _alarm("S1", "NodeB is out of service")],
        {"S1": {"3g", "4g"}},
    )
    assert completely == {"S1"}
    assert partial == set()


def test_single_generation_alarm_on_single_tech_site_is_completely_down():
    completely, partial = classify_site_technology_coverage(
        [_alarm("S1", "BTS O&M LINK FAILURE")],
        {"S1": {"2g"}},
    )
    assert completely == {"S1"}
    assert partial == set()


def test_site_with_no_known_inventory_lands_in_neither_set():
    completely, partial = classify_site_technology_coverage(
        [_alarm("S1", "NE Is Disconnected")],
        {},
    )
    assert completely == set()
    assert partial == set()
