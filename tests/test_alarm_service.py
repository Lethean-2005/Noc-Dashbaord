"""Tests for AlarmService's ISP POP/EZE/TCT badge counts.

ISP POP counts distinct (POP Name, POP Code) sites with an active alarm of
a given type, not the raw number of alarm rows — POP Name alone isn't a
reliable site identity, so both fields together are the site key, scoped
only to get_isp_pop_counts(). EZE/TCT (via the shared _typed_counts()) use
a hybrid rule: a row with a real POP link (pop_name AND pop_code both
present) is deduped by that site, same as ISP POP; a row with no POP link
(e.g. a core device with nothing to map to a POP — confirmed live for
TCT's zero_traffic type) is counted as a plain record instead, one per
row, since there's no site to dedupe by.
"""

from app.services.alarm.alarm_service import AlarmService, CONGESTION_TCT_TYPES, EZE_TYPES, TCT_TYPES


class FakeCacheRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


def test_get_isp_pop_counts_counts_distinct_sites_not_alarm_rows():
    rows = [
        {"alarm": "POP/PON DOWN", "pop_name": "KOH_RONG1-MBT", "pop_code": "7210"},
        {"alarm": "POP/PON DOWN", "pop_name": "KOH_RONG1-MBT", "pop_code": "7210"},
        {"alarm": "POP/PON DOWN", "pop_name": "KOH_RONG1-MBT", "pop_code": "7210"},
        {"alarm": "POP/PON DOWN", "pop_name": "CHBAAMPOV-CFOCN-MCB", "pop_code": "7032"},
    ]
    svc = AlarmService(FakeCacheRepo(rows))

    counts = svc.get_isp_pop_counts()

    # 4 rows, but only 2 distinct sites (KOH_RONG1-MBT/7210 x3, CHBAAMPOV-CFOCN-MCB/7032 x1).
    assert counts["POP/PON DOWN"] == 2


def test_get_isp_pop_counts_treats_same_name_different_code_as_different_sites():
    rows = [
        {"alarm": "POP/PON DOWN", "pop_name": "SITE-A", "pop_code": "1001"},
        {"alarm": "POP/PON DOWN", "pop_name": "SITE-A", "pop_code": "1002"},
    ]
    svc = AlarmService(FakeCacheRepo(rows))

    counts = svc.get_isp_pop_counts()

    assert counts["POP/PON DOWN"] == 2


def test_get_isp_pop_counts_ignores_rows_with_no_pop_name():
    rows = [{"alarm": "POP/PON DOWN", "pop_name": "", "pop_code": "1001"}]
    svc = AlarmService(FakeCacheRepo(rows))

    counts = svc.get_isp_pop_counts()

    assert counts["POP/PON DOWN"] == 0


def test_get_isp_pop_counts_returns_zero_for_type_with_no_rows():
    svc = AlarmService(FakeCacheRepo([]))

    counts = svc.get_isp_pop_counts()

    assert counts == {"POP/PON DOWN": 0, "POP/PON POWER": 0}


def test_get_eze_counts_dedupes_by_pop_site_when_pop_linked():
    rows = [
        {"alarm": "PORT", "device_name": "SW-A", "pop_name": "SITE-A", "pop_code": "1001"},
        {"alarm": "PORT", "device_name": "SW-A2", "pop_name": "SITE-A", "pop_code": "1001"},
        {"alarm": "PORT", "device_name": "SW-B", "pop_name": "SITE-B", "pop_code": "1002"},
    ]
    svc = AlarmService(FakeCacheRepo(rows))

    counts = svc.get_eze_counts()

    # 2 devices at SITE-A collapse to 1 site + SITE-B = 2, not 3 raw rows.
    assert counts["PORT"] == 2
    # Every other EZE type still comes back as 0, not missing.
    assert set(counts.keys()) == set(EZE_TYPES)
    assert counts["CPU"] == 0


def test_get_eze_counts_counts_raw_records_when_no_pop_link():
    # Same device, 4 separate rows, no pop_name/pop_code at all — e.g. a
    # core device with nothing to map to a POP (confirmed live for TCT's
    # zero_traffic: 4 rows, same device_name, empty pop_name/pop_code).
    # There's no site to dedupe by, so every row counts on its own.
    rows = [{"alarm": "PORT", "device_name": "CORE-1"} for _ in range(4)]
    svc = AlarmService(FakeCacheRepo(rows))

    counts = svc.get_eze_counts()

    assert counts["PORT"] == 4


def test_get_tct_counts_matches_case_insensitively_and_dedupes_by_pop_site():
    rows = [
        {"alarm": "bgp", "device_name": "RTR-A", "pop_name": "SITE-A", "pop_code": "1001"},
        {"alarm": "BGP", "device_name": "RTR-A2", "pop_name": "SITE-A", "pop_code": "1001"},
        {"alarm": "bgp", "device_name": "RTR-B", "pop_name": "SITE-B", "pop_code": "1002"},
    ]
    svc = AlarmService(FakeCacheRepo(rows))

    counts = svc.get_tct_counts()

    assert counts["bgp"] == 2


def test_get_tct_counts_zero_traffic_no_pop_link_counts_raw_records():
    # Real case reported live: 4 zero_traffic rows, all the same device,
    # pop_name/pop_code both empty — badge should show 4, not 1.
    rows = [
        {"alarm": "zero_traffic", "device_name": "MSC5-M6K8S-BGP01", "pop_name": "", "pop_code": ""}
        for _ in range(4)
    ]
    svc = AlarmService(FakeCacheRepo(rows))

    counts = svc.get_tct_counts()

    assert counts["zero_traffic"] == 4


def test_get_tct_counts_merges_bandwidth_into_congestion():
    # 'bandwidth' and 'congestion' are two distinct raw alarm names MSSQL
    # sends for the same underlying condition — the card shows one
    # Congestion badge, so its count must be the sum of both, and
    # 'bandwidth' must not appear as its own key any more.
    rows = [
        {"alarm": "bandwidth", "device_name": "RTR-A", "pop_name": "", "pop_code": ""},
        {"alarm": "bandwidth", "device_name": "RTR-B", "pop_name": "", "pop_code": ""},
        {"alarm": "congestion", "device_name": "RTR-C", "pop_name": "", "pop_code": ""},
    ]
    svc = AlarmService(FakeCacheRepo(rows))

    counts = svc.get_tct_counts()

    assert counts["congestion"] == 3
    assert "bandwidth" not in counts


def test_congestion_tct_types_is_subset_of_tct_types():
    # CONGESTION_TCT_TYPES is also hardcoded as literal SQL text in
    # alarms.sql's congestion_history query (that file can't import this
    # Python tuple) — this guards that it stays {'bandwidth', 'congestion'}
    # and a valid subset of TCT_TYPES, so an edit to either constant that
    # breaks the relationship fails loudly here instead of silently
    # undercounting Congestion History on the live dashboard.
    assert set(CONGESTION_TCT_TYPES) == {"bandwidth", "congestion"}
    assert set(CONGESTION_TCT_TYPES) <= set(TCT_TYPES)
