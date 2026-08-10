"""Tests for POST /alarms/clear (dashboard.clear_alarm) — the Clear Alarm
popup's submit target for EZE/TCT/ISP POP's three-dot Action menu.
Monkeypatches the module-level `alarm_service` singleton instead of hitting
real MSSQL — this route's own job is just validating the incoming form and
forwarding it to AlarmService.clear_alarm(), which is already covered on
its own terms elsewhere. Deliberately no test here ever calls the real
AlarmRepository/MSSQL write path — same as test_acknowledge_alarm.py, this
stays at the fake-service level only.
"""

from app.routes import dashboard


class FakeAlarmService:
    def __init__(self):
        self.calls = []

    def clear_alarm(self, row_id, username):
        self.calls.append((row_id, username))
        return True


def test_clear_alarm_forwards_valid_form_to_service(client, monkeypatch):
    fake = FakeAlarmService()
    monkeypatch.setattr(dashboard, "alarm_service", fake)

    response = client.post("/alarms/clear", data={"id": "row-1", "username": "slethean"})

    assert response.status_code == 302
    assert fake.calls == [("row-1", "slethean")]


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
