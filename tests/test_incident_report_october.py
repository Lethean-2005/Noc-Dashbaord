"""October reference mapping, saved-report compatibility, and real editor behavior."""
from io import BytesIO
from hashlib import sha256
import json
from pathlib import Path

from docx import Document
from werkzeug.datastructures import MultiDict

from app.services.incident_report.incident_report_docx import build_docx
from app.services.incident_report.incident_report_october import TEMPLATE
from app.services.incident_report.incident_report_service import IncidentReportService


def report():
    return dict(incident_layout="smart_oct_2026", document_title="Official Incident Report",
                file_name="IR_TEST", prepared_by="Test NOC", incident_number="TCT#TEST",
                customers_impacted="Test Customer", service_disruption="TEST-A/TEST-B",
                service_type="IPLC", symptom="Down", time_of_complaint="19-Oct-2026 16:59",
                response_time="19-Oct-2026 17:05", time_issue="19-Oct-2026 16:56",
                restored_time="19-Oct-2026 19:56", duration_of_interruption="03hrs 00mins",
                cause_of_outage="First verified fault", resolution="First recovery",
                permanent_fixed="Permanently fixed.", has_second_fault="1",
                cause_of_outage_2="Second verified fault", resolution_2="Second recovery",
                permanent_fixed_2="Monitoring", chronology_events=[
                    {"date":"19-Oct-2026", "time":"23:58", "description":"First activity"},
                    {"date":"20-Oct-2026", "time":"00:05", "description":"Second activity"}],
                summary_remarks={"time_issue":"Observed by monitoring"})


def test_packaged_template_is_the_supplied_reference():
    # Pin the supplied reference without depending on an untracked local upload.
    assert sha256(TEMPLATE.read_bytes()).hexdigest() == "4fefabcc6db4ad40d364f5c2d6d0b46798b22ad89bd47b86e65075cdb03e8030"


def test_reference_export_maps_distinct_times_and_both_faults_without_sample_leaks():
    item = report()
    document = Document(BytesIO(build_docx(item)))
    table = document.tables[0]
    assert len(document.tables) == 1
    assert table.rows[7].cells[1].text == item["time_of_complaint"]
    assert table.rows[8].cells[1].text == item["response_time"]
    assert table.rows[9].cells[1].text == item["time_issue"]
    assert table.rows[9].cells[2].text == "Observed by monitoring"
    text = "\n".join(cell.text for row in table.rows for cell in row.cells)
    for expected in ["19-Oct-2026   23:58", "20-Oct-2026   00:05", "Second recovery", "Monitoring"]:
        assert expected in text
    for sample in ["MX1453", "1998942", "rodent", "Johor"]:
        assert sample not in text
    reference = Document(TEMPLATE)
    assert document.sections[0].page_width == reference.sections[0].page_width
    from docx.oxml.ns import qn
    assert table._tbl.tblGrid.xml == reference.tables[0]._tbl.tblGrid.xml
    assert table._tbl.tblPr.find(qn("w:tblpPr")) is None
    assert table._tbl.tblPr.find(qn("w:tblInd")).get(qn("w:w")) == "-366"
    assert table.rows[0].cells[0]._tc.tcPr.xml == reference.tables[0].rows[0].cells[0]._tc.tcPr.xml
    assert document.sections[0].header._element.xml == reference.sections[0].header._element.xml


def test_single_fault_does_not_export_the_sample_second_fault():
    item = report()
    item["has_second_fault"] = ""
    document = Document(BytesIO(build_docx(item)))
    text = "\n".join(cell.text for row in document.tables[0].rows for cell in row.cells)
    assert "2nd Fault" not in text
    assert "Second recovery" not in text
    assert "First recovery" in text


def test_new_form_saves_and_reopens_all_new_fields(client):
    item = report()
    form = MultiDict({key:value for key,value in item.items() if isinstance(value,str)})
    form.add("event_date", "19-Oct-2026")
    form.add("event_time", "16:56")
    form.add("event_description", "Detected test outage")
    form.add("summary_remark_key", "time_issue")
    form.add("summary_remark", "Monitoring")
    form["intent"] = "final"
    response = client.post("/incident-report/save", data=form)
    assert response.status_code == 302
    report_id = response.location.split("id=")[1]
    saved = IncidentReportService().get_report(report_id)
    for field in ["incident_layout", "prepared_by", "service_type", "symptom", "time_issue", "response_time"]:
        assert saved[field] == item[field]
    assert saved["status"] == "Final"
    assert saved["summary_remarks"]["time_issue"] == "Monitoring"
    page = client.get(response.location)
    assert page.status_code == 200
    assert b'data-incident-layout="smart_oct_2026"' in page.data


