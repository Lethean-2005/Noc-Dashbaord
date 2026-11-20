"""Fill the October customer incident reference without rebuilding its layout."""
import base64
import re
from copy import deepcopy
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor, Twips
from docx.table import _Row

LAYOUT = "smart_oct_2026"
TEMPLATE = Path(__file__).parent / "template" / "incident_report_october.docx"
SUMMARY_FIELDS = (
    ("prepared_by", "TELCOTECH NOC"), ("incident_number", ""),
    ("customers_impacted", ""), ("service_disruption", ""),
    ("service_type", ""), ("symptom", ""), ("time_of_complaint", ""),
    ("response_time", ""), ("time_issue", ""), ("restored_time", ""),
    ("duration_of_interruption", ""),
)


def _write(cell, value):
    value = str(value or "")
    if cell.text == value:
        return
    paragraph = next((p for p in cell.paragraphs if p.text.strip()), cell.paragraphs[0])
    run = next((r for r in paragraph.runs if r.text.strip()), None)
    if run is None:
        run = paragraph.add_run()
    run.text = value
    for other in list(paragraph.runs):
        if other._element is not run._element:
            other._element.getparent().remove(other._element)
    for other in list(cell.paragraphs):
        if other._p is not paragraph._p:
            other._p.getparent().remove(other._p)


def _align_reference_table(document, table):
    """Keep the reference placement without Word's floating-table shading gap."""
    properties = table._tbl.tblPr
    floating = properties.find(qn("w:tblpPr"))
    if floating is None:
        return
    horizontal = int(floating.get(qn("w:tblpX"), "0"))
    vertical = int(floating.get(qn("w:tblpY"), "0"))
    properties.remove(floating)
    indent = properties.find(qn("w:tblInd"))
    if indent is None:
        indent = OxmlElement("w:tblInd")
        properties.append(indent)
    indent.set(qn("w:w"), str(horizontal))
    indent.set(qn("w:type"), "dxa")
    paragraph = document.add_paragraph()
    table._tbl.addprevious(paragraph._p)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Twips(max(0, vertical - document.sections[0].top_margin.twips - 20))
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(1)
    paragraph.add_run().font.size = Pt(1)
    spacing = properties.find(qn("w:tblCellSpacing"))
    if spacing is not None:
        properties.remove(spacing)


def _normalize_cell_borders(table):
    """Use the reference header's line width so Word fills cells up to every border."""
    reference = table.rows[0].cells[0]._tc.tcPr.find(qn("w:tcBorders"))
    left = reference.find(qn("w:left")) if reference is not None else None
    size = left.get(qn("w:sz"), "4") if left is not None else "4"
    for row in table.rows:
        for cell in row._tr.tc_lst:
            borders = cell.get_or_add_tcPr().find(qn("w:tcBorders"))
            if borders is not None:
                for edge in borders:
                    if edge.get(qn("w:val")) == "single":
                        edge.set(qn("w:sz"), size)


def _fit_fault_labels(rows):
    """Keep long labels inside the reference's narrow orange column."""
    for row in rows:
        cell = row.cells[0]
        properties = cell._tc.get_or_add_tcPr()
        no_wrap = properties.find(qn("w:noWrap"))
        if no_wrap is not None:
            properties.remove(no_wrap)
        margins = properties.find(qn("w:tcMar"))
        if margins is None:
            margins = OxmlElement("w:tcMar")
            properties.append(margins)
        for edge in ("top", "bottom"):
            margin = margins.find(qn("w:" + edge))
            if margin is None:
                margin = OxmlElement("w:" + edge)
                margins.append(margin)
            margin.set(qn("w:w"), "0")
            margin.set(qn("w:type"), "dxa")
        for paragraph in cell.paragraphs:
            paragraph.paragraph_format.left_indent = Pt(5.1)
            paragraph.paragraph_format.right_indent = Pt(5.1)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            if paragraph.text.strip() == "Cause of Outage:":
                runs = paragraph.runs
                run = next((r for r in runs if r.text.strip()), None)
                if run is not None:
                    run.text = "Cause of\nOutage:"
                    for other in runs:
                        if other._element is not run._element:
                            other._element.getparent().remove(other._element)
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST


def _append_heading(document, text):
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.keep_with_next = True
    paragraph.paragraph_format.space_before = Pt(12)
    run = paragraph.add_run(text)
    run.bold = True
    run.font.name = "Times New Roman"
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0, 0, 0)


