"""Tests for POST /alarms/acknowledge (dashboard.acknowledge_alarm) — the
Acknowledge/Modify popup's submit target for EZE/TCT/ISP POP. Monkeypatches
the module-level `alarm_service`/`alarm_sync_service` singletons instead of
hitting real MSSQL — this route's own job is just validating the incoming
form and forwarding it to AlarmService.acknowledge_note() (already covered
on its own terms elsewhere), then patching just that one row into the local
cache via AlarmSyncService.apply_acknowledge_result() (replaced a full
sync_scope() table re-fetch — see the route's own docstring) so the
redirect the user lands on doesn't show stale data — that patch call must
be faked here too, or this test would try a real MSSQL round-trip.
"""

from app.routes import dashboard


class FakeAlarmService:
    def __init__(self):
        self.calls = []

    def acknowledge_note(self, row_id, tt_inc_wo_id, note, username):
        self.calls.append((row_id, tt_inc_wo_id, note, username))
        return {"NOTE": f"{tt_inc_wo_id}: {note}", "ACK": "2026-01-01", "AB": username, "MD": "", "MB": ""}


class FakeAlarmSyncService:
    def __init__(self):
        self.apply_acknowledge_calls = []

    def apply_acknowledge_result(self, source, row_id, result):
        self.apply_acknowledge_calls.append((source, row_id, result))


def test_acknowledge_alarm_forwards_valid_form_to_service(client, monkeypatch):
    fake = FakeAlarmService()
    fake_sync = FakeAlarmSyncService()
    monkeypatch.setattr(dashboard, "alarm_service", fake)
    monkeypatch.setattr(dashboard, "alarm_sync_service", fake_sync)

    response = client.post(
        "/alarms/acknowledge",
        data={
            "id": "row-1",
            "tt_inc_wo_id": "TT-1",
            "note": "checked",
            "username": "slethean",
            "source": "eze",
        },
    )

    assert response.status_code == 302
    assert fake.calls == [("row-1", "TT-1", "checked", "slethean")]
    assert fake_sync.apply_acknowledge_calls == [
        ("eze", "row-1", {"NOTE": "TT-1: checked", "ACK": "2026-01-01", "AB": "slethean", "MD": "", "MB": ""})
    ]


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
