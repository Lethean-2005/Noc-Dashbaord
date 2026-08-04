"""Tests for AlarmService's ISP POP/EZE/TCT badge counts.

ISP POP counts distinct (POP Name, POP Code) sites with an active alarm of
a given type, not the raw number of alarm rows — POP Name alone isn't a
reliable site identity, so both fields together are the site key, scoped
only to get_isp_pop_counts(). EZE/TCT count distinct devices instead (via
the shared _typed_counts()), not the raw row count either.
"""
from app.services.alarm.alarm_service import AlarmService, EZE_TYPES


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


def test_get_eze_counts_counts_distinct_devices_not_alarm_rows():
    rows = [
        {"alarm": "PORT", "device_name": "SW-A"},
        {"alarm": "PORT", "device_name": "SW-A"},
        {"alarm": "PORT", "device_name": "SW-B"},
    ]
    svc = AlarmService(FakeCacheRepo(rows))

    counts = svc.get_eze_counts()

    assert counts["PORT"] == 2
    # Every other EZE type still comes back as 0, not missing.
    assert set(counts.keys()) == set(EZE_TYPES)
    assert counts["CPU"] == 0


def test_get_tct_counts_matches_case_insensitively_and_counts_distinct_devices():
    rows = [
        {"alarm": "bgp", "device_name": "RTR-A"},
        {"alarm": "BGP", "device_name": "RTR-A"},  # same device, different case - still 1
        {"alarm": "bgp", "device_name": "RTR-B"},
    ]
    svc = AlarmService(FakeCacheRepo(rows))

    counts = svc.get_tct_counts()

    assert counts["bgp"] == 2
