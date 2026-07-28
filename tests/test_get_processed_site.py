"""Tests for app/utils/get_processed_site.py — the Python port of PostgreSQL's
get_processed_site() PL/pgSQL function (see that function's SQL comments
for the original 5-step priority chain this must match exactly).
"""
from app.utils.get_processed_site import get_processed_site, index_site_lookup


def _lookup(sran_id=None, nodeb_id=None, bts_id=None):
    by_sran_id = {sran_id[0]: sran_id[1]} if sran_id else {}
    by_nodeb_id = {nodeb_id[0]: nodeb_id[1]} if nodeb_id else {}
    by_bts_id = {bts_id[0]: bts_id[1]} if bts_id else {}
    return by_sran_id, by_nodeb_id, by_bts_id


def test_step1_sran_id_lookup_wins_when_site_name_found():
    by_sran_id, by_nodeb_id, by_bts_id = _lookup(sran_id=(1234, "XX5678"))
    code = get_processed_site("PLMN-PLMN/MRBTS-1234-X", "", by_sran_id, by_nodeb_id, by_bts_id)
    assert code == "5678"


def test_step1_falls_through_to_step2_when_lookup_misses():
    by_sran_id, by_nodeb_id, by_bts_id = _lookup()
    code = get_processed_site("PLMN-PLMN/MRBTS-1234-suffix", "", by_sran_id, by_nodeb_id, by_bts_id)
    assert code == "1234"


def test_step1_falls_through_when_looked_up_name_too_short():
    by_sran_id, by_nodeb_id, by_bts_id = _lookup(sran_id=(1234, "X"))
    code = get_processed_site("PLMN-PLMN/MRBTS-1234-9999", "", by_sran_id, by_nodeb_id, by_bts_id)
    # site_name "X" has len < 2, so step 1 falls through to step 2's raw digits
    assert code == "1234"


def test_step2_extracts_first_four_digit_run_not_followed_by_a_digit():
    by_sran_id, by_nodeb_id, by_bts_id = _lookup()
    code = get_processed_site("SITEAB1234XY", "", by_sran_id, by_nodeb_id, by_bts_id)
    assert code == "1234"


def test_step2_takes_priority_over_additional_info_lookups():
    by_sran_id, by_nodeb_id, by_bts_id = _lookup(nodeb_id=(5555, "YY7777"))
    code = get_processed_site("SITEAB1234XY", "UIubLink=5555;", by_sran_id, by_nodeb_id, by_bts_id)
    assert code == "1234"


def test_step4_nodeb_id_lookup_when_site_has_no_digits():
    by_sran_id, by_nodeb_id, by_bts_id = _lookup(nodeb_id=(5555, "YY7777"))
    code = get_processed_site("NoDigitsHere", "prefix;UIubLink=5555;suffix", by_sran_id, by_nodeb_id, by_bts_id)
    assert code == "7777"


def test_step5_bts_id_lookup_when_no_site_digits_or_nodeb_match():
    by_sran_id, by_nodeb_id, by_bts_id = _lookup(bts_id=(6666, "ZZ8888"))
    code = get_processed_site("NoDigitsHere", "prefix;GBtsEquipment=6666;suffix", by_sran_id, by_nodeb_id, by_bts_id)
    assert code == "8888"


def test_step6_fallback_pattern_in_additional_info():
    by_sran_id, by_nodeb_id, by_bts_id = _lookup()
    code = get_processed_site("NoDigitsHere", "ABCDEF1234GHI", by_sran_id, by_nodeb_id, by_bts_id)
    assert code == "1234"


def test_returns_empty_string_when_nothing_matches():
    by_sran_id, by_nodeb_id, by_bts_id = _lookup()
    code = get_processed_site("NoDigitsHere", "no patterns here either", by_sran_id, by_nodeb_id, by_bts_id)
    assert code == ""


def test_handles_none_site_and_additional_info():
    by_sran_id, by_nodeb_id, by_bts_id = _lookup()
    assert get_processed_site(None, None, by_sran_id, by_nodeb_id, by_bts_id) == ""


def test_index_site_lookup_builds_all_three_dicts_from_one_row():
    rows = [{"sran_id": 1, "nodeb_id": 2, "bts_id": 3, "site_name": "AB1111"}]
    by_sran_id, by_nodeb_id, by_bts_id = index_site_lookup(rows)
    assert by_sran_id == {1: "AB1111"}
    assert by_nodeb_id == {2: "AB1111"}
    assert by_bts_id == {3: "AB1111"}


def test_index_site_lookup_skips_missing_ids():
    rows = [{"sran_id": None, "nodeb_id": 2, "bts_id": None, "site_name": "AB1111"}]
    by_sran_id, by_nodeb_id, by_bts_id = index_site_lookup(rows)
    assert by_sran_id == {}
    assert by_nodeb_id == {2: "AB1111"}
    assert by_bts_id == {}
