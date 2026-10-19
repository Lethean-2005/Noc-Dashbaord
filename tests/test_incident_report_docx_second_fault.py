"""Tests for the "Add Second Fault" page-2 DOCX export
(incident_report_docx.py's _build_second_fault_section() and the
always-present Issued Time row) — real docx round-trips via
python-docx, same verification technique used to confirm the Duration
column-width fix earlier: build, save, re-open, inspect the actual
structure rather than trusting the code alone.
"""

from io import BytesIO

from docx import Document

from app.services.incident_report.incident_report_docx import build_docx

# A real, minimal, valid 1x1 PNG.
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

_BASE_REPORT = {
    "document_title": "Official Incident Report",
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
    "actions_taken_summary": "",
    "cause_of_outage": "x",
    "fault_gps_location": "x",
    "issued_time": "11-Sep-2026 09:00",
    "resolution": "x",
    "permanent_fixed": "Yes",
    "chronology_events": [],
}


def _fault_tbl(document):
    outer_cell = document.tables[2].rows[0].cells[0]
    return outer_cell.tables[3]


def test_issued_time_row_only_inserted_for_second_fault(app):
    with app.app_context():
        report = dict(
            _BASE_REPORT,
            has_second_fault="1",
            cause_of_outage_2="x",
            fault_gps_location_2="x",
            issued_time_2="x",
            resolution_2="x",
            permanent_fixed_2="x",
        )
        data = build_docx(report)
    d = Document(BytesIO(data))
    fault_tbl = _fault_tbl(d)
    assert len(fault_tbl.rows) == 6
    assert fault_tbl.rows[3].cells[0].text == "1st Issued Time (UTC+7):"
    assert fault_tbl.rows[3].cells[1].text == "11-Sep-2026 09:00"


def test_no_second_fault_has_no_issued_time_row_page_break_or_extra_tables(app):
    with app.app_context():
        report = dict(_BASE_REPORT, has_second_fault="")
        data = build_docx(report)
    d = Document(BytesIO(data))
    assert len(d.tables) == 3
    assert not any('type="page"' in p._p.xml for p in d.paragraphs)
    # No "1st " prefix, and no Issued Time row at all, without a second
    # fault — matches document.html's own irIssuedTimeRow staying
    # hidden for the same reason (see incident_report_service.py's
    # _SECOND_FAULT_TEXT_FIELDS note).
    fault_tbl = _fault_tbl(d)
    assert len(fault_tbl.rows) == 5
    assert fault_tbl.rows[1].cells[0].text == "Cause of Outage:"
    assert not any("Issued Time" in row.cells[0].text for row in fault_tbl.rows)


def test_single_fault_with_pictures_gets_picture_only_page_2(app):
    # A single fault with photos attached still gets a page 2 — just
    # "Picture Reference", no 2nd Fault Analysis table or Improvement
    # Plan since neither applies (see IR_SMART-IX1222_15-Sep-2026.pdf, a
    # real report shaped exactly this way).
    with app.app_context():
        report = dict(
            _BASE_REPORT,
            has_second_fault="",
            picture_references=[
                {"id": "p1", "filename": "a.png", "content_type": "image/png", "data_base64": _TINY_PNG_B64},
            ],
        )
        data = build_docx(report)
    d = Document(BytesIO(data))

    assert any('type="page"' in p._p.xml for p in d.paragraphs)

    fault_tbl = _fault_tbl(d)
    assert len(fault_tbl.rows) == 5
    assert fault_tbl.rows[1].cells[0].text == "Cause of Outage:"

    # 3 original top-level tables + 1 new page-2 bordering container —
    # no nested 2nd fault/plan tables inside it at all this time.
    assert len(d.tables) == 4
    page2_container = d.tables[3].rows[0].cells[0]
    assert len(page2_container.tables) == 0
    assert any(p.text == "Picture Reference" for p in page2_container.paragraphs)
    assert len(d.inline_shapes) == 1


def test_single_fault_with_no_pictures_has_no_page_2(app):
    with app.app_context():
        report = dict(_BASE_REPORT, has_second_fault="", picture_references=[])
        data = build_docx(report)
    d = Document(BytesIO(data))
    assert len(d.tables) == 3
    assert not any('type="page"' in p._p.xml for p in d.paragraphs)


