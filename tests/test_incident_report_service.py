"""Tests for IncidentReportService's "Add Second Fault" support —
parse_form()'s handling of the 2nd-fault fields, Improvement Plan
list, and Picture Reference uploads, plus is_complete()'s conditional
validation of the 2nd-fault fields. Most reports have exactly one
fault (has_second_fault empty) — these tests exist specifically to
lock in that an ordinary single-fault report is never blocked by, or
required to fill in, the second-fault fields (see
incident_report_service.py's own note on why _SECOND_FAULT_TEXT_FIELDS
is kept out of _TEXT_FIELDS/_REQUIRED_FIELDS).
"""

import json

from app.services.incident_report.incident_report_service import IncidentReportService

_BASE_REQUIRED = {
    "document_title": "Official Incident Report",
    "file_name": "IR_test",
    "incident_raised_by": "x",
    "incident_received_by": "x",
    "reported_date": "11-Sep-2026",
    "service_disruption": "x",
    "incident_date": "11-Sep-2026",
    "report_time": "10:00",
    "incident_number": "TCT#1",
    "incident_category": "x",
    "customers_impacted": "x",
    "duration_of_interruption": "x",
    "raise_time": "11-Sep-2026 10:00",
    "restored_time": "11-Sep-2026 11:00",
    "details_date_and_time": "x",
    "time_of_complaint": "x",
    "issue_reported": "x",
    "actions_taken_summary": "x",
    "cause_of_outage": "x",
    "fault_gps_location": "x",
    "issued_time": "11-Sep-2026 09:00",
    "resolution": "x",
    "permanent_fixed": "Yes",
}


class FakeForm:
    """Minimal stand-in for Flask's request.form — .get()/.getlist()
    over a plain dict of key -> single value or list of values."""

    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        value = self._data.get(key, default)
        if isinstance(value, list):
            return value[0] if value else default
        return value

    def getlist(self, key):
        value = self._data.get(key, [])
        return value if isinstance(value, list) else [value]


class FakeFile:
    """Minimal stand-in for a Werkzeug FileStorage — just enough of the
    interface _build_picture_references() actually uses."""

    def __init__(self, filename, content_type, data):
        self.filename = filename
        self.content_type = content_type
        self._data = data

    def read(self):
        return self._data


class FakeFiles:
    def __init__(self, data):
        self._data = data

    def getlist(self, key):
        return self._data.get(key, [])


def _form(**overrides):
    data = dict(_BASE_REQUIRED)
    data.update(overrides)
    return FakeForm(data)


def test_parse_form_second_fault_fields_are_stripped(app):
    with app.app_context():
        svc = IncidentReportService()
        form = _form(
            has_second_fault="1",
            cause_of_outage_2="  fiber cut  ",
            fault_gps_location_2="  Svay Rieng  ",
            issued_time_2="12th-Sep-2026 06:39 UTC+7",
            resolution_2="  re-spliced  ",
            permanent_fixed_2="Yes",
        )
        fields = svc.parse_form(form)
        assert fields["has_second_fault"] == "1"
        assert fields["cause_of_outage_2"] == "fiber cut"
        assert fields["fault_gps_location_2"] == "Svay Rieng"
        assert fields["resolution_2"] == "re-spliced"
        assert fields["permanent_fixed_2"] == "Yes"


def test_parse_form_second_fault_fields_default_blank(app):
    with app.app_context():
        svc = IncidentReportService()
        fields = svc.parse_form(_form())
        assert fields["has_second_fault"] == ""
        assert fields["cause_of_outage_2"] == ""
        assert fields["fault_gps_location_2"] == ""
        assert fields["issued_time_2"] == ""
        assert fields["resolution_2"] == ""
        assert fields["permanent_fixed_2"] == ""


def test_parse_form_improvement_plan_drops_blank_items(app):
    with app.app_context():
        svc = IncidentReportService()
        form = _form(improvement_item=["Enhance comms", "  ", "Review route"])
        fields = svc.parse_form(form)
        assert json.loads(fields["improvement_plan_json"]) == ["Enhance comms", "Review route"]


def test_parse_form_picture_upload_encodes_new_file(app):
    with app.app_context():
        svc = IncidentReportService()
        form = _form()
        files = FakeFiles({"picture_reference": [FakeFile("photo1.jpg", "image/jpeg", b"fakebytes")]})
        fields = svc.parse_form(form, files)
        pictures = json.loads(fields["picture_references_json"])
        assert len(pictures) == 1
        assert pictures[0]["filename"] == "photo1.jpg"
        assert pictures[0]["content_type"] == "image/jpeg"
        import base64
        assert base64.b64decode(pictures[0]["data_base64"]) == b"fakebytes"
        assert pictures[0]["id"]


def test_parse_form_picture_upload_skips_empty_file_input(app):
    with app.app_context():
        svc = IncidentReportService()
        files = FakeFiles({"picture_reference": [FakeFile("", "", b"")]})
        fields = svc.parse_form(_form(), files)
        assert json.loads(fields["picture_references_json"]) == []


def test_parse_form_keeps_existing_pictures_by_id_and_merges_new(app):
    with app.app_context():
        svc = IncidentReportService()
        existing = [
            {"id": "keep-me", "filename": "old1.jpg", "content_type": "image/jpeg", "data_base64": "b2xk"},
            {"id": "drop-me", "filename": "old2.jpg", "content_type": "image/jpeg", "data_base64": "b2xk"},
        ]
        form = _form(keep_picture_id="keep-me")
        files = FakeFiles({"picture_reference": [FakeFile("new.jpg", "image/jpeg", b"newbytes")]})
        fields = svc.parse_form(form, files, existing_pictures=existing)
        pictures = json.loads(fields["picture_references_json"])
        ids = [p["id"] for p in pictures]
        filenames = [p["filename"] for p in pictures]
        assert "keep-me" in ids
        assert "drop-me" not in ids
        assert "new.jpg" in filenames


def test_is_complete_single_fault_does_not_require_second_fault_fields(app):
    with app.app_context():
        fields = dict(_BASE_REQUIRED)
        fields["has_second_fault"] = ""
        fields["chronology_events_json"] = json.dumps(
            [{"date": "11-Sep-2026", "time": "10:00", "description": "x"}]
        )
        assert IncidentReportService.is_complete(fields) is True


def test_is_complete_second_fault_requires_all_five_fields(app):
    with app.app_context():
        fields = dict(_BASE_REQUIRED)
        fields["has_second_fault"] = "1"
        fields["chronology_events_json"] = json.dumps(
            [{"date": "11-Sep-2026", "time": "10:00", "description": "x"}]
        )
        fields["cause_of_outage_2"] = "x"
        fields["fault_gps_location_2"] = "x"
        fields["issued_time_2"] = "x"
        fields["resolution_2"] = "x"
        fields["permanent_fixed_2"] = ""  # missing
        assert IncidentReportService.is_complete(fields) is False

        fields["permanent_fixed_2"] = "Yes"
        assert IncidentReportService.is_complete(fields) is True
