"""API aliases preserve validation and legacy behavior without source writes."""
import pytest

from app.routes.api import JSON_ROUTES


def test_api_catalog_lists_registered_endpoints(client):
    response = client.get("/api/v1/")
    assert response.status_code == 200
    assert response.json["version"] == "v1"
    assert len(response.json["endpoints"]) == len(JSON_ROUTES) + 1
    assert client.get("/api/v1").json == response.json


@pytest.mark.parametrize("path,endpoint,existing,method", JSON_ROUTES)
def test_api_alias_uses_original_handler_and_http_method(app, client, path, endpoint, existing, method):
    assert app.view_functions["api_v1." + endpoint] is app.view_functions[existing]
    if method == "POST":
        assert client.get("/api/v1" + path).status_code == 405


@pytest.mark.parametrize("legacy,versioned", [
    ("/map/sites.json", "/api/v1/map/sites"),
    ("/partner-contact/partner-contacts", "/api/v1/partner-contact/contacts"),
    ("/partner-contact/domains", "/api/v1/partner-contact/domains"),
    ("/partner-contact/escalation-levels", "/api/v1/partner-contact/escalation-levels"),
    ("/partner-contact/escalation-matrix-values", "/api/v1/partner-contact/escalation-matrix-values"),
    ("/partner-contact/check-name", "/api/v1/partner-contact/check-name"),
])
def test_get_api_matches_legacy_cache_response(client, legacy, versioned):
    old, new = client.get(legacy), client.get(versioned)
    assert old.status_code == new.status_code == 200
    assert old.is_json and new.is_json
    assert old.json == new.json


def test_mentor_validation_preserves_error_without_saving(client):
    old = client.post("/mentor/validate")
    new = client.post("/api/v1/mentor/validate")
    assert old.status_code == new.status_code == 400
    assert old.json == new.json


def test_api_post_retains_csrf_protection(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/api/v1/mentor/validate").status_code == 400


def test_map_api_returns_cached_payload_without_changing_schema(client, monkeypatch):
    from app.routes.map_view import map_view_service

    sites = [{"site_code": "TEST-SITE", "latitude": 11.5, "longitude": 104.9}]
    monkeypatch.setattr(map_view_service, "get_sites", lambda: sites)
    monkeypatch.setattr(map_view_service, "get_status_counts", lambda rows: {"total": len(rows)})
    monkeypatch.setattr(map_view_service, "get_pops", lambda: [])
    expected = {"sites": sites, "status_counts": {"total": 1}, "pops": []}
    assert client.get("/api/v1/map/sites").json == expected
    assert client.get("/map/sites.json").json == expected


def test_partner_api_retains_query_parameters(client, monkeypatch):
    from app.routes import partner_contact

    monkeypatch.setattr(partner_contact._repo, "fetch_all", lambda table: [
        {"partner_id": "A", "contact_id": "1", "contact_name": "Requested"},
        {"partner_id": "B", "contact_id": "2", "contact_name": "Other"},
    ])
    response = client.get("/api/v1/partner-contact/contacts?partner_id=A")
    assert [item["contact_name"] for item in response.json["contacts"]] == ["Requested"]


def test_partner_api_import_cannot_bypass_password(client, app):
    app.config["PARTNER_CONTACT_IMPORT_PASSWORD"] = "test-only-password"
    response = client.post("/api/v1/partner-contact/import", data={"import_password": "incorrect"})
    assert response.json == {"ok": False, "error": "bad_password"}


def test_pages_generate_versioned_json_urls(client):
    mentor = client.get("/mentor/")
    partners = client.get("/partner-contact")
    assert mentor.status_code == partners.status_code == 200
    assert b'data-validate-url="/api/v1/mentor/validate"' in mentor.data
    assert b'/api/v1/partner-contact/contacts' in partners.data
    assert b'/api/v1/partner-contact/import' in partners.data