def test_second_fault_adds_page_break_and_prefixes_first_fault_labels(app):
    with app.app_context():
        report = dict(
            _BASE_REPORT,
            has_second_fault="1",
            cause_of_outage_2="Fiber cut from an electrical explosion.",
            fault_gps_location_2="Svay Rieng Province, Cambodia.",
            issued_time_2="12th-Sep-2026 06:39 UTC+7",
            resolution_2="Laid new fiber and re-spliced.",
            permanent_fixed_2="Yes",
            improvement_plan=["Enhance customer communication.", "Review the affected route."],
            picture_references=[
                {"id": "p1", "filename": "a.png", "content_type": "image/png", "data_base64": _TINY_PNG_B64},
            ],
        )
        data = build_docx(report)
    d = Document(BytesIO(data))

    assert any('type="page"' in p._p.xml for p in d.paragraphs)

    fault_tbl = _fault_tbl(d)
    assert fault_tbl.rows[1].cells[0].text == "1st Cause of Outage:"
    assert fault_tbl.rows[3].cells[0].text == "1st Issued Time (UTC+7):"
    assert fault_tbl.rows[5].cells[0].text == "1st Permanent Fixed:"
    # Real superscript on the ordinal suffix, not just plain "1st" text.
    label_runs = fault_tbl.rows[1].cells[0].paragraphs[0].runs
    assert label_runs[1].text == "st"
    assert label_runs[1].font.superscript is True

    # 3 original top-level tables + 1 new page-2 bordering container
    # (the 2nd fault table, plan header, and plan body all live NESTED
    # inside that container, same as page 1's own tables all nest inside
    # table[2]) — pictures are plain inline images, not their own table.
    assert len(d.tables) == 4
    page2_container = d.tables[3].rows[0].cells[0]
    fault_tbl_2, plan_header, plan_table = page2_container.tables

    assert fault_tbl_2.rows[0].cells[0].text == "Fault Analysis & Resolution"
    assert fault_tbl_2.rows[1].cells[0].text == "2nd Cause of Outage:"
    assert fault_tbl_2.rows[1].cells[1].text == "Fiber cut from an electrical explosion."
    assert fault_tbl_2.rows[3].cells[0].text == "2nd Issued Time (UTC+7):"
    assert fault_tbl_2.rows[5].cells[1].text == "Yes"
    label_runs_2 = fault_tbl_2.rows[1].cells[0].paragraphs[0].runs
    assert label_runs_2[1].text == "nd"
    assert label_runs_2[1].font.superscript is True

    assert plan_header.rows[0].cells[0].text == "Improvement and preventive plan"

    # Improvement Plan's own body is a real bordered table (one row per
    # line), not free-floating text.
    assert plan_table.rows[0].cells[0].text == "TELCOTECH will take the following actions:"
    assert plan_table.rows[1].cells[0].text == "1.Enhance customer communication."
    assert plan_table.rows[2].cells[0].text == "2.Review the affected route."

    page2_paragraphs = [p.text for p in page2_container.paragraphs]
    assert "Picture Reference" in page2_paragraphs
    picture_para = next(p for p in page2_container.paragraphs if p.text == "Picture Reference")
    assert picture_para.runs[0].font.bold is True

    assert len(d.inline_shapes) == 1


def test_second_fault_with_no_pictures_or_plan_items_still_builds(app):
    with app.app_context():
        report = dict(
            _BASE_REPORT,
            has_second_fault="1",
            cause_of_outage_2="x",
            fault_gps_location_2="x",
            issued_time_2="x",
            resolution_2="x",
            permanent_fixed_2="x",
            improvement_plan=[],
            picture_references=[],
        )
        data = build_docx(report)
    d = Document(BytesIO(data))
    assert len(d.inline_shapes) == 0
    page2_container = d.tables[3].rows[0].cells[0]
    assert any(p.text == "Picture Reference" for p in page2_container.paragraphs)


def test_picture_data_survives_base64_round_trip(app):
    with app.app_context():
        report = dict(
            _BASE_REPORT,
            has_second_fault="1",
            cause_of_outage_2="x",
            fault_gps_location_2="x",
            issued_time_2="x",
            resolution_2="x",
            permanent_fixed_2="x",
            improvement_plan=[],
            picture_references=[
                {"id": "p1", "filename": "a.png", "content_type": "image/png", "data_base64": _TINY_PNG_B64},
                {"id": "p2", "filename": "b.png", "content_type": "image/png", "data_base64": _TINY_PNG_B64},
            ],
        )
        data = build_docx(report)
    d = Document(BytesIO(data))
    assert len(d.inline_shapes) == 2
    for shape in d.inline_shapes:
        image_part = shape._inline.graphic.graphicData.pic.blipFill.blip.embed
        assert image_part
