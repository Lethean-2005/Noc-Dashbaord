"""Report identity, stale form, partial input and picker payload regressions."""
import json
from werkzeug.datastructures import MultiDict
from app.services.incident_report.incident_report_service import IncidentReportService
from app.services.incident_report.incident_report_october import LAYOUT


def test_missing_report_never_creates_replacement(client):
    service = IncidentReportService()
    assert client.get("/incident-report/?id=missing-report").status_code == 404
    assert client.post("/incident-report/save",data={"report_id":"missing-report","file_name":"Lost tab"}).status_code == 404
    assert not service.list_reports()


def test_final_report_cannot_be_overwritten_by_stale_draft_tab(client):
    service = IncidentReportService()
    key = service.create_report({"file_name":"Original", "report_type":"incident"})
    service.set_status(key,"Final")
    assert client.post("/incident-report/save",data={"report_id":key,"file_name":"Stale edit"}).status_code == 409
    saved = service.get_report(key)
    assert saved["file_name"] == "Original" and saved["status"] == "Final"


def test_stale_legacy_form_cannot_downgrade_current_layout(client):
    service = IncidentReportService()
    key = service.create_report({"file_name":"Current", "report_type":"incident", "incident_layout":LAYOUT,
                                 "issue_reported":"Keep this note"})
    assert client.post("/incident-report/save",data={"report_id":key,"file_name":"Old tab"}).status_code == 409
    saved = service.get_report(key)
    assert saved["incident_layout"] == LAYOUT
    assert saved["issue_reported"] == "Keep this note"


def test_incomplete_final_save_keeps_draft_and_explains_problem(client):
    response = client.post("/incident-report/save",data={"file_name":"Incomplete", "incident_layout":LAYOUT,"intent":"final"})
    assert response.status_code == 302 and "finalize_error=1" in response.location
    assert b"This report isn't complete yet" in client.get(response.location).data
    key = IncidentReportService().list_reports()[0]["id"]
    assert IncidentReportService().get_report(key)["status"] == "Draft"


def test_partial_chronology_and_smart_rows_are_preserved_for_draft():
    service = IncidentReportService()
    form = MultiDict([("event_description","Only a note was submitted")])
    events = json.loads(service.parse_form(form)["chronology_events_json"])
    assert events == [{"date":"", "time":"", "description":"Only a note was submitted"}]
    fields = service.parse_smart_form(MultiDict([("circuit_id","TEST-CIRCUIT"),("outage_notes","Retain partial outage note")]))
    assert json.loads(fields["smart_active_circuits_json"])[0]["circuit_id"] == "TEST-CIRCUIT"
    assert json.loads(fields["smart_services_outage_json"])[0]["notes"] == "Retain partial outage note"


def test_picker_does_not_load_or_decode_report_photo_payloads(app):
    service = IncidentReportService()
    key = service.create_report({"file_name":"Metadata only", "report_type":"incident", "picture_references_json":"not valid JSON"})
    rows = service.list_reports()
    assert rows[0]["id"] == key and rows[0]["file_name"] == "Metadata only"
    assert "picture_references_json" not in rows[0]
    assert "chronology_events_json" not in rows[0]


def test_repeated_draft_save_with_refreshed_csrf_session(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    token_response = client.get("/incident-report/csrf")
    assert token_response.headers["Cache-Control"] == "no-store"
    token = token_response.json["csrf_token"]
    first = client.post("/incident-report/save", data={"csrf_token": token,
        "file_name": "First draft", "incident_layout": LAYOUT, "intent": "draft"})
    assert first.status_code == 302
    service = IncidentReportService()
    key = service.list_reports()[0]["id"]
    client.delete_cookie(app.config["SESSION_COOKIE_NAME"])
    rejected = client.post("/incident-report/save", data={"csrf_token": token,
        "report_id": key, "file_name": "Rejected", "incident_layout": LAYOUT})
    assert rejected.status_code == 400
    # The shared fixture retains an app context; real HTTP requests create a new g.
    from flask import g
    g.pop("csrf_token", None)
    fresh = client.get("/incident-report/csrf").json["csrf_token"]
    second = client.post("/incident-report/save", data={"csrf_token": fresh,
        "report_id": key, "file_name": "Second draft", "incident_layout": LAYOUT, "intent": "draft"})
    assert second.status_code == 302
    assert service.get_report(key)["file_name"] == "Second draft"
    assert len(service.list_reports()) == 1