def _append_pictures(document, pictures, title):
    if not pictures:
        return
    _append_heading(document, title)
    for picture in pictures:
        payload = base64.b64decode(picture["data_base64"])
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.keep_with_next = True
        shape = paragraph.add_run().add_picture(BytesIO(payload), width=Inches(5.5))
        if shape.height > Inches(6.5):
            shape.width = int(shape.width * Inches(6.5) / shape.height)
            shape.height = Inches(6.5)
        caption = document.add_paragraph()
        run = caption.add_run(picture.get("filename") or "")
        run.font.name = "Times New Roman"
        run.font.size = Pt(9)


def build_october_docx(report):
    document = Document(TEMPLATE)
    table = document.tables[0]
    _align_reference_table(document, table)
    _normalize_cell_borders(table)
    original = list(table.rows)
    for paragraph in original[13].cells[0].paragraphs:
        for run in paragraph.runs:
            run.font.color.rgb = RGBColor(0, 0, 0)
    remarks = report.get("summary_remarks") or {}
    for index, (field, default) in enumerate(SUMMARY_FIELDS, 1):
        value = report.get(field, default)
        if field == "time_issue":
            value = value or report.get("raise_time")
        _write(original[index].cells[1], value)
        _write(original[index].cells[2], remarks.get(field, ""))

    # Keep every event's own date; a midnight crossing must never inherit the wrong day.
    anchor = original[14]._tr
    for event in report.get("chronology_events") or []:
        element = deepcopy(original[16]._tr)
        anchor.addnext(element)
        anchor = element
        row = _Row(element, table)
        date = event.get("date") or report.get("incident_date") or ""
        _write(row.cells[0], (date + "   " + (event.get("time") or "")).strip())
        _write(row.cells[1], event.get("description"))
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    for row in original[15:23]:
        table._tbl.remove(row._tr)

    _write(original[24].cells[1], report.get("cause_of_outage"))
    _write(original[25].cells[1], report.get("resolution"))
    _write(original[26].cells[1], report.get("permanent_fixed"))
    if report.get("has_second_fault"):
        _write(original[28].cells[1], report.get("cause_of_outage_2"))
        _write(original[29].cells[1], report.get("resolution_2"))
        _write(original[30].cells[1], report.get("permanent_fixed_2"))
    else:
        for row in original[27:31]:
            table._tbl.remove(row._tr)
        _write(original[24].cells[0], "Cause of Outage:")

    _fit_fault_labels(original[24:27] + (original[28:31] if report.get("has_second_fault") else []))

    # User-authored overflow must grow rather than clip at a reference sample's height.
    for row in table.rows:
        if row.height_rule != WD_ROW_HEIGHT_RULE.EXACTLY:
            row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST

    title = report.get("document_title") or "Official Incident Report"
    if title != "Official Incident Report":
        for section in document.sections:
            nodes = section.header._element.xpath(".//w:t")
            combined = "".join(node.text or "" for node in nodes)
            positions = []
            offset = 0
            for node in nodes:
                length = len(node.text or "")
                positions.append((node, offset, offset + length))
                offset += length
            # Headers contain both DrawingML and legacy text-box versions of the title.
            for match in reversed(list(re.finditer(re.escape("Official Incident Report"), combined))):
                inserted = False
                for node, begin, finish in positions:
                    if begin < match.end() and finish > match.start():
                        text = node.text or ""
                        left = max(0, match.start() - begin)
                        right = min(finish, match.end()) - begin
                        node.text = text[:left] + (title if not inserted else "") + text[right:]
                        inserted = True

    # Legacy detail values stay saved but are not part of the October reference export.
    pictures = report.get("picture_references") or []
    if pictures:
        document.add_page_break()
        _append_pictures(document, [p for p in pictures if p.get("fault") == "1"], "1st Fault - Picture Reference")
        second_title = "2nd Fault - Picture Reference" if report.get("has_second_fault") else "Retained second-fault pictures"
        _append_pictures(document, [p for p in pictures if p.get("fault") == "2"], second_title)
        _append_pictures(document, [p for p in pictures if p.get("fault") not in ("1", "2")], "Picture Reference")
    output = BytesIO()
    document.save(output)
    return output.getvalue()