def test_new_report_defaults_to_reference_but_legacy_report_is_not_migrated_by_viewing(client):
    assert b'data-incident-layout="smart_oct_2026"' in client.get("/incident-report/").data
    service = IncidentReportService()
    legacy_id = service.create_report({"file_name":"Legacy", "issue_reported":"Keep original note",
                                       "report_type":"incident", "picture_references_json":"[]"})
    old = client.get("/incident-report/?id="+legacy_id)
    assert b'data-incident-layout="smart_oct_2026"' not in old.data
    assert b'Use updated template' in old.data
    preview = client.get("/incident-report/?id="+legacy_id+"&layout=current")
    assert b'data-incident-layout="smart_oct_2026"' in preview.data
    assert b'value="Keep original note"' in preview.data
    assert not service.get_report(legacy_id)["incident_layout"]


def test_new_completion_requires_reference_fields_but_not_removed_legacy_fields():
    item = report()
    item["chronology_events_json"] = json.dumps(item["chronology_events"])
    assert IncidentReportService.is_complete(item)
    item["response_time"] = ""
    assert not IncidentReportService.is_complete(item)


def test_optional_plan_and_photo_export_while_legacy_notes_stay_hidden():
    from tests.test_incident_report_docx_second_fault import _TINY_PNG_B64
    item = report()
    item.update(issue_reported="Saved note", fault_gps_location="Saved location",
                improvement_plan=["Saved preventive action"], picture_references=[
                    {"filename":"photo.png", "data_base64":_TINY_PNG_B64}])
    document = Document(BytesIO(build_docx(item)))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Saved preventive action" not in text
    assert len(document.tables) == 1
    assert "Additional incident details" not in text
    assert "Saved note" not in text
    assert len(document.inline_shapes) == 1


def test_october_editor_controls_and_save_roundtrip_in_browser(app, tmp_path):
    import threading
    import pytest
    playwright = pytest.importorskip("playwright.sync_api")
    from werkzeug.serving import make_server
    edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    if not edge.exists():
        pytest.skip("Installed Edge browser is unavailable")
    app.config["WTF_CSRF_ENABLED"] = True
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width":1440,"height":1050})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/incident-report/", wait_until="networkidle")
            values = report()
            for name in ("incident_number", "customers_impacted", "service_disruption", "service_type", "symptom",
                         "time_of_complaint", "response_time", "time_issue", "restored_time",
                         "cause_of_outage", "resolution", "permanent_fixed"):
                page.locator('[name="'+name+'"]').fill(values[name])
            assert page.locator('[name="duration_of_interruption"]').input_value() == "03hrs 00mins"
            assert page.locator('[name="time_of_complaint"]').input_value() == values["time_of_complaint"]
            page.locator("#irAddEvent").click()
            assert page.locator('[name="event_date"]').input_value() == "19-Oct-2026"
            page.locator('[name="event_description"]').fill("Detected test outage")
            page.locator("#irAddSecondFault").click()
            assert page.locator("#irPage2").is_visible()
            for name in ("cause_of_outage_2", "resolution_2", "permanent_fixed_2"):
                page.locator('[name="'+name+'"]').fill(values[name])
            from tests.test_incident_report_docx_second_fault import _TINY_PNG_B64
            import base64
            for fault in ("1", "2"):
                with page.expect_file_chooser() as chooser:
                    page.locator("#irAddPicture"+fault).click()
                chooser.value.set_files({"name":"fault-"+fault+".png", "mimeType":"image/png", "buffer":base64.b64decode(_TINY_PNG_B64)})
                assert page.locator("#irPictureList"+fault+" img").count() == 1
            page.screenshot(path=str(tmp_path/"editor.png"),full_page=True)
            page.locator("#irSaveDraftBtn").click()
            page.wait_for_load_state("networkidle")
            assert page.locator('[name="time_issue"]').input_value() == values["time_issue"]
            assert page.locator('[name="service_type"]').input_value() == "IPLC"
            assert page.locator("#irPage2").is_visible()
            for fault in ("1", "2"):
                assert page.locator("#irPictureList"+fault+" img").count() == 1
                assert page.locator("#irPictureList"+fault+" .ir-picture-filename").inner_text() == "fault-"+fault+".png"
            # Recover from a lost browser session without losing the open draft/photos.
            page.context.clear_cookies()
            page.locator('[name="symptom"]').fill("Edited after session loss")
            page.locator("#irRemoveSecondFault").click()
            page.locator("#irSaveDraftBtn").click()
            page.wait_for_load_state("networkidle")
            assert page.locator('[name="symptom"]').input_value() == "Edited after session loss"
            page.route("**/incident-report/csrf", lambda route: route.fulfill(status=503, body="Unavailable"))
            page.locator('[name="symptom"]').fill("Retain unsaved edit")
            page.locator("#irSaveDraftBtn").click()
            page.get_by_role("alert").filter(has_text="Unable to prepare the save").wait_for()
            assert page.locator('[name="symptom"]').input_value() == "Retain unsaved edit"
            page.unroute("**/incident-report/csrf")
            page.locator("#irSaveDraftBtn").click()
            page.wait_for_load_state("networkidle")
            assert page.locator('[name="symptom"]').input_value() == "Retain unsaved edit"
            page.locator("#irAddSecondFault").click()
            assert page.locator("#irPictureList2 img").count() == 1
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        thread.join()


