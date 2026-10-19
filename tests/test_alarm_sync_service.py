"""Tests for AlarmSyncService.sync_scope() — refreshes only the one
cache table (isp_pop/eze/tct/it_node) an Acknowledge/Clear action
actually touched, instead of sync_all()'s all 4. See
test_acknowledge_alarm.py/test_clear_alarm.py for the routes that call
this at the fake-service level; these tests cover the real
AlarmSyncService.sync_scope() dispatch itself.
"""

from app.services.alarm.alarm_sync_service import AlarmSyncService


class FakeAlarmRepo:
    def __init__(self):
        self.calls = []

    def _fetch(self, name, rows):
        self.calls.append(name)
        return rows

    def fetch_isp_pop_active(self):
        return self._fetch("isp_pop", [{"ID": 1, "AlarmName": "X"}])

    def fetch_eze_active(self):
        return self._fetch("eze", [{"ID": 2, "alarm_type": "port"}])

    def fetch_tct_active(self):
        return self._fetch("tct", [{"ID": 3, "alarm_type": "congestion"}])

    def fetch_it_node_active(self):
        return self._fetch("it_node", [{"ID": 4, "AlarmName": "Y"}])


class FakeCacheRepo:
    def __init__(self):
        self.written = {}

    def replace_all(self, table, rows):
        self.written[table] = rows


def test_sync_scope_isp_pop_only_touches_isp_pop_table():
    mssql = FakeAlarmRepo()
    cache = FakeCacheRepo()
    svc = AlarmSyncService(mssql, cache)

    count = svc.sync_scope("isp_pop")

    assert count == 1
    assert mssql.calls == ["isp_pop"]
    assert list(cache.written.keys()) == ["isp_pop_alarm_cache"]


def test_sync_scope_eze_only_touches_eze_table():
    mssql = FakeAlarmRepo()
    cache = FakeCacheRepo()
    svc = AlarmSyncService(mssql, cache)

    svc.sync_scope("eze")

    assert mssql.calls == ["eze"]
    assert list(cache.written.keys()) == ["eze_alarm_cache"]


def test_sync_scope_tct_only_touches_tct_table():
    mssql = FakeAlarmRepo()
    cache = FakeCacheRepo()
    svc = AlarmSyncService(mssql, cache)

    svc.sync_scope("tct")

    assert mssql.calls == ["tct"]
    assert list(cache.written.keys()) == ["tct_alarm_cache"]


def test_sync_scope_it_node_only_touches_it_node_table():
    mssql = FakeAlarmRepo()
    cache = FakeCacheRepo()
    svc = AlarmSyncService(mssql, cache)

    svc.sync_scope("it_node")

    assert mssql.calls == ["it_node"]
    assert list(cache.written.keys()) == ["it_node_alarm_cache"]


def test_sync_scope_unknown_source_is_a_noop():
    mssql = FakeAlarmRepo()
    cache = FakeCacheRepo()
    svc = AlarmSyncService(mssql, cache)

    result = svc.sync_scope("bogus")

    assert result is None
    assert mssql.calls == []
    assert cache.written == {}


def test_sync_scope_blank_source_is_a_noop():
    mssql = FakeAlarmRepo()
    cache = FakeCacheRepo()
    svc = AlarmSyncService(mssql, cache)

    result = svc.sync_scope("")

    assert result is None
    assert mssql.calls == []
