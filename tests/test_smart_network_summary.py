"""Section 3 follows section 2 even when submitted summary values are stale."""
import json

from werkzeug.datastructures import MultiDict

from app.services.incident_report.incident_report_service import IncidentReportService


def test_summary_uses_monthly_outages_and_ignores_stale_fault_values():
    form = MultiDict([
        ("outage_circuit", " MX1 "), ("outage_circuit", "MX2"),
        ("outage_circuit", ""),
        ("outage_jan", "99.9%"), ("outage_jan", "100%"), ("outage_jan", ""),
        ("fault_circuit", "OLD"), ("fault_jan", "wrong"),
    ])
    fields = IncidentReportService().parse_smart_form(form)
    rows = json.loads(fields["smart_fault_services_json"])
    assert fields["smart_fault_services_json"] == fields["smart_monthly_outage_json"]
    assert [row["circuit"] for row in rows] == ["MX1", "MX2"]
    assert [row["months"]["jan"] for row in rows] == ["99.9%", "100%"]


def test_clearing_monthly_outages_clears_summary():
    fields = IncidentReportService().parse_smart_form(MultiDict({"fault_circuit": "OLD"}))
    assert json.loads(fields["smart_fault_services_json"]) == []


def test_saved_report_and_exports_read_summary_from_monthly_data(app):
    service = IncidentReportService()
    fields = service.parse_smart_form(MultiDict({"outage_circuit": "MX1", "outage_nov": "99%"}))
    fields["smart_fault_services_json"] = '[{"circuit": "STALE"}]'
    report_id = service.create_report(fields)
    report = service.get_report(report_id)
    assert report["smart_fault_services"] == report["smart_monthly_outage"]
    assert report["smart_fault_services"][0]["circuit"] == "MX1"
