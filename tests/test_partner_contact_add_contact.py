"""Tests for POST /partner-contact/add-contact (partner_contact.add_contact)
— the "Add Contact" button per row (see partner_contact/index.html's third
modal mode). Monkeypatches the module-level `_service`/`_sync_service`
singletons instead of hitting real MSSQL, same fake-service pattern as
test_clear_alarm.py/test_acknowledge_alarm.py. This route's own job is
attaching a new Contact to an EXISTING Partner without ever creating a
duplicate Partner row — see partner_contact_service.py's module docstring
for the bug this fixes.
"""

from app.routes import partner_contact


class FakePartnerContactService:
    def __init__(self, add_contact_result=True):
        self.calls = []
        self._add_contact_result = add_contact_result

    def add_contact(self, **kwargs):
        self.calls.append(kwargs)
        return self._add_contact_result


class FakeSyncService:
    def __init__(self):
        self.sync_calls = 0

    def sync(self):
        self.sync_calls += 1


def test_add_contact_forwards_valid_form_to_service(client, monkeypatch):
    fake_service = FakePartnerContactService()
    fake_sync = FakeSyncService()
    monkeypatch.setattr(partner_contact, "_service", fake_service)
    monkeypatch.setattr(partner_contact, "_sync_service", fake_sync)

    response = client.post(
        "/partner-contact/add-contact",
        data={
            "partner_id": "partner-1",
            "partner_name": "Telcotech",
            "partner_type": "ISP",
            "username": "slethean",
            "escalation_level": "L2",
            "escalation_matrix": "NOC -> Manager",
            "contact_name": "Jane Doe",
            "contact_role": "Engineer",
            "phone_number": "+855 12 345 678",
            "email": "jane@partner.com",
        },
    )

    assert response.status_code == 302
    assert fake_service.calls == [
        {
            "partner_id": "partner-1",
            "escalation_level": "L2",
            "escalation_matrix": "NOC -> Manager",
            "contact_name": "Jane Doe",
            "contact_role": "Engineer",
            "phone_number": "+855 12 345 678",
            "email": "jane@partner.com",
            "remark": "",
            "username": "slethean",
        }
    ]
    assert fake_sync.sync_calls == 1
    location = response.headers["Location"]
    assert "status=contact_added" in location
    assert "partner_id=partner-1" in location
    assert "partner_name=Telcotech" in location


def test_add_contact_skips_service_call_when_partner_id_missing(client, monkeypatch):
    fake_service = FakePartnerContactService()
    monkeypatch.setattr(partner_contact, "_service", fake_service)

    response = client.post(
        "/partner-contact/add-contact",
        data={"partner_id": "", "username": "slethean"},
    )

    assert response.status_code == 302
    assert fake_service.calls == []
    assert "status=error" in response.headers["Location"]


def test_add_contact_skips_service_call_when_username_missing(client, monkeypatch):
    fake_service = FakePartnerContactService()
    monkeypatch.setattr(partner_contact, "_service", fake_service)

    response = client.post(
        "/partner-contact/add-contact",
        data={"partner_id": "partner-1", "username": ""},
    )

    assert response.status_code == 302
    assert fake_service.calls == []
    assert "status=error" in response.headers["Location"]


def test_add_contact_does_not_resync_when_service_returns_falsy(client, monkeypatch):
    fake_service = FakePartnerContactService(add_contact_result=None)
    fake_sync = FakeSyncService()
    monkeypatch.setattr(partner_contact, "_service", fake_service)
    monkeypatch.setattr(partner_contact, "_sync_service", fake_sync)

    response = client.post(
        "/partner-contact/add-contact",
        data={
            "partner_id": "partner-1",
            "username": "slethean",
            "escalation_level": "L2",
            "escalation_matrix": "NOC -> Manager",
            "contact_name": "Jane Doe",
            "contact_role": "Engineer",
            "phone_number": "+855 12 345 678",
            "email": "jane@partner.com",
        },
    )

    assert response.status_code == 302
    assert len(fake_service.calls) == 1
    assert fake_sync.sync_calls == 0
    assert "status=error" in response.headers["Location"]
