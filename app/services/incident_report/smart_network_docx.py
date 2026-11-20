"""Fill the supplied Sep-Oct 2026 revision (2) without rebuilding its design.

Six tables cover inventory, monthly availability, its mirrored summary,
Failure to React, Services Outage Report, and Credit Note Summary.
Source styles, section orientations, logos, headers and footers are retained.
The credit summary uses aligned header merges and an inline, full-width footer.
"""

import copy
from io import BytesIO
from pathlib import Path


from docx import Document
from docx.shared import Twips
from docx.text.paragraph import Paragraph
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.table import _Cell
from docx.enum.table import WD_ROW_HEIGHT_RULE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from app.utils.smart_report import report_year_suffix

_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "template" / "smart_network_report_template.docx"
)

_MONTH_KEYS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _delete_run(run):
    run._element.getparent().remove(run._element)


def _delete_paragraph(paragraph):
    p = paragraph._p
    p.getparent().remove(p)


def _set_paragraph_text(paragraph, text):
    """Replace text while preserving the first run formatting."""
    if paragraph.text == (text or ""):
        return
    runs = paragraph.runs
    if runs:
        runs[0].text = text or ""
        for r in list(runs[1:]):
            _delete_run(r)
    else:
        paragraph.add_run(text or "")


def _set_cell_value(cell, text):
    """Overwrites a cell's text while keeping its first run's formatting
    (font/size/color) exactly as the template had it."""
    if cell.text == (text or ""):
        return
    _set_paragraph_text(cell.paragraphs[0], text)
    for p in list(cell.paragraphs[1:]):
        _delete_paragraph(p)


def _clone_row(table, index):
    """Copy row XML to retain template borders, shading and fonts."""
    anchor_tr = table.rows[index]._tr
    new_tr = copy.deepcopy(anchor_tr)
    anchor_tr.addnext(new_tr)
    return table.rows[index + 1]


def _find_paragraph(document, text):
    for p in document.paragraphs:
        if p.text == text:
            return p
    raise ValueError(f"Smart Network Report template is missing expected paragraph {text!r}")


def _trim_to_one_row(table, anchor_index):
    """Keep one data row as the formatting anchor and remove sample rows."""
    while len(table.rows) > anchor_index + 1:
        last_tr = table.rows[-1]._tr
        last_tr.getparent().remove(last_tr)


def _fill_circuits_table(table, circuits):
    _trim_to_one_row(table, 1)
    row = table.rows[1]
    if not circuits:
        for cell in row.cells:
            _set_cell_value(cell, "")
        return
    for i, c in enumerate(circuits, start=1):
        if i > 1:
            row = _clone_row(table, len(table.rows) - 1)
        _set_cell_value(row.cells[0], str(i))
        _set_cell_value(row.cells[1], c.get("customer_description"))
        _set_cell_value(row.cells[2], c.get("service"))
        _set_cell_value(row.cells[3], c.get("bandwidth"))
        _set_cell_value(row.cells[4], c.get("circuit_id"))


def _monthly_cells(row):
    """One cell per visible field, regardless of Word's underlying grid spans."""
    return [_Cell(cell, row._parent) for cell in row._tr.tc_lst]


def _fill_monthly_table(table, rows, year_suffix):
    header = _monthly_cells(table.rows[1])
    for i, label in enumerate(_MONTH_LABELS):
        _set_cell_value(header[2 + i], f"{label}-{year_suffix}")

    _trim_to_one_row(table, 2)
    row = table.rows[2]
    if not rows:
        for cell in _monthly_cells(row):
            _set_cell_value(cell, "")
        return
    for i, item in enumerate(rows, start=1):
        if i > 1:
            row = _clone_row(table, len(table.rows) - 1)
        cells = _monthly_cells(row)
        _set_cell_value(cells[0], str(i))
        _set_cell_value(cells[1], item.get("circuit"))
        months = item.get("months") or {}
        for j, key in enumerate(_MONTH_KEYS):
            _set_cell_value(cells[2 + j], months.get(key))