def test_duration_uses_occurrence_not_complaint_and_rejects_reversed_dates():
    service = IncidentReportService()
    item = report()
    form = MultiDict({key:value for key,value in item.items() if isinstance(value,str)})
    form["duration_of_interruption"] = "wrong client duration"
    form.add("event_date", "19-Oct-2026")
    form.add("event_time", "16:56")
    form.add("event_description", "Detected")
    fields = service.parse_form(form)
    assert fields["duration_of_interruption"] == "03hrs 00mins"
    assert service.is_complete(fields)
    fields["restored_time"] = "19-Oct-2026 16:55"
    assert not service.is_complete(fields)
    fields["restored_time"] = "31-Feb-2026 12:00"
    assert not service.is_complete(fields)


def test_long_chronology_and_multiline_faults_preserve_all_content():
    item = report()
    item["chronology_events"] = [{"date":"19-Oct-2026","time":"16:56","description":f"Activity {index:03d} " + "Detail "*20} for index in range(80)]
    item["cause_of_outage"] = "Cause line one\nCause line two"
    document = Document(BytesIO(build_docx(item)))
    text = "\n".join(cell.text for row in document.tables[0].rows for cell in row.cells)
    assert "Activity 000" in text and "Activity 079" in text
    assert "Cause line one\nCause line two" in text
    title = next(row.cells[0] for row in document.tables[0].rows if "Description of the Root Cause" in row.cells[0].text)
    assert all(str(run.font.color.rgb) == "000000" for p in title.paragraphs for run in p.runs)


def test_custom_title_replaces_both_header_variants_without_changing_service_record_label():
    item = report()
    item["document_title"] = "Customer Incident Review"
    document = Document(BytesIO(build_docx(item)))
    text = "".join(document.sections[0].header._element.xpath(".//w:t/text()"))
    assert text.count("Customer Incident Review") == 2
    assert "Official Incident Report" not in text
    assert text.count("Telcotech-FRM02-Service Performance Record") == 2


def test_fault_picture_uploads_keep_grouping_and_existing_general_photo(client):
    from tests.test_incident_report_docx_second_fault import _TINY_PNG_B64
    import base64
    picture = base64.b64decode(_TINY_PNG_B64)
    service = IncidentReportService()
    report_id = service.create_report({"report_type":"incident", "incident_layout":"smart_oct_2026", "file_name":"Photo test",
        "picture_references_json":json.dumps([{"id":"existing", "filename":"original.png", "content_type":"image/png", "data_base64":_TINY_PNG_B64}])})
    response = client.post("/incident-report/save", data={"report_id":report_id,"file_name":"Photo test",
        "incident_layout":"smart_oct_2026", "has_second_fault":"1", "keep_picture_id":"existing",
        "picture_reference_1":(BytesIO(picture),"first.png"), "picture_reference_2":(BytesIO(picture),"second.png")})
    assert response.status_code == 302
    saved = service.get_report(report_id)
    assert [(pic["filename"],pic.get("fault")) for pic in saved["picture_references"]] == [
        ("original.png",None),("first.png","1"),("second.png","2")]
    page = client.get(response.location)
    assert b"General Picture Reference" in page.data
    assert b"Additional incident details" not in page.data
    document = Document(BytesIO(build_docx(saved)))
    text = "\n".join(p.text for p in document.paragraphs)
    assert text.index("1st Fault - Picture Reference") < text.index("first.png")
    assert text.index("2nd Fault - Picture Reference") < text.index("second.png")
    assert "original.png" in text
    assert len(document.inline_shapes) == 3


