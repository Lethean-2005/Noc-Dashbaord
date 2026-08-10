"""Tests for app/utils/event_name.py's clean_event_name() — the shared
display-only cleanup used by both app/services/ran/ran_main_ac_alarm_service.py
and app/services/vip/vip_alarm_service.py. Strips any leading vendor
boilerplate prefix generically (shape: "CATEGORY NAME:::real name"),
covering all 16 distinct prefixes found in real production data plus any
new ones that show up later.
"""

from app.utils.event_name import clean_event_name


def test_strips_the_originally_reported_prefix():
    assert (
        clean_event_name("BASE STATION EXTERNAL ALARM NOTIFICATION:::Main Failure")
        == "Main Failure"
    )


def test_strips_other_real_world_prefix_variants_generically():
    assert (
        clean_event_name("BASE STATION CONNECTIVITY PROBLEM:::GTP-U Path Failure")
        == "GTP-U Path Failure"
    )
    assert clean_event_name("CELL FAULTY:::Cell Down") == "Cell Down"
    assert clean_event_name("FILE SYSTEM USAGE OVER LIMIT:::Disk Full") == "Disk Full"
    assert clean_event_name("BASE STATION/UNIT AUTONOMOUS RESET NOTIFICATION:::Reset") == "Reset"


def test_leaves_clean_event_names_unchanged():
    assert clean_event_name("Main Failure Alarm") == "Main Failure Alarm"
    assert clean_event_name("Door Alarm") == "Door Alarm"


def test_handles_none():
    assert clean_event_name(None) == ""


def test_handles_empty_string():
    assert clean_event_name("") == ""


def test_does_not_strip_when_there_is_no_triple_colon_separator():
    assert clean_event_name("MAIN FAILURE ALARM") == "MAIN FAILURE ALARM"