def _fit_data_rows(table, count):
    """Keep each reference row's formatting; clone only additional rows."""
    wanted = max(1, count)
    while len(table.rows) > wanted + 1:
        row = table.rows[-1]._tr
        row.getparent().remove(row)
    while len(table.rows) < wanted + 1:
        _clone_row(table, len(table.rows) - 1)
    return list(table.rows)[1:]


def _fill_detail_table(table, items, keys):
    for row, item in zip(_fit_data_rows(table, len(items)), items or [{}]):
        changed = any(item.get(key) and row.cells[index].text != item[key]
                      for index, key in enumerate(keys))
        for column, key in enumerate(keys):
            _set_cell_value(row.cells[column], item.get(key) or "")
        if changed:
            # Retain the reference height as a minimum; longer user notes can grow.
            row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST


def _fill_outage_table(table, outages):
    _fill_detail_table(table, outages, (
        "ticket_no", "circuit_id", "date_started", "date_finished",
        "service", "issue_owner", "interruption", "notes",
    ))


def _fill_reaction_table(table, reactions):
    _fill_detail_table(table, reactions, (
        "ticket_no", "circuit_id", "occurred_time", "smart_complain", "tct_respond",
        "failure_to_react", "sla", "service_credit", "note",
    ))


def _align_credit_table(table):
    """Use one column grid and merge labels without splitting the footer text."""
    table.autofit = False
    floating = table._tbl.tblPr.find(qn("w:tblpPr"))
    if floating is not None:
        # Word offsets shading from borders in floating tables. Keep the placement
        # as an inline indent and paragraph spacing instead.
        horizontal = int(floating.get(qn("w:tblpX"), "0"))
        vertical = int(floating.get(qn("w:tblpY"), "0"))
        indent = table._tbl.tblPr.find(qn("w:tblInd"))
        if indent is None:
            indent = OxmlElement("w:tblInd")
            table._tbl.tblPr.append(indent)
        indent.set(qn("w:w"), str(horizontal))
        indent.set(qn("w:type"), "dxa")
        previous = table._tbl.getprevious()
        if previous is not None and previous.tag == qn("w:p") and vertical > 0:
            paragraph = Paragraph(previous, table._parent)
            paragraph.paragraph_format.space_after = (
                (paragraph.paragraph_format.space_after or 0) + Twips(vertical)
            )
        table._tbl.tblPr.remove(floating)
    spacing = table._tbl.tblPr.find(qn("w:tblCellSpacing"))
    if spacing is not None:
        table._tbl.tblPr.remove(spacing)
    grid = table._tbl.tblGrid.gridCol_lst
    widths = [column.w for column in grid]
    for row_index, row in enumerate(table.rows):
        if row_index >= 2:
            row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        column = 0
        for cell in row._tr.tc_lst:
            span = cell.grid_span
            properties = cell.get_or_add_tcPr()
            no_wrap = properties.find(qn("w:noWrap"))
            if no_wrap is not None:
                properties.remove(no_wrap)
            properties.get_or_add_tcW().set(
                qn("w:w"), str(sum(widths[column:column + span]) // 635),
            )
            column += span
    # The reference has separate header rows and one blank cell before January.
    blank = table.cell(1, 0).merge(table.cell(1, 1))
    _set_cell_value(blank, "")
    footer = table.rows[-1]
    label = footer.cells[0]
    if label._tc is not footer.cells[-1]._tc:
        label = label.merge(footer.cells[-1])
    _set_cell_value(label, "Credit amount (USD)")
    label.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
    header_runs = table.cell(0, 0).paragraphs[0].runs
    if header_runs:
        for run in label.paragraphs[0].runs:
            run.font.name = header_runs[0].font.name
    shading = label._tc.tcPr.find(qn("w:shd"))
    fill = shading.get(qn("w:fill")) if shading is not None else "E36C0A"
    # Fill the table background so Word cannot leave white seams at shaded edges.
    table_shading = table._tbl.tblPr.find(qn("w:shd"))
    if table_shading is None:
        table_shading = OxmlElement("w:shd")
        table._tbl.tblPr.append(table_shading)
    table_shading.set(qn("w:val"), "clear")
    table_shading.set(qn("w:fill"), fill)
    for row_index, row in enumerate(table.rows):
        for cell in row._tr.tc_lst:
            cell_shading = cell.tcPr.find(qn("w:shd"))
            if cell_shading is None:
                cell_shading = OxmlElement("w:shd")
                cell.tcPr.append(cell_shading)
            cell_shading.set(qn("w:val"), "clear")
            cell_shading.set(qn("w:fill"), fill if row_index in (0, len(table.rows) - 1) else "FFFFFF")
    borders = table._tbl.tblPr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        table._tbl.tblPr.append(borders)
    for child in list(borders):
        borders.remove(child)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement("w:" + edge)
        for key, value in (("val", "single"), ("sz", "4"), ("space", "0"), ("color", fill)):
            border.set(qn("w:" + key), value)
        borders.append(border)
    # Cell overrides produce seams against the shared table border in Word.
    for row in table.rows:
        for cell in row._tr.tc_lst:
            override = cell.tcPr.find(qn("w:tcBorders"))
            if override is not None:
                cell.tcPr.remove(override)


def _fill_credit_table(table, credits, amounts, year_suffix):
    footer = copy.deepcopy(table.rows[-1]._tr)
    table.rows[-1]._tr.getparent().remove(table.rows[-1]._tr)
    _fill_monthly_table(table, credits, year_suffix)
    table._tbl.append(footer)
    _align_credit_table(table)
    values = [f"{label}: {amounts[key]}" for key, label in zip(_MONTH_KEYS, _MONTH_LABELS)
              if amounts.get(key) is not None and str(amounts[key]).strip()]
    text = "Credit amount (USD)"
    if values:
        text += "   " + ", ".join(values)
    _set_cell_value(table.rows[-1].cells[0], text)


def build_docx(report):
    """report: a dict shaped like IncidentReportRepository._to_dict()'s
    output for a report_type == 'smart_network' row (smart_customer_name,
    smart_report_month, smart_active_circuits, smart_monthly_outage,
    smart_fault_services, smart_services_outage). Returns .docx bytes."""
    document = Document(str(_TEMPLATE_PATH))
    year_suffix = report_year_suffix(report.get("smart_report_month"))

    # "Document Title" is user-editable on the form (defaults to blank)
    # but previously had no effect on the export at all — the template's
    # own "MONTHLY REPORT" text was always left untouched. Falls back to
    # that same original title when left blank, so an existing report
    # saved before this field existed still exports identically.
    _set_paragraph_text(
        _find_paragraph(document, "MONTHLY REPORT"),
        (report.get("document_title") or "MONTHLY REPORT").upper(),
    )
    _set_paragraph_text(
        _find_paragraph(document, "SMART AXIATA"),
        (report.get("smart_customer_name") or "").upper(),
    )
    _set_paragraph_text(
        _find_paragraph(document, "Sep-Oct 2026"),
        report.get("smart_report_month") or "",
    )

    _fill_circuits_table(document.tables[0], report.get("smart_active_circuits") or [])
    _fill_monthly_table(document.tables[1], report.get("smart_monthly_outage") or [], year_suffix)
    _fill_monthly_table(document.tables[2], report.get("smart_fault_services") or [], year_suffix)
    _fill_reaction_table(document.tables[3], report.get("smart_failure_to_react") or [])
    _fill_outage_table(document.tables[4], report.get("smart_services_outage") or [])
    _fill_credit_table(document.tables[5], report.get("smart_credit_note") or [],
                       report.get("smart_credit_amounts") or {}, year_suffix)

    buf = BytesIO()
    document.save(buf)
    return buf.getvalue()
