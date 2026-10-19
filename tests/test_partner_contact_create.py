"""Tests for POST /partner-contact/create (partner_contact.create) — the
Add Partner modal's submit target. Creates a Partner plus its first
Contact together, as one atomic batch (a single-item list into
PartnerContactService.create_partner_with_contacts() — see that method's
own docstring for the general "N contacts at once" case this is a
special case of). Monkeypatches the module-level `_service`/`_sync_service`
singletons instead of hitting real MSSQL, same fake-service pattern as
test_partner_contact_add_contact.py.
"""

from app.routes import partner_contact


class FakePartnerContactService:
    def __init__(self, result="new-partner-id"):
        self.calls = []
        self._result = result

    def partner_name_exists(self, partner_name):
        return False

    def create_partner_with_contacts(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


class FakeSyncService:
    def __init__(self):
        self.sync_calls = 0

    def sync(self):
        self.sync_calls += 1


def test_create_forwards_valid_form_to_service(client, monkeypatch):
    fake_service = FakePartnerContactService()
    fake_sync = FakeSyncService()
    monkeypatch.setattr(partner_contact, "_service", fake_service)
    monkeypatch.setattr(partner_contact, "_sync_service", fake_sync)

    response = client.post(
        "/partner-contact/create",
        data={
            "partner_name": "Telcotech",
            "partner_type": "ISP",
            "domain": "Cellcard",
            "remark": "New vendor",
            "username": "slethean",
            "escalation_level": "L1",
            "escalation_matrix": "NOC -> Manager",
            "contact_name": "Alice",
            "contact_role": "Engineer",
            "phone_number": "111",
            "email": "a@x.com",
        },
    )

    assert response.status_code == 302
    assert len(fake_service.calls) == 1
    call = fake_service.calls[0]
    assert call["partner_name"] == "Telcotech"
    assert call["partner_type"] == "ISP"
    assert call["domain"] == "Cellcard"
    assert call["username"] == "slethean"
    assert call["contacts"] == [{
        "escalation_level": "L1",
        "escalation_matrix": "NOC -> Manager",
        "contact_name": "Alice",
        "contact_role": "Engineer",
        "phone_number": "111",
        "email": "a@x.com",
        "remark": "New vendor",
    }]
    assert fake_sync.sync_calls == 1
    assert "status=created" in response.headers["Location"]


def test_create_allows_optional_contact_fields_to_be_blank(client, monkeypatch):
    """remark is the only contact field NOT in create()'s fields_filled
    check — escalation_level/escalation_matrix/contact_name/contact_role/
    phone_number/email are all required."""
    fake_service = FakePartnerContactService()
    fake_sync = FakeSyncService()
    monkeypatch.setattr(partner_contact, "_service", fake_service)
    monkeypatch.setattr(partner_contact, "_sync_service", fake_sync)

    response = client.post(
        "/partner-contact/create",
        data={
            "partner_name": "Telcotech",
            "partner_type": "ISP",
            "domain": "Cellcard",
            "username": "slethean",
            "escalation_level": "L1",
            "escalation_matrix": "NOC -> Manager",
            "contact_name": "Alice",
            "contact_role": "Engineer",
            "phone_number": "111",
            "email": "a@x.com",
        },
    )

    assert response.status_code == 302
    assert len(fake_service.calls) == 1
    assert fake_service.calls[0]["contacts"] == [{
        "escalation_level": "L1",
        "escalation_matrix": "NOC -> Manager",
        "contact_name": "Alice",
        "contact_role": "Engineer",
        "phone_number": "111",
        "email": "a@x.com",
        "remark": "",
    }]
    assert "status=created" in response.headers["Location"]


def test_create_skips_service_call_when_partner_name_missing(client, monkeypatch):
    fake_service = FakePartnerContactService()
    monkeypatch.setattr(partner_contact, "_service", fake_service)

    response = client.post(
        "/partner-contact/create",
        data={"partner_name": "", "partner_type": "ISP", "username": "slethean"},
    )

    assert response.status_code == 302
    assert fake_service.calls == []
    assert "status=error" in response.headers["Location"]


def test_create_skips_service_call_when_username_missing(client, monkeypatch):
    fake_service = FakePartnerContactService()
    monkeypatch.setattr(partner_contact, "_service", fake_service)

    response = client.post(
        "/partner-contact/create",
        data={"partner_name": "Telcotech", "partner_type": "ISP", "username": ""},
    )

    assert response.status_code == 302
    assert fake_service.calls == []
    assert "status=error" in response.headers["Location"]
