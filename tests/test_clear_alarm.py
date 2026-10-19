"""Tests for POST /alarms/clear (dashboard.clear_alarm) — the Clear Alarm
popup's submit target for EZE/TCT/ISP POP's three-dot Action menu.
Monkeypatches the module-level `alarm_service`/`alarm_sync_service`
singletons instead of hitting real MSSQL — this route's own job is just
validating the incoming form and forwarding it to AlarmService.clear_alarm()
(already covered on its own terms elsewhere), then removing that one row
from the local cache via AlarmSyncService.apply_clear() (replaced a full
sync_scope() table re-fetch — see the route's own docstring) so the
redirect the user lands on doesn't show stale data — that call must be
faked here too, or this test would try a real MSSQL round-trip.
Deliberately no test here ever calls the real AlarmRepository/MSSQL write
path — same as test_acknowledge_alarm.py, this stays at the fake-service
level only.
"""

from app.routes import dashboard


class FakeAlarmService:
    def __init__(self):
        self.calls = []

    def clear_alarm(self, row_id, username):
        self.calls.append((row_id, username))
        return True


class FakeAlarmSyncService:
    def __init__(self):
        self.apply_clear_calls = []

    def apply_clear(self, source, row_id):
        self.apply_clear_calls.append((source, row_id))


def test_clear_alarm_forwards_valid_form_to_service(client, monkeypatch):
    fake = FakeAlarmService()
    fake_sync = FakeAlarmSyncService()
    monkeypatch.setattr(dashboard, "alarm_service", fake)
    monkeypatch.setattr(dashboard, "alarm_sync_service", fake_sync)

    response = client.post(
        "/alarms/clear", data={"id": "row-1", "username": "slethean", "source": "tct"}
    )

    assert response.status_code == 302
    assert fake.calls == [("row-1", "slethean")]
    assert fake_sync.apply_clear_calls == [("tct", "row-1")]


def test_clear_alarm_skips_service_call_when_username_missing(client, monkeypatch):
    fake = FakeAlarmService()
    monkeypatch.setattr(dashboard, "alarm_service", fake)

    response = client.post("/alarms/clear", data={"id": "row-1", "username": ""})

    assert response.status_code == 302
    assert fake.calls == []


def test_clear_alarm_skips_service_call_when_id_missing(client, monkeypatch):
    fake = FakeAlarmService()
    monkeypatch.setattr(dashboard, "alarm_service", fake)

    response = client.post("/alarms/clear", data={"id": "", "username": "slethean"})

    assert response.status_code == 302
    assert fake.calls == []
