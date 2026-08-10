"""Tests for POST /alarms/acknowledge (dashboard.acknowledge_alarm) — the
Acknowledge/Modify popup's submit target for EZE/TCT/ISP POP. Monkeypatches
the module-level `alarm_service` singleton instead of hitting real MSSQL —
this route's own job is just validating the incoming form and forwarding it
to AlarmService.acknowledge_note(), which is already covered on its own
terms elsewhere.
"""

from app.routes import dashboard


class FakeAlarmService:
    def __init__(self):
        self.calls = []

    def acknowledge_note(self, row_id, tt_inc_wo_id, note, username):
        self.calls.append((row_id, tt_inc_wo_id, note, username))
        return True


def test_acknowledge_alarm_forwards_valid_form_to_service(client, monkeypatch):
    fake = FakeAlarmService()
    monkeypatch.setattr(dashboard, "alarm_service", fake)

    response = client.post(
        "/alarms/acknowledge",
        data={
            "id": "row-1",
            "tt_inc_wo_id": "TT-1",
            "note": "checked",
            "username": "slethean",
        },
    )

    assert response.status_code == 302
    assert fake.calls == [("row-1", "TT-1", "checked", "slethean")]


def test_acknowledge_alarm_skips_service_call_when_username_missing(client, monkeypatch):
    fake = FakeAlarmService()
    monkeypatch.setattr(dashboard, "alarm_service", fake)

    response = client.post(
        "/alarms/acknowledge",
        data={
            "id": "row-1",
            "tt_inc_wo_id": "TT-1",
            "note": "checked",
            "username": "",
        },
    )

    assert response.status_code == 302
    assert fake.calls == []


def test_acknowledge_alarm_skips_service_call_when_id_missing(client, monkeypatch):
    fake = FakeAlarmService()
    monkeypatch.setattr(dashboard, "alarm_service", fake)

    response = client.post(
        "/alarms/acknowledge",
        data={
            "id": "",
            "tt_inc_wo_id": "TT-1",
            "note": "checked",
            "username": "slethean",
        },
    )

    assert response.status_code == 302
    assert fake.calls == []


def test_acknowledge_alarm_skips_service_call_when_note_and_tt_inc_wo_both_blank(
    client, monkeypatch
):
    fake = FakeAlarmService()
    monkeypatch.setattr(dashboard, "alarm_service", fake)

    response = client.post(
        "/alarms/acknowledge",
        data={
            "id": "row-1",
            "tt_inc_wo_id": "",
            "note": "",
            "username": "slethean",
        },
    )

    assert response.status_code == 302
    assert fake.calls == []