def test_single_fault_can_have_photo_without_adding_second_fault():
    from tests.test_incident_report_docx_second_fault import _TINY_PNG_B64

    item = report()
    item["has_second_fault"] = ""
    item["picture_references"] = [{"filename":"first.png","fault":"1","data_base64":_TINY_PNG_B64}]
    document = Document(BytesIO(build_docx(item)))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "1st Fault - Picture Reference" in text
    assert "2nd Fault - Picture Reference" not in text
    assert len(document.inline_shapes) == 1


def test_tall_fault_photo_fits_page_without_distortion():
    import base64
    from PIL import Image

    data = BytesIO()
    Image.new("RGB", (100, 1000), "white").save(data, format="PNG")
    item = report()
    item["picture_references"] = [
        {
            "filename": "tall.png",
            "fault": "2",
            "data_base64": base64.b64encode(data.getvalue()).decode(),
        }
    ]
    document = Document(BytesIO(build_docx(item)))
    shape = document.inline_shapes[0]
    assert shape.height <= 6.5 * 914400
    assert abs(shape.width / shape.height - .1) < .001


def test_removed_additional_section_preserves_legacy_values_on_save(client):
    from lxml import html
    service = IncidentReportService()
    report_id = service.create_report({"file_name":"Retain notes", "report_type":"incident",
        "incident_layout":"smart_oct_2026", "issue_reported":"Saved original note",
        "fault_gps_location":"Saved location", "improvement_plan_json":json.dumps(["Saved original plan"]), "picture_references_json":"[]"})
    page = client.get("/incident-report/?id="+report_id)
    assert b"Additional incident details" not in page.data
    document = html.fromstring(page.data)
    form = MultiDict()
    for element in document.xpath('//form[@id="incidentReportForm"]//input[@type="hidden"]'):
        if element.get("name"):
            form.add(element.get("name"), element.get("value", ""))
    form["file_name"] = "Retain notes"
    assert client.post("/incident-report/save",data=form).status_code == 302
    saved = service.get_report(report_id)
    assert saved["issue_reported"] == "Saved original note"
    assert saved["fault_gps_location"] == "Saved location"
    assert saved["improvement_plan"] == ["Saved original plan"]
    assert b"Improvement and Preventive Plan" not in page.data
    exported = Document(BytesIO(build_docx(saved)))
    assert len(exported.tables) == 1
    assert "Saved original note" not in "\n".join(p.text for p in exported.paragraphs)


def test_fault_labels_wrap_inside_the_reference_column_without_shrinking_fonts():
    from docx.oxml.ns import qn
    from docx.enum.table import WD_ROW_HEIGHT_RULE
    for has_second_fault in ("", "1"):
        item = report()
        item["has_second_fault"] = has_second_fault
        document = Document(BytesIO(build_docx(item)))
        fault_rows = [row for row in document.tables[0].rows if "Cause of" in row.cells[0].text]
        assert len(fault_rows) == (2 if has_second_fault else 1)
        for row in fault_rows:
            cell = row.cells[0]
            assert "Cause of\nOutage:" in cell.text
            assert cell.width == Document(TEMPLATE).tables[0].rows[24].cells[0].width
            assert row.height_rule == WD_ROW_HEIGHT_RULE.AT_LEAST
            assert cell._tc.tcPr.find(qn("w:noWrap")) is None
            assert cell._tc.tcPr.find(qn("w:shd")).get(qn("w:fill")) == "E36C0A"
            for paragraph in cell.paragraphs:
                assert paragraph.paragraph_format.left_indent.pt == 5.1
                assert paragraph.paragraph_format.right_indent.pt == 5.1
            assert all(run.font.size.pt == 10 for p in cell.paragraphs for run in p.runs if run.font.size)


def test_all_cell_borders_use_one_width_to_prevent_white_shading_seams():
    from docx.oxml.ns import qn
    for second in ("", "1"):
        item = report()
        item["has_second_fault"] = second
        document = Document(BytesIO(build_docx(item)))
        widths = set()
        for row in document.tables[0].rows:
            for cell in row._tr.tc_lst:
                borders = cell.get_or_add_tcPr().find(qn("w:tcBorders"))
                if borders is not None:
                    widths.update(edge.get(qn("w:sz")) for edge in borders if edge.get(qn("w:val")) == "single")
        assert widths == {"4"}
